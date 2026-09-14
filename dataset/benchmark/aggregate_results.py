"""Aggregate persisted OSINT benchmark case artifacts.

Usage:
    python -m dataset.benchmark.aggregate_results --input path/to/OSINT-001.json ... \
        --output dataset/results/aggregate.json

Inputs are explicit so historical runs are never silently mixed.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


METRIC_PATHS = {
    "entity_f1": ("entities", "f1"),
    "relation_f1": ("relations", "f1"),
    "finding_f1": ("key_findings", "f1"),
    "contradiction_grounded_f1": ("contradictions", "grounded_f1"),
    "reasoning_grounded_score": ("reasoning_quality", "grounded_score"),
    "report_quality": ("report_quality", "score"),
    "source_precision": ("source_traceability", "source_precision"),
    "source_recall": ("source_traceability", "source_recall"),
}


def _get(mapping: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = mapping
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def aggregate(paths: list[Path]) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for path in paths:
        result = json.loads(path.read_text(encoding="utf-8"))
        metrics = result.get("metrics", {})
        output = result.get("output", {})
        operational = output.get("operational", {})
        row: dict[str, Any] = {
            "case_id": result.get("case_id"),
            "artifact": str(path),
            "run_id": path.parent.parent.name,
            "structured_output_valid": bool(metrics.get("output_validation", {}).get("valid")),
            "structured_output_complete": bool(output.get("structured_output_complete", False)),
            "termination_reason": operational.get("termination_reason"),
            "runtime_failure": operational.get("termination_reason") == "runtime_failure",
            "retrieval_status": metrics.get("retrieval", {}).get("status", "unknown"),
            "metrics": {name: _get(metrics, metric_path) for name, metric_path in METRIC_PATHS.items()},
        }
        cases.append(row)

    cases.sort(key=lambda item: str(item.get("case_id")))
    means: dict[str, float | None] = {}
    for name in METRIC_PATHS:
        values = [row["metrics"][name] for row in cases if isinstance(row["metrics"].get(name), (int, float))]
        means[name] = statistics.mean(values) if values else None

    from collections import Counter
    return {
        "case_count": len(cases),
        "case_ids": [row["case_id"] for row in cases],
        "valid_structured_outputs": sum(row["structured_output_valid"] for row in cases),
        "complete_structured_outputs": sum(row["structured_output_complete"] for row in cases),
        "final_report_terminations": sum(row["termination_reason"] == "final_report" for row in cases),
        "runtime_failures": [row["case_id"] for row in cases if row["runtime_failure"]],
        "retrieval_status_counts": dict(Counter(row["retrieval_status"] for row in cases)),
        "mean_metrics": means,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, help="case result artifact; repeat for each case")
    parser.add_argument("--output", required=True, help="JSON output path")
    args = parser.parse_args()
    paths = [Path(value) for value in args.input]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        parser.error(f"input artifact not found: {', '.join(missing)}")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(aggregate(paths), ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
