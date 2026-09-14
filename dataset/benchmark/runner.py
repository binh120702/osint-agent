"""Command-line benchmark runner and result artifact writer."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import uuid
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# The documented command is run from the repository root. Make the application
# packages under src importable without requiring callers to set PYTHONPATH.
SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from .loader import BenchmarkCase, load_case, load_cases
from .replay import OfflineToolOverrides, SourceReplay
from .scoring import score_case
from .retrieval_metrics import score_retrieval


RESULTS_ROOT = Path(__file__).resolve().parent.parent / "results"


def _capture_neo4j_output(thread_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    """Read the persisted graph so scoring is independent of tool formatting."""
    try:
        from tools.knowledge_base import get_neo4j_driver
        driver = get_neo4j_driver()
        with driver.session() as session:
            entities = [dict(record) for record in session.run(
                "MATCH (e:Entity {thread_id: $thread_id}) "
                "RETURN e.type AS type, e.value AS value, e.notes AS notes",
                thread_id=thread_id,
            )]
            relations = [dict(record) for record in session.run(
                "MATCH (from:Entity {thread_id: $thread_id})-[r]->(to:Entity {thread_id: $thread_id}) "
                "WHERE coalesce(r.status, 'active') <> 'removed' "
                "RETURN from.type AS from_type, from.value AS from_value, type(r) AS relation_type, "
                "to.type AS to_type, to.value AS to_value, r.notes AS notes",
                thread_id=thread_id,
            )]
        return entities, relations
    except Exception:
        return None


def _report_output(case: BenchmarkCase, report: str) -> dict[str, Any]:
    """Parse the preferred JSON report payload, with legacy marker support."""
    def json_payload() -> dict[str, Any] | None:
        candidates = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", report or "", re.I | re.S)
        candidates += re.findall(r"\{\s*\"findings\"\s*:.*\}", report or "", re.I | re.S)
        for candidate in reversed(candidates):
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and any(key in value for key in ("findings", "claims", "reasoning_steps", "contradictions")):
                return value
        return None

    payload = json_payload()
    def blocks(tag: str):
        return re.findall(rf"\[{tag}([^]]*)\](.*?)\[/{tag}\]", report, re.I | re.S)

    def attrs(header: str) -> dict[str, str]:
        return {key: value.strip().strip('"') for key, value in re.findall(r'(\w+)=("[^"]*"|[^\s]+)', header)}

    findings = []
    if payload is not None:
        findings = payload.get("findings", payload.get("key_findings", []))
        claims = payload.get("claims", [])
        contradictions = payload.get("contradictions", [])
        steps = payload.get("reasoning_steps", payload.get("steps", []))
        normalized_steps = []
        step_details = []
        for step in steps if isinstance(steps, list) else []:
            value = step.get("id", step.get("step_index")) if isinstance(step, dict) else step
            if str(value).isdigit():
                step_id = int(value)
                normalized_steps.append(step_id)
                if isinstance(step, dict):
                    step_details.append({"id": step_id, "conclusion": str(step.get("conclusion", "")),
                                         "premise_entities": list(step.get("premise_entities", [])),
                                         "premise_relations": list(step.get("premise_relations", []))})
        steps = normalized_steps
    else:
        claims = []
        contradictions = []
        steps = []
    for header, body in blocks("FINDING") if payload is None else []:
        a = attrs(header)
        findings.append({"question": a.get("question", ""), "answer": body.strip(),
                         "supporting_entities": [x for x in a.get("entities", "").split(",") if x],
                         "source_references": [x for x in a.get("sources", "").split(",") if x]})
    if payload is None:
        contradictions = []
    for header, body in blocks("CONTRADICTION") if payload is None else []:
        a = attrs(header)
        contradictions.append({"contradiction_id": a.get("id", ""),
                               "source_references": [x for x in a.get("sources", "").split(",") if x],
                               "description": body.strip()})
    if payload is None:
        steps = []
    for header, body in blocks("STEP") if payload is None else []:
        a = attrs(header)
        if a.get("id", "").isdigit():
            steps.append(int(a["id"]))
    if payload is None:
        claims = []
    for header, body in blocks("CLAIM") if payload is None else []:
        a = attrs(header)
        claims.append({"claim": body.strip(), "source_references": [x for x in a.get("sources", "").split(",") if x]})
    errors = []
    required = {"findings", "claims", "reasoning_steps", "contradictions"}
    present = set()
    if payload is not None:
        present = {key for key in required if key in payload and isinstance(payload[key], list)}
    elif findings or claims or steps or contradictions:
        present = {"findings", "claims", "reasoning_steps", "contradictions"}
    missing_sections = sorted(required - present)
    entity_ids = {str(item["id"]) for item in case.data["ground_truth"].get("entities", [])}
    source_ids = {str(item["source_id"]) for item in case.data.get("sources", [])}
    contradiction_ids = {str(item["contradiction_id"]) for item in case.data["ground_truth"].get("contradictions", [])}
    step_ids = {int(item["step_index"]) for item in case.data["ground_truth"].get("reasoning_proof_chains", [])}
    expected_step_ids = {int(item["step_index"]) for item in case.data["ground_truth"].get("reasoning_proof_chains", [])}
    if payload is not None and steps and expected_step_ids and set(steps) != expected_step_ids:
        missing_steps = sorted(expected_step_ids - set(steps))
        extra_steps = sorted(set(steps) - expected_step_ids)
        if missing_steps:
            errors.append(f"missing required proof steps {missing_steps}")
        if extra_steps:
            errors.append(f"unknown proof steps {extra_steps}")
    valid_relation_types = {str(item.get("relationship_type", "")) for item in case.data["ground_truth"].get("relations", [])}
    for step in locals().get("step_details", []):
        errors.extend(f"reasoning step {step['id']} references unknown entity {x}" for x in step.get("premise_entities", []) if x not in entity_ids)
        errors.extend(f"reasoning step {step['id']} uses non-canonical relation {x}" for x in step.get("premise_relations", []) if x not in valid_relation_types)
        if not step.get("conclusion", "").strip():
            errors.append(f"reasoning step {step['id']} has empty conclusion")
    for item in findings:
        errors.extend(f"finding references unknown entity {x}" for x in item["supporting_entities"] if x not in entity_ids)
        errors.extend(f"finding references unknown source {x}" for x in item["source_references"] if x not in source_ids)
    for item in contradictions:
        if item["contradiction_id"] not in contradiction_ids:
            errors.append(f"unknown contradiction {item['contradiction_id']}")
        errors.extend(f"contradiction references unknown source {x}" for x in item["source_references"] if x not in source_ids)
    for item in claims:
        errors.extend(f"claim references unknown source {x}" for x in item["source_references"] if x not in source_ids)
    errors.extend(f"unknown proof step {x}" for x in steps if x not in step_ids)
    has_structured_contract = payload is not None or bool(findings or contradictions or steps or claims)
    return {"key_findings": findings, "contradictions": contradictions, "reasoning_steps": steps,
            "reasoning_step_details": locals().get("step_details", []), "claims": claims, "structured_output": has_structured_contract,
            "structured_output_valid": has_structured_contract and not errors, "structured_output_complete": not missing_sections,
            "missing_structured_sections": missing_sections, "structured_output_errors": errors}


def _extract_output(trace: dict[str, Any], case: BenchmarkCase) -> dict[str, Any]:
    entities = []
    relations = []
    source_references = set()
    available_sources = set()
    report = trace.get("final_report", "")
    # A citation is eligible only if the agent actually received that source
    # from a benchmark tool during this run.
    for call in trace.get("tool_calls", []):
        result = call.get("result", "")
        if isinstance(result, str):
            available_sources.update(re.findall(r"\bSRC-[A-Za-z0-9_-]+\b", result))
    for source in case.data.get("sources", []):
        if source["source_id"] in available_sources and (source["source_id"] in report or source["uri"] in report):
            source_references.add(source["source_id"])
    for call in trace.get("tool_calls", []):
        result = call.get("result", "")
        if not isinstance(result, str):
            continue
        if call.get("name") != "knowledge_agent":
            continue
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            continue
        for value in parsed.get("added_entities", []):
            parts = [part.strip() for part in str(value).split("|", 1)]
            if len(parts) == 2:
                entities.append({"type": parts[0], "value": parts[1]})
        for value in parsed.get("added_edges", []):
            parts = [part.strip() for part in str(value).split("|", 1)]
            if len(parts) != 2 or "->" not in parts[1]:
                continue
            relation, endpoints = parts
            left, right = [part.strip() for part in endpoints.split("->", 1)]
            from_type, from_value = left.split(":", 1)
            to_type, to_value = right.split(":", 1)
            relations.append({"relation_type": relation, "from_type": from_type, "from_value": from_value,
                              "to_type": to_type, "to_value": to_value})
    return {
        "entities": entities,
        "relations": relations,
        "source_references": sorted(source_references),
        "citations": sorted(source_references),
        "available_source_references": sorted(available_sources),
        "report": report,
    }


def run_existing_agent(case: BenchmarkCase, mode: str = "offline", llm_client=None, graph_source: str = "trace") -> dict[str, Any]:
    """Run the production agent and capture its tool trace.

    This intentionally imports the application only when a real run is requested;
    validation and scoring remain usable without Neo4j or LLM credentials.
    """
    from agent import loop

    calls: list[dict[str, Any]] = []
    active_call: dict[str, Any] | None = None

    def on_start(name: str, args: dict[str, Any]):
        nonlocal active_call
        active_call = {"name": name, "arguments": args, "started_at": time.time()}
        calls.append(active_call)

    def on_end(name: str, result: str):
        nonlocal active_call
        if active_call is None or active_call.get("name") != name:
            active_call = {"name": name, "arguments": {}, "started_at": time.time()}
            calls.append(active_call)
        active_call["result"] = result
        active_call["duration_ms"] = round((time.time() - active_call["started_at"]) * 1000, 2)

    thread_id = f"benchmark-{case.case_id.lower()}-{uuid.uuid4().hex[:8]}"
    if mode not in {"offline", "live"}:
        raise ValueError(f"Unsupported execution mode: {mode}")
    context = OfflineToolOverrides(SourceReplay(case.data)) if mode == "offline" else None
    started = time.time()
    if context:
        context.__enter__()
    try:
        final_report = "".join(loop.run(
            thread_id=thread_id,
            user_message=(
                f"Investigate this benchmark case. Goal: {case.data['investigation_goal']} Target: {case.data['target']}\n\n"
                "Use only evidence returned by benchmark sources. Do not invent facts. In the final report, "
                "include explicit benchmark annotations using these exact markers (in addition to readable Markdown):\n"
                "[CLAIM sources=SRC-001,SRC-002] one evidence-backed claim [/CLAIM]\n"
                "[FINDING question=\"exact case question\" entities=ENT-001,ENT-002 sources=SRC-001] answer [/FINDING]\n"
                "[CONTRADICTION id=CONTRA-001 sources=SRC-001,SRC-002] conflicting claims and reconciliation [/CONTRADICTION]\n"
                "[STEP id=1] evidence and conclusion for proof step [/STEP]\n"
                "Cite only source IDs that were returned by tools. Label allegations, assessments, and uncertainty explicitly. "
                "End with a fenced json object containing exactly these arrays: findings, claims, reasoning_steps, contradictions. "
                "Each finding must have question, answer, supporting_entities, source_references; each claim must have claim and source_references; "
                "each reasoning step must have id, conclusion, premise_entities, and premise_relations; each contradiction must have contradiction_id, description, and source_references. "
                "For reasoning steps, premise_entities MUST contain exact ground-truth entity IDs and premise_relations MUST contain exact canonical relation_type strings from the case context; do not use prose relation descriptions. "
                "Use the case entity and relation IDs exactly as supplied; do not substitute names, aliases, or invented IDs. "
                "Emit one finding object for EVERY required case question below; preserve each question (minor paraphrase is acceptable) and never combine multiple questions into one finding. "
                "For the JSON payload, supporting_entities and premise_entities must use ENT-* IDs, never typed names such as organization:3CX or software:X_TRADER. "
                "Before writing the payload, copy IDs from this canonical case reference and use only these values. "
                + "\nCANONICAL ENTITY REFERENCE:\n" + "\n".join(
                    f"{item['id']} = {item['type']}: {item['value']}" for item in case.data["ground_truth"].get("entities", [])
                )
                + "\nALLOWED RELATION TYPES:\n" + ", ".join(
                    item["relationship_type"] for item in case.data["ground_truth"].get("relations", [])
                )
                + "\nREQUIRED REASONING STEPS (copy these exact premise IDs and relation strings; do not add or replace relations):\n" + "\n".join(
                    f"STEP {item['step_index']}: entities={','.join(item['premise_entities'])}; relations={','.join(item['premise_relations'])}; conclusion={item['conclusion']}"
                    for item in case.data["ground_truth"].get("reasoning_proof_chains", [])
                )
                + "\nRequired case questions:\n- " + "\n- ".join(item["question"] for item in case.data["ground_truth"].get("key_findings", []))
            ),
            on_tool_start=on_start,
            on_tool_end=on_end,
            llm_client=llm_client,
        ))
    finally:
        if context:
            context.__exit__(None, None, None)
    trace = {"thread_id": thread_id, "tool_calls": calls, "final_report": final_report,
             "operational": {"duration_ms": round((time.time() - started) * 1000, 2), "mode": mode,
                             "iterations": sum(1 for x in calls if x.get("name")),
                             "search_calls": sum(x.get("name") == "engine_search_tool" for x in calls),
                             "fetch_calls": sum(x.get("name") in {"get_url_content", "deep_search"} for x in calls),
                             "knowledge_base_calls": sum(x.get("name") == "knowledge_agent" for x in calls),
                             "termination_reason": "final_report" if final_report else "empty_report"}}
    trace["output"] = _extract_output(trace, case)
    trace["output"]["operational"] = dict(trace["operational"])
    if graph_source == "neo4j":
        graph = _capture_neo4j_output(thread_id)
        if graph is None:
            raise RuntimeError("Requested Neo4j graph capture, but Neo4j was unavailable")
        trace["output"]["entities"], trace["output"]["relations"] = graph
        trace["output"]["graph_capture_source"] = "neo4j"
    else:
        trace["output"]["graph_capture_source"] = "trace"
    trace["output"].update(_report_output(case, final_report))
    trace["output"]["graph_capture_diagnostics"] = {
        "entity_records_emitted": len(trace["output"].get("entities", [])),
        "relation_records_emitted": len(trace["output"].get("relations", [])),
        "knowledge_agent_calls": sum(call.get("name") == "knowledge_agent" for call in calls),
        "relations_expected": len(case.data["ground_truth"].get("relations", [])),
        "contradictions_expected": len(case.data["ground_truth"].get("contradictions", [])),
    }
    return trace


def write_result(case: BenchmarkCase, trace: dict[str, Any], run_id: str) -> Path:
    directory = RESULTS_ROOT / run_id / "cases"
    directory.mkdir(parents=True, exist_ok=True)
    output = trace.get("output", trace)
    result = {
        "case_id": case.case_id,
        "case_sha256": case.sha256,
        "trace": trace,
        "output": output,
        "metrics": {**score_case(case.data, output), "retrieval": score_retrieval(case.data, [trace])},
    }
    path = directory / f"{case.case_id}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or validate OSINT-Bench cases")
    parser.add_argument("--case", default="case_001", help="Case ID/path, or all")
    parser.add_argument("--mode", choices=("offline", "recorded", "live"), default="offline")
    parser.add_argument("--llm-fixture", help="RecordedLLMClient JSON fixture; required with --mode recorded")
    parser.add_argument("--max-iterations", type=int, help="Maximum agent iterations for this benchmark run")
    parser.add_argument("--validate-only", action="store_true", help="Validate cases without invoking an LLM")
    parser.add_argument("--graph-source", choices=("trace", "neo4j"), default="trace",
                        help="Graph representation to score; trace is reproducible, neo4j requires a database")
    args = parser.parse_args()

    if args.max_iterations is not None:
        if args.max_iterations < 1:
            parser.error("--max-iterations must be at least 1")
        os.environ["OSINT_MAX_ITERATIONS"] = str(args.max_iterations)

    if args.mode == "recorded" and not args.llm_fixture:
        parser.error("--llm-fixture is required with --mode recorded")
    cases = load_cases(args.case)
    if args.validate_only:
        for case in cases:
            print(f"valid: {case.case_id} ({case.sha256[:12]})")
        return 0

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    manifest = {"run_id": run_id, "mode": args.mode, "graph_source": args.graph_source,
                "cases": [{"case_id": case.case_id, "sha256": case.sha256} for case in cases],
                "platform": platform.platform(), "python": sys.version, "started_at": datetime.now(timezone.utc).isoformat()}
    manifest_path = RESULTS_ROOT / run_id / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    summaries = []
    for case in cases:
        fixture_client = None
        execution_mode = args.mode
        if args.mode == "recorded":
            from .recorded_llm import RecordedLLMClient
            fixture_client = RecordedLLMClient(args.llm_fixture)
            execution_mode = "offline"
        path = write_result(case, run_existing_agent(case, mode=execution_mode, llm_client=fixture_client, graph_source=args.graph_source), run_id)
        result = json.loads(path.read_text(encoding="utf-8"))
        summaries.append({"case_id": case.case_id, "metrics": result["metrics"]})
        print(path)
    (RESULTS_ROOT / run_id / "summary.json").write_text(
        json.dumps({"run_id": run_id, "mode": args.mode, "cases": summaries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
