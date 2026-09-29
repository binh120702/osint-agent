from __future__ import annotations
import hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'src'))
from dataset.benchmark.loader import load_case
from dataset.benchmark.runner import _report_output
from dataset.benchmark.scoring import score_case
RUNS=Path(__file__).parent/'runs'
rows=[]
for p in sorted((RUNS / f'OSINT-{i:03d}' / 'io' / 'candidate-result.json' for i in range(1, 11) if (RUNS / f'OSINT-{i:03d}' / 'io' / 'candidate-result.json').exists())):
 d=json.loads(p.read_text(encoding='utf8')); cid=d['case_id']; c=load_case(cid); report=d.get('report',''); parsed=_report_output(c,report)
 available={s['source_id'] for s in c.data.get('sources',[])}
 refs=sorted(set(re.findall(r'SRC-[A-Za-z0-9_-]+',report)) & available)
 out={'entities':[],'relations':[],'available_source_references':sorted(available),'source_references':refs,'report':report,**parsed}
 m=score_case(c.data,out)
 metrics={'finding_f1':m['key_findings']['f1'],'contradiction_grounded_f1':m['contradictions']['grounded_f1'],'reasoning_grounded_score':m['reasoning_quality']['grounded_score'],'report_quality':m['report_quality']['score'],'source_precision':m['source_traceability']['source_precision'],'source_recall':m['source_traceability']['source_recall'],'entity_f1':'not_applicable','relation_f1':'not_applicable'}
 result={'case_id':cid,'candidate':'assafelovic/gpt-researcher','adaptation':'native-workflow-snapshot-retriever-file-inference-v1','artifact':str(p.relative_to(ROOT)).replace('\\','/'),'artifact_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'output_summary':{'source_references':refs,'key_findings':parsed['key_findings'],'claims':parsed['claims'],'reasoning_steps':parsed['reasoning_steps'],'contradictions':parsed['contradictions'],'structured_output_valid':parsed['structured_output_valid'],'structured_output_complete':parsed['structured_output_complete'],'structured_output_errors':parsed['structured_output_errors']},'metrics':metrics}
 (p.parent/'scored-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8'); rows.append(result)
keys=list(rows[0]['metrics']) if rows else []
def avg(k):
 vals=[r['metrics'][k] for r in rows if isinstance(r['metrics'][k],(int,float))]; return sum(vals)/len(vals) if vals else 'not_applicable'
aggregate={'candidate':'assafelovic/gpt-researcher','adaptation':'native-workflow-snapshot-retriever-file-inference-v1','cases_completed':len(rows),'cases_total':10,'valid_structured_outputs':sum(bool(r['output_summary']['structured_output_valid']) for r in rows),'complete_structured_outputs':sum(bool(r['output_summary']['structured_output_complete']) for r in rows),'metrics':{k:avg(k) for k in keys},'case_results':[r['case_id'] for r in rows]}
(RUNS/'scored-aggregate.json').write_text(json.dumps(aggregate,ensure_ascii=False,indent=2),encoding='utf8'); print(json.dumps(aggregate,indent=2))
