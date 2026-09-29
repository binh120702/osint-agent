from __future__ import annotations
import argparse, json, os, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
CASES = [f"OSINT-{i:03d}" for i in range(1, 11)]
p = argparse.ArgumentParser()
p.add_argument("--model", required=True)
p.add_argument("--max-requests", type=int, default=40)
p.add_argument("--timeout", type=int, default=1200)
a = p.parse_args()

root = Path(__file__).parent / "runs"
root.mkdir(exist_ok=True)
rows = []

for cid in CASES:
    run_dir = root / cid
    io = run_dir / "io"
    io.mkdir(parents=True, exist_ok=True)
    start = time.time()
    cmd = [sys.executable, str(Path(__file__).parent / "run_case.py"), cid, "--io", str(io), "--model", a.model, "--max-requests", str(a.max_requests)]
    bridge_cmd = [sys.executable, str(Path(__file__).parent / "inference_bridge.py"), "--io", str(io), "--model", a.model, "--max-requests", str(a.max_requests), "--timeout", str(a.timeout)]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    bridge = subprocess.Popen(bridge_cmd, cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=a.timeout)
        (run_dir / "candidate.log").write_text(proc.stdout + "\n" + proc.stderr, encoding="utf8")
    except Exception as exc:
        proc = None
        (run_dir / "candidate.log").write_text(f"{type(exc).__name__}: {exc}", encoding="utf8")
    finally:
        bridge.terminate()
        try:
            bridge.wait(timeout=10)
        except subprocess.TimeoutExpired:
            bridge.kill()
        (run_dir / "bridge.log").write_text((bridge.stdout.read() if bridge.stdout else ""), encoding="utf8")
    result = io / "candidate-result.json"
    status = "completed" if result.exists() else "failed"
    row = {
        "case_id": cid,
        "status": status,
        "exit_code": None if proc is None else proc.returncode,
        "duration_seconds": time.time() - start,
        "artifact": str(result.relative_to(ROOT)).replace("\\", "/") if result.exists() else None,
    }
    if result.exists():
        import hashlib
        row["sha256"] = hashlib.sha256(result.read_bytes()).hexdigest()
    rows.append(row)
    print(json.dumps(row), flush=True)

manifest = {
    "candidate": "langchain-ai/open_deep_research",
    "source_revision": (Path(__file__).parent / "source-revision.txt").read_text().strip(),
    "adaptation": "native-langgraph-snapshot-search-file-inference-v1",
    "model": a.model,
    "max_requests": a.max_requests,
    "cases": rows,
    "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
(root / "all-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")
