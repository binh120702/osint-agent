from __future__ import annotations
import json,re
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
sys.path.insert(0,'src')
from dataset.benchmark.loader import load_case
from dataset.benchmark.runner import _report_output
from dataset.benchmark.scoring import score_case
run=Path('outputs/candidate-runs/openosint/runs/OSINT-001-final')
case=load_case('case_001')
d=json.loads((run/'io/candidate-result.json').read_text(encoding='utf-8'))
report=d['content']; parsed=_report_output(case,report)
available=set()
for call in d['tool_calls']:
 available.update(re.findall(r'\bSRC-[A-Za-z0-9_-]+\b',call.get('result','')))
output={'entities':[], 'relations':[], 'available_source_references':sorted(available), 'source_references':sorted(set(re.findall(r'SRC-[A-Za-z0-9_-]+',report)) & available), 'report':report, **parsed}
metrics=score_case(case.data,output)
result={'candidate':'OpenOSINT','run_dir':str(run),'model':'gpt-5.6-luna','adaptation':'snapshot-tools-file-inference-transport-v1','note':'Entity/relation scores are not applicable to this adapter: upstream OpenOSINT has no integration with our knowledge-agent graph contract. Findings/reasoning/contradiction/report metrics are parsed with the existing deterministic scorer.','output_summary':{k:output[k] for k in ['source_references','available_source_references','key_findings','claims','reasoning_steps','reasoning_step_details','contradictions','structured_output','structured_output_valid','structured_output_complete','missing_structured_sections','structured_output_errors']},'metrics':metrics}
(run/'scored-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'finding_f1':metrics['key_findings']['f1'],'finding_score':metrics['key_findings']['score'],'contradiction_grounded_f1':metrics['contradictions']['grounded_f1'],'reasoning_grounded_score':metrics['reasoning_quality']['grounded_score'],'report_quality':metrics['report_quality'],'traceability':metrics['source_traceability'],'structured_valid':output['structured_output_valid'],'structured_complete':output['structured_output_complete']},ensure_ascii=False,indent=2))
