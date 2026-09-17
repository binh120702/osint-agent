from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--case',required=True); a=p.parse_args()
root=Path(__file__).resolve().parents[3]; sys.path.insert(0,str(root)); sys.path.insert(0,str(root/'src'))
from dataset.benchmark.loader import load_case
from dataset.benchmark.runner import _report_output
from dataset.benchmark.scoring import score_case
case=load_case(Path(a.case).stem); run=Path(__file__).resolve().parent/'runs'/case.data['case_id']; d=json.loads((run/'io/candidate-result.json').read_text(encoding='utf-8')); report=d['content']
parsed=_report_output(case,report); available=set();
for call in d['tool_calls']: available.update(re.findall(r'\bSRC-[A-Za-z0-9_-]+\b',call.get('result','')))
output={'entities':[],'relations':[],'available_source_references':sorted(available),'source_references':sorted(set(re.findall(r'SRC-[A-Za-z0-9_-]+',report))&available),'report':report,**parsed}
m=score_case(case.data,output)
result={'case_id':case.data['case_id'],'candidate':'OpenOSINT','model':'gpt-5.6-luna','metrics':{'finding_f1':m['key_findings']['f1'],'finding_score':m['key_findings']['score'],'contradiction_grounded_f1':m['contradictions']['grounded_f1'],'reasoning_grounded_score':m['reasoning_quality']['grounded_score'],'report_quality':m['report_quality']['score'],'source_precision':m['source_traceability']['source_precision'],'source_recall':m['source_traceability']['source_recall'],'structured_output_valid':output['structured_output_valid'],'structured_output_complete':output['structured_output_complete']},'full_metrics':m}
(run/'scored-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(result['metrics']))
