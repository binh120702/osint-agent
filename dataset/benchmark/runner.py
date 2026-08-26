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
    """Derive structured benchmark fields from the final report without a judge."""
    normalized_report = report.casefold()
    report_tokens = set(re.findall(r"[a-z0-9_@.-]+", normalized_report))
    findings = []
    for finding in case.data["ground_truth"].get("key_findings", []):
        answer_tokens = {token for token in re.findall(r"[a-z0-9_@.-]+", finding["answer"].casefold()) if len(token) > 3}
        overlap = len(answer_tokens & report_tokens) / len(answer_tokens) if answer_tokens else 0
        supporting = []
        for entity in case.data["ground_truth"]["entities"]:
            if entity["id"] in finding.get("supporting_entities", []) and entity["value"].casefold() in normalized_report:
                supporting.append(entity["id"])
        if overlap >= 0.25:
            findings.append({"question": finding["question"], "answer": report, "supporting_entities": supporting})

    reasoning_steps = []
    for step in case.data["ground_truth"].get("reasoning_proof_chains", []):
        premise_values = []
        entities_by_id = {item["id"]: item for item in case.data["ground_truth"]["entities"]}
        for entity_id in step.get("premise_entities", []):
            value = entities_by_id.get(entity_id, {}).get("value", "")
            if value and value.casefold() in normalized_report:
                premise_values.append(value)
        conclusion_tokens = {token for token in re.findall(r"[a-z0-9_@.-]+", step["conclusion"].casefold()) if len(token) > 3}
        if len(premise_values) >= max(1, len(step.get("premise_entities", [])) // 2) and len(conclusion_tokens & report_tokens) >= 3:
            reasoning_steps.append(step["step_index"])
    return {"key_findings": findings, "reasoning_steps": reasoning_steps}


def _extract_output(trace: dict[str, Any], case: BenchmarkCase) -> dict[str, Any]:
    entities = []
    relations = []
    source_references = set()
    report = trace.get("final_report", "")
    # Only citations present in the final report count as traceability evidence.
    for source in case.data.get("sources", []):
        if source["source_id"] in report or source["uri"] in report:
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
        "report": report,
    }


def run_existing_agent(case: BenchmarkCase, mode: str = "offline", llm_client=None) -> dict[str, Any]:
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
    context = OfflineToolOverrides(SourceReplay(case.data)) if mode == "offline" else None
    started = time.time()
    if context:
        context.__enter__()
    try:
        final_report = "".join(loop.run(
            thread_id=thread_id,
            user_message=f"Investigate this benchmark case. Goal: {case.data['investigation_goal']} Target: {case.data['target']}",
            on_tool_start=on_start,
            on_tool_end=on_end,
            llm_client=llm_client,
        ))
    finally:
        if context:
            context.__exit__(None, None, None)
    trace = {"thread_id": thread_id, "tool_calls": calls, "final_report": final_report,
             "operational": {"duration_ms": round((time.time() - started) * 1000, 2), "mode": mode}}
    trace["output"] = _extract_output(trace, case)
    trace["output"]["operational"] = dict(trace["operational"])
    graph = _capture_neo4j_output(thread_id)
    if graph is not None:
        trace["output"]["entities"], trace["output"]["relations"] = graph
        trace["output"]["graph_capture_source"] = "neo4j"
    else:
        trace["output"]["graph_capture_source"] = "tool_result_fallback"
    trace["output"].update(_report_output(case, final_report))
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
        "metrics": score_case(case.data, output),
    }
    path = directory / f"{case.case_id}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or validate OSINT-Bench cases")
    parser.add_argument("--case", default="case_001", help="Case ID/path, or all")
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument("--max-iterations", type=int, help="Maximum agent iterations for this benchmark run")
    parser.add_argument("--validate-only", action="store_true", help="Validate cases without invoking an LLM")
    args = parser.parse_args()

    if args.max_iterations is not None:
        if args.max_iterations < 1:
            parser.error("--max-iterations must be at least 1")
        os.environ["OSINT_MAX_ITERATIONS"] = str(args.max_iterations)

    cases = load_cases(args.case)
    if args.validate_only:
        for case in cases:
            print(f"valid: {case.case_id} ({case.sha256[:12]})")
        return 0

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    manifest = {"run_id": run_id, "mode": args.mode,
                "cases": [{"case_id": case.case_id, "sha256": case.sha256} for case in cases],
                "platform": platform.platform(), "python": sys.version, "started_at": datetime.now(timezone.utc).isoformat()}
    manifest_path = RESULTS_ROOT / run_id / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    summaries = []
    for case in cases:
        path = write_result(case, run_existing_agent(case, mode=args.mode), run_id)
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
