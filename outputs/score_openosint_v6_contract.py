from __future__ import annotations
import json, statistics, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'outputs/multi-iteration-runs/openosint-v6-contract-10workers'
rows=[]
for p in sorted(BASE.glob('iteration-*/**/scored-result.json')):
  rel=p.relative_to(BASE)
  iteration=int(next(part.split('-')[-1] for part in rel.parts if part.startswith('iteration-')))
  d=json.loads(p.read_text(encoding='utf8')); m=d['metrics']; rows.append({'iteration':iteration,'case_id':d['case_id'],'artifact':str((p.parent/'io/candidate-result.json').relative_to(ROOT)).replace('\\','/'),'metrics':{'finding_f1':m['finding_f1'],'contradiction_f1':m['contradiction_grounded_f1'],'reasoning':m['reasoning_grounded_score'],'report_quality':m['report_quality'],'source_precision':m['source_precision'],'source_recall':m['source_recall']},'structured_output_valid':bool(m['structured_output_valid'])})
def agg(rs): return {'n_rows':len(rs),'metrics':{k:{'mean':statistics.fmean([r['metrics'][k] for r in rs])} for k in ('finding_f1','contradiction_f1','reasoning','report_quality','source_precision','source_recall')}}
v=[r for r in rows if r['structured_output_valid']]
r={'protocol':'openosint-v6-contract','benchmark_snapshot_sha256':'561e463eac51c71d83b97cf20c706395f8ecb3763fdec6d77715c17da9156bd0','rows':rows,'completed_output':agg(rows),'valid_only':agg(v),'validity_rate':len(v)/len(rows),'terminal_failures':0}
(BASE/'scoring').mkdir(exist_ok=True); (BASE/'scoring/aggregate.json').write_text(json.dumps(r,indent=2)); print(json.dumps(r,indent=2))
