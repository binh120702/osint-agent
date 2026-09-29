from __future__ import annotations

import hashlib
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from dataset.benchmark.loader import load_case  # noqa: E402
from dataset.benchmark.runner import _report_output  # noqa: E402
from dataset.benchmark.scoring import score_case  # noqa: E402


CASE_IDS = [f"OSINT-{i:03d}" for i in range(1, 11)]
RUNS_ROOT = Path(__file__).parent / "runs"
CANDIDATE = "langchain-ai/open_deep_research"
ADAPTATION = "native-langgraph-snapshot-search-file-inference-v1"


def _json_payload(report: str) -> dict[str, Any] | None:
    """Return the last fenced JSON object in a report, if one is present."""
    candidates = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", report or "", re.I | re.S)
    for candidate in reversed(candidates):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _refs(value: Any) -> list[str]:
    return [str(item) for item in _list(value) if str(item).strip()]


def _normalize_contract(case: dict[str, Any], report: str) -> dict[str, Any]:
    """Normalize Open Deep Research's native JSON aliases to the shared scorer contract."""
    payload = _json_payload(report)
    if payload is None:
        try:
            return _report_output(load_case(case["case_id"]), report)
        except Exception as exc:
            return {
                "key_findings": [],
                "claims": [],
                "contradictions": [],
                "reasoning_steps": [],
                "reasoning_step_details": [],
                "structured_output": False,
                "structured_output_valid": False,
                "structured_output_complete": False,
                "missing_structured_sections": ["findings", "claims", "reasoning_steps", "contradictions"],
                "structured_output_errors": [f"parser failure: {type(exc).__name__}: {exc}"],
            }

    required = {"findings", "claims", "reasoning_steps", "contradictions"}
    errors: list[str] = []
    missing = sorted(key for key in required if not isinstance(payload.get(key), list))

    findings: list[dict[str, Any]] = []
    for index, item in enumerate(_list(payload.get("findings"))):
        if not isinstance(item, dict):
            errors.append(f"finding {index + 1} is not an object")
            continue
        findings.append({
            "question": str(item.get("question", "")),
            "answer": str(item.get("answer", item.get("finding", item.get("text", "")))),
            "supporting_entities": _refs(item.get("supporting_entities", item.get("entities", []))),
            "source_references": _refs(item.get("source_references", item.get("sources", []))),
        })

    claims: list[dict[str, Any]] = []
    for index, item in enumerate(_list(payload.get("claims"))):
        if not isinstance(item, dict):
            errors.append(f"claim {index + 1} is not an object")
            continue
        claims.append({
            "claim": str(item.get("claim", item.get("text", ""))),
            "source_references": _refs(item.get("source_references", item.get("sources", []))),
        })

    contradictions: list[dict[str, Any]] = []
    for index, item in enumerate(_list(payload.get("contradictions"))):
        if not isinstance(item, dict):
            errors.append(f"contradiction {index + 1} is not an object")
            continue
        contradictions.append({
            "contradiction_id": str(item.get("contradiction_id", item.get("id", ""))),
            "source_references": _refs(item.get("source_references", item.get("sources", []))),
            "description": str(item.get("description", item.get("text", ""))),
        })

    reasoning_steps: list[int] = []
    reasoning_details: list[dict[str, Any]] = []
    for index, item in enumerate(_list(payload.get("reasoning_steps"))):
        if not isinstance(item, dict):
            errors.append(f"reasoning step {index + 1} is not an object")
            continue
        raw_id = item.get("id", item.get("step_index"))
        if not str(raw_id).isdigit():
            errors.append(f"reasoning step {index + 1} has invalid id {raw_id!r}")
            continue
        step_id = int(raw_id)
        reasoning_steps.append(step_id)
        reasoning_details.append({
            "id": step_id,
            "conclusion": str(item.get("conclusion", "")),
            "premise_entities": _refs(item.get("premise_entities", [])),
            "premise_relations": _refs(item.get("premise_relations", [])),
        })

    entity_ids = {str(item["id"]) for item in case["ground_truth"].get("entities", [])}
    source_ids = {str(item["source_id"]) for item in case.get("sources", [])}
    relation_types = {str(item.get("relationship_type", "")) for item in case["ground_truth"].get("relations", [])}
    contradiction_ids = {str(item["contradiction_id"]) for item in case["ground_truth"].get("contradictions", [])}
    expected_steps = {int(item["step_index"]) for item in case["ground_truth"].get("reasoning_proof_chains", [])}

    for item in findings:
        errors.extend(f"finding references unknown entity {value}" for value in item["supporting_entities"] if value not in entity_ids)
        errors.extend(f"finding references unknown source {value}" for value in item["source_references"] if value not in source_ids)
        if not item["question"].strip():
            errors.append("finding has empty question")
        if not item["answer"].strip():
            errors.append("finding has empty answer")

    for item in claims:
        errors.extend(f"claim references unknown source {value}" for value in item["source_references"] if value not in source_ids)
        if not item["claim"].strip():
            errors.append("claim has empty text")

    for item in contradictions:
        if item["contradiction_id"] not in contradiction_ids:
            errors.append(f"unknown contradiction {item['contradiction_id']}")
        errors.extend(f"contradiction references unknown source {value}" for value in item["source_references"] if value not in source_ids)
        if not item["description"].strip():
            errors.append(f"contradiction {item['contradiction_id']} has empty description")

    seen_steps = set(reasoning_steps)
    if expected_steps and seen_steps != expected_steps:
        missing_steps = sorted(expected_steps - seen_steps)
        extra_steps = sorted(seen_steps - expected_steps)
        if missing_steps:
            errors.append(f"missing required proof steps {missing_steps}")
        if extra_steps:
            errors.append(f"unknown proof steps {extra_steps}")
    for step in reasoning_details:
        errors.extend(f"reasoning step {step['id']} references unknown entity {value}" for value in step["premise_entities"] if value not in entity_ids)
        errors.extend(f"reasoning step {step['id']} uses non-canonical relation {value}" for value in step["premise_relations"] if value not in relation_types)
        if not step["conclusion"].strip():
            errors.append(f"reasoning step {step['id']} has empty conclusion")

    present = {key for key in required if isinstance(payload.get(key), list)}
    if missing:
        errors.extend(f"missing structured section {key}" for key in missing)

    return {
        "key_findings": findings,
        "contradictions": contradictions,
        "reasoning_steps": reasoning_steps,
        "reasoning_step_details": reasoning_details,
        "claims": claims,
        "structured_output": True,
        "structured_output_valid": bool(present == required and not errors),
        "structured_output_complete": present == required,
        "missing_structured_sections": missing,
        "structured_output_errors": errors,
    }


def _available_source_ids(case: dict[str, Any], result: dict[str, Any]) -> list[str]:
    """Reconstruct exactly which snapshot rows the adapter exposed to the model."""
    max_results = 0
    for trace in result.get("search_trace", []):
        try:
            max_results = max(max_results, int(trace.get("max_results", 0)))
        except (TypeError, ValueError):
            continue
    return sorted(str(item["source_id"]) for item in case.get("sources", [])[:max_results])


def _score_case(case_id: str, case: dict[str, Any], artifact: Path, manifest_row: dict[str, Any] | None) -> dict[str, Any]:
    raw = json.loads(artifact.read_text(encoding="utf-8"))
    report = str(raw.get("report", ""))
    parsed = _normalize_contract(case, report)
    expected_sources = {str(item["source_id"]) for item in case.get("sources", [])}
    mentioned_sources = sorted(set(re.findall(r"\bSRC-[A-Za-z0-9_-]+\b", report)) & expected_sources)
    available_sources = _available_source_ids(case, raw)

    output = {
        "entities": [],
        "relations": [],
        "available_source_references": available_sources,
        "source_references": mentioned_sources,
        "citations": [],
        "report": report,
        **parsed,
    }
    metrics = score_case(case, output)
    artifact_sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest_hash = manifest_row.get("sha256") if manifest_row else None
    return {
        "case_id": case_id,
        "candidate": CANDIDATE,
        "adaptation": ADAPTATION,
        "artifact": str(artifact.relative_to(ROOT)).replace("\\", "/"),
        "artifact_sha256": artifact_sha256,
        "manifest_sha256": manifest_hash,
        "manifest_hash_match": manifest_hash == artifact_sha256 if manifest_hash else False,
        "report_sha256": hashlib.sha256(report.encode("utf-8")).hexdigest(),
        "status": "completed" if report and not report.startswith("Error generating final report:") else "report_failure",
        "output_summary": {
            "available_source_references": available_sources,
            "source_references": mentioned_sources,
            "key_findings": parsed["key_findings"],
            "claims": parsed["claims"],
            "reasoning_steps": parsed["reasoning_steps"],
            "contradictions": parsed["contradictions"],
            "structured_output_valid": parsed["structured_output_valid"],
            "structured_output_complete": parsed["structured_output_complete"],
            "structured_output_errors": parsed["structured_output_errors"],
        },
        "metrics": {
            "finding_f1": metrics["key_findings"]["f1"],
            "contradiction_grounded_f1": metrics["contradictions"]["grounded_f1"],
            "reasoning_grounded_score": metrics["reasoning_quality"]["grounded_score"],
            "report_quality": metrics["report_quality"]["score"],
            "source_precision": metrics["source_traceability"]["source_precision"],
            "source_recall": metrics["source_traceability"]["source_recall"],
            "entity_f1": "not_applicable",
            "relation_f1": "not_applicable",
        },
        "full_metrics": metrics,
    }


def _mean(rows: list[dict[str, Any]], key: str) -> float | str:
    values = [row["metrics"][key] for row in rows if isinstance(row["metrics"].get(key), (int, float))]
    return round(statistics.fmean(values), 10) if values else "not_applicable"


def main() -> None:
    manifest_path = RUNS_ROOT / "all-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest_rows = {str(row.get("case_id")): row for row in manifest.get("cases", [])}

    rows: list[dict[str, Any]] = []
    for case_id in CASE_IDS:
        case = load_case(case_id).data
        artifact = RUNS_ROOT / case_id / "io" / "candidate-result.json"
        if not artifact.exists():
            rows.append({"case_id": case_id, "status": "missing", "metrics": None})
            continue
        scored = _score_case(case_id, case, artifact, manifest_rows.get(case_id))
        rows.append(scored)
        (artifact.parent / "scored-result.json").write_text(json.dumps(scored, ensure_ascii=False, indent=2), encoding="utf-8")

    scored_rows = [row for row in rows if row.get("metrics")]
    aggregate = {
        "candidate": CANDIDATE,
        "adaptation": ADAPTATION,
        "source_revision": manifest.get("source_revision"),
        "model": manifest.get("model"),
        "cases_completed": len(scored_rows),
        "cases_total": len(CASE_IDS),
        "cases_with_reports": sum(row.get("status") == "completed" for row in scored_rows),
        "valid_structured_outputs": sum(bool(row["output_summary"]["structured_output_valid"]) for row in scored_rows),
        "complete_structured_outputs": sum(bool(row["output_summary"]["structured_output_complete"]) for row in scored_rows),
        "manifest_hash_matches": sum(bool(row.get("manifest_hash_match")) for row in scored_rows),
        "metrics": {
            "finding_f1": _mean(scored_rows, "finding_f1"),
            "contradiction_grounded_f1": _mean(scored_rows, "contradiction_grounded_f1"),
            "reasoning_grounded_score": _mean(scored_rows, "reasoning_grounded_score"),
            "report_quality": _mean(scored_rows, "report_quality"),
            "source_precision": _mean(scored_rows, "source_precision"),
            "source_recall": _mean(scored_rows, "source_recall"),
            "entity_f1": "not_applicable",
            "relation_f1": "not_applicable",
        },
        "case_results": [row["case_id"] for row in scored_rows],
        "cases": rows,
    }
    (RUNS_ROOT / "scored-aggregate.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: aggregate[key] for key in ("cases_completed", "cases_total", "cases_with_reports", "valid_structured_outputs", "complete_structured_outputs", "manifest_hash_matches", "metrics")}, indent=2))


if __name__ == "__main__":
    main()
