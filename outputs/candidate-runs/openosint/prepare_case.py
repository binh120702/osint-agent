"""Prepare one assisted OpenOSINT benchmark case."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from dataset.benchmark.blind import blind_case, blind_prompt

p = argparse.ArgumentParser(); p.add_argument('--case', required=True); a = p.parse_args()
root = Path(__file__).resolve().parents[3]
case_path = root / 'dataset' / 'cases' / a.case
case = json.loads(case_path.read_text(encoding='utf-8'))
public_case = blind_case(case)
case_id = case['case_id']; out = Path(__file__).resolve().parent / 'runs' / case_id
prompt = blind_prompt(public_case)
out.mkdir(parents=True, exist_ok=True); (out/'input').mkdir(exist_ok=True); (out/'io').mkdir(exist_ok=True)
spec = {'case_id': case_id, 'case_sha256': hashlib.sha256(case_path.read_bytes()).hexdigest(), 'model': 'gpt-5.6-luna', 'max_requests': 20, 'sources': [{'source_id': s['source_id'], 'uri': s['uri'], 'raw_text': s.get('raw_text',''), 'content': {'page_title': (s.get('content') or {}).get('page_title', s['source_id'])}} for s in case['sources']], 'prompt': prompt}
(out/'input/case.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8'); print(out)
