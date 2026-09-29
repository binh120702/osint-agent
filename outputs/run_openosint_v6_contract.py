"""Run a preserved-source OpenOSINT v6 contract evaluation with bounded parallelism.

This controller writes only to outputs/multi-iteration-runs/openosint-v6-contract.
It deliberately invokes the existing isolated case runner so the candidate source,
container, bridge, and report adapter remain unchanged from the preserved protocol.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "outputs" / "candidate-runs" / "openosint"
BASE = ROOT / "outputs" / "multi-iteration-runs" / "openosint-v6-contract-10workers"
SNAPSHOT = ROOT / "dataset" / "results" / "aggregate-20260914.json"
SOURCE_REVISION = "1ab71de6cdb1e6f5423c46e154b7a838b233aae2"
IMAGE = "osint-bench-openosint:1ab71de"
MODEL = "gpt-5.6-luna"
METRICS = (
    "finding_f1", "contradiction_grounded_f1", "reasoning_grounded_score",
    "report_quality", "source_precision", "source_recall",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_input(case_path: Path, run: Path) -> None:
    case_id = json.loads(case_path.read_text(encoding="utf-8"))["case_id"]
    source_run = CANDIDATE / "runs" / case_id
    if not source_run.exists():
        raise FileNotFoundError(f"missing prepared input: {source_run}")
    (run / "input").mkdir(parents=True, exist_ok=False)
    (run / "io").mkdir()
    shutil.copy2(source_run / "input" / "case.json", run / "input" / "case.json")


def score(run: Path, case_path: Path) -> dict:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    from dataset.benchmark.loader import load_case
    from dataset.benchmark.runner import _report_output
    from dataset.benchmark.scoring import score_case

    case = load_case(case_path.stem)
    candidate = json.loads((run / "io" / "candidate-result.json").read_text(encoding="utf-8"))
    report = candidate["content"]
    parsed = _report_output(case, report)
    available: set[str] = set()
    for call in candidate.get("tool_calls", []):
        available.update(re.findall(r"\bSRC-[A-Za-z0-9_-]+\b", call.get("result", "")))
    output = {
        "entities": [],
        "relations": [],
        "available_source_references": sorted(available),
        "source_references": sorted(set(re.findall(r"SRC-[A-Za-z0-9_-]+", report)) & available),
        "report": report,
        **parsed,
    }
    metrics = score_case(case.data, output)
    return {
        "case_id": case.data["case_id"],
        "candidate": "OpenOSINT",
        "model": MODEL,
        "metrics": {
            "finding_f1": metrics["key_findings"]["f1"],
            "contradiction_grounded_f1": metrics["contradictions"]["grounded_f1"],
            "reasoning_grounded_score": metrics["reasoning_quality"]["grounded_score"],
            "report_quality": metrics["report_quality"]["score"],
            "source_precision": metrics["source_traceability"]["source_precision"],
            "source_recall": metrics["source_traceability"]["source_recall"],
            "structured_output_valid": output["structured_output_valid"],
            "structured_output_complete": output["structured_output_complete"],
        },
        "full_metrics": metrics,
    }


def run_case(iteration: int, case_path: Path, max_requests: int, timeout: int, retry_timeout: int) -> dict:
    case_id = json.loads(case_path.read_text(encoding="utf-8"))["case_id"]
    case_root = BASE / f"iteration-{iteration:02d}" / case_id
    case_root.mkdir(parents=True, exist_ok=True)
    attempts = []
    for attempt, limit in ((1, timeout), (2, retry_timeout)):
        attempt_number = attempt
        run = case_root / f"attempt-{attempt_number:02d}"
        while run.exists():
            attempt_number += 1
            run = case_root / f"attempt-{attempt_number:02d}"
        prepare_input(case_path, run)
        started = time.time()
        command = [sys.executable, str(CANDIDATE / "run_pilot.py"), "--run-dir", str(run),
                   "--timeout", str(limit), "--max-requests", str(max_requests),
                   "--bridge-python", str(ROOT / "src" / ".venv" / "Scripts" / "python.exe"),
                   "--bridge-script", str(CANDIDATE / "inference_bridge_retry_long.py")]
        stdout = run / "controller.stdout.log"
        stderr = run / "controller.stderr.log"
        with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
            proc = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err, timeout=limit + 60)
        manifest_path = run / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        status = manifest.get("status", "failed")
        event = {
            "attempt": attempt,
            "status": status,
            "exit_code": proc.returncode,
            "duration_seconds": round(time.time() - started, 3),
            "run": run.relative_to(ROOT).as_posix(),
        }
        if attempt == 2:
            event["retry_of"] = 1
        attempts.append(event)
        if status == "completed":
            artifact = run / "io" / "candidate-result.json"
            scored = score(run, case_path)
            (run / "scored-result.json").write_text(json.dumps(scored, indent=2), encoding="utf-8")
            return {"case_id": case_id, "iteration": iteration, "attempts": attempts,
                    "terminal_status": "completed", "artifact": artifact.relative_to(ROOT).as_posix(),
                    "artifact_sha256": sha256(artifact), "score": scored}
        if status != "timeout":
            break
    return {"case_id": case_id, "iteration": iteration, "attempts": attempts,
            "terminal_status": attempts[-1]["status"] if attempts else "failed", "score": None}


def aggregate(rows: list[dict]) -> dict:
    completed = [r for r in rows if r["terminal_status"] == "completed" and r.get("score")]
    valid = [r for r in completed if r["score"]["metrics"]["structured_output_valid"]]
    result = {"completed": len(completed), "valid": len(valid), "total": len(rows), "metrics": {}}
    for metric in METRICS:
        result["metrics"][metric] = {}
        for view, selected in (("completed", completed), ("valid_only", valid)):
            values = [r["score"]["metrics"][metric] for r in selected]
            result["metrics"][metric][view] = {
                "mean": mean(values) if values else None,
                "population_sd": pstdev(values) if len(values) > 1 else None,
                "n": len(values),
            }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--start-iteration", type=int, default=1)
    parser.add_argument("--case", default=None)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--retry-timeout", type=int, default=2400)
    parser.add_argument("--max-requests", type=int, default=20)
    args = parser.parse_args()
    cases = sorted((ROOT / "dataset" / "cases").glob("case_*.json"))
    if len(cases) != 10:
        raise SystemExit(f"expected 10 benchmark cases, found {len(cases)}")
    bridge_python = ROOT / "src" / ".venv" / "Scripts" / "python.exe"
    if not bridge_python.exists():
        raise SystemExit(f"missing bridge interpreter: {bridge_python}")
    if sha256(SNAPSHOT) != "561e463eac51c71d83b97cf20c706395f8ecb3763fdec6d77715c17da9156bd0":
        raise SystemExit("immutable benchmark snapshot hash mismatch")
    BASE.mkdir(parents=True, exist_ok=True)
    controller = {"protocol": "openosint-v6-contract", "started_at": now(),
                  "benchmark_snapshot": SNAPSHOT.relative_to(ROOT).as_posix(),
                  "benchmark_snapshot_sha256": sha256(SNAPSHOT), "source_revision": SOURCE_REVISION,
                  "image": IMAGE, "model": MODEL, "iterations": args.iterations,
                  "cases": [json.loads(p.read_text(encoding="utf-8"))["case_id"] for p in cases],
                  "workers": args.workers, "timeout_seconds": args.timeout,
                  "retry_timeout_seconds": args.retry_timeout, "max_requests": args.max_requests,
                  "bridge_python": bridge_python.relative_to(ROOT).as_posix(), "rows": []}
    state = BASE / "parallel-controller.json"
    state.write_text(json.dumps(controller, indent=2), encoding="utf-8")
    jobs = [(i, p) for i in range(args.start_iteration, args.start_iteration + args.iterations) for p in cases if args.case is None or json.loads(p.read_text(encoding="utf-8"))["case_id"] == args.case]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_case, i, p, args.max_requests, args.timeout, args.retry_timeout): (i, p) for i, p in jobs}
        for future in as_completed(futures):
            row = future.result()
            controller["rows"].append(row)
            controller["updated_at"] = now()
            state.write_text(json.dumps(controller, indent=2), encoding="utf-8")
            print(json.dumps({k: row[k] for k in ("iteration", "case_id", "terminal_status")}), flush=True)
    controller["rows"].sort(key=lambda r: (r["iteration"], r["case_id"]))
    controller["aggregate"] = aggregate(controller["rows"])
    controller["finished_at"] = now()
    state.write_text(json.dumps(controller, indent=2), encoding="utf-8")
    (BASE / "all-case-scores.jsonl").write_text("\n".join(json.dumps(r) for r in controller["rows"]) + "\n", encoding="utf-8")
    (BASE / "aggregate.json").write_text(json.dumps(controller["aggregate"], indent=2), encoding="utf-8")
    return 0 if all(r["terminal_status"] == "completed" for r in controller["rows"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
