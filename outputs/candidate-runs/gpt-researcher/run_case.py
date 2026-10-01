from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(Path(__file__).parent))
from dataset.benchmark.loader import load_case
from dataset.benchmark.blind import blind_case
from adapter import run
p=argparse.ArgumentParser(); p.add_argument('case_id'); p.add_argument('--io',required=True); p.add_argument('--model',required=True); p.add_argument('--max-requests',type=int,default=80); a=p.parse_args()
case=blind_case(load_case(a.case_id).data)
# Keep the native context-manager path, but avoid network-backed embedding compression
# for immutable benchmark snapshots; this is a declared replay boundary.
os.environ['COMPRESSION_THRESHOLD'] = str(max(10_000_000, sum(len(s.get('raw_text','')) for s in case.get('sources', [])) + 1))
os.environ['MAX_SEARCH_RESULTS_PER_QUERY'] = str(max(10, len(case.get('sources', []))))
io=Path(a.io); io.mkdir(parents=True,exist_ok=True)
(io/'input-case.json').write_text(json.dumps(case,ensure_ascii=False,indent=2),encoding='utf8')
run(case,io,a.model,a.max_requests)
