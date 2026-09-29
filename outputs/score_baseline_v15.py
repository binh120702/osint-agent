from __future__ import annotations
import hashlib,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from dataset.benchmark.loader import load_case
from dataset.benchmark.runner import _report_output
from dataset.benchmark.report_adapter import adapt_report_output
from dataset.benchmark.scoring import score_case
BASE=ROOT/'outputs/multi-iteration-runs/baseline-v15-structured-contract/baseline'; OUT=BASE.parent/'scoring'; OUT.mkdir(parents=True,exist_ok=True)
MET={'finding_f1':('key_findings','f1'),'contradiction_f1':('contradictions','grounded_f1'),'reasoning':('reasoning_quality','grounded_score'),'report_quality':('report_quality','score'),'source_precision':('source_traceability','source_precision'),'source_recall':('source_traceability','source_recall')}
rows=[]
for iteration_dir in sorted(BASE.glob('iteration-*')):
 for p in sorted(iteration_dir.glob('OSINT-*/candidate-result.json')):
  cid=p.parent.name; case=load_case(cid); raw=json.loads(p.read_text(encoding='utf8')); output=dict(raw.get('output',{})); output.update(_report_output(case,raw.get('trace',{}).get('final_report',''))); output=adapt_report_output(case,output); m=score_case(case.data,output); rows.append({'iteration':int(iteration_dir.name.split('-')[-1]),'case_id':cid,'artifact':str(p.relative_to(ROOT)).replace('\\','/'),'artifact_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'structured_output_valid':bool(output.get('structured_output_valid')),'structured_output_errors':output.get('structured_output_errors',[]),'metrics':{k:m[a][b] for k,(a,b) in MET.items()}})
def agg(sel):return {'n_rows':len(sel),'metrics':{k:{'mean':statistics.fmean([r['metrics'][k] for r in sel]) if sel else None} for k in MET}}
valid=[r for r in rows if r['structured_output_valid']]
result={'protocol':'baseline-v15-structured-contract','benchmark_snapshot_sha256':'561e463eac51c71d83b97cf20c706395f8ecb3763fdec6d77715c17da9156bd0','rows':rows,'completed_output':agg(rows),'valid_only':agg(valid),'validity_rate':len(valid)/len(rows) if rows else 0,'terminal_failures':0}
(OUT/'aggregate.json').write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))
