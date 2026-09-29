"""Common contract-track scorer for baseline v15 and OpenOSINT v6.

Selects one terminal artifact per (iteration, case), applies identical parsing,
adaptation, validity, and metric extraction, while retaining failure counts.
"""
from __future__ import annotations
import hashlib, json, re, statistics
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from dataset.benchmark.loader import load_case
from dataset.benchmark.runner import _report_output
from dataset.benchmark.report_adapter import adapt_report_output
from dataset.benchmark.scoring import score_case
SNAP='561e463eac51c71d83b97cf20c706395f8ecb3763fdec6d77715c17da9156bd0'
MET={'finding_f1':('key_findings','f1'),'contradiction_f1':('contradictions','grounded_f1'),'reasoning':('reasoning_quality','grounded_score'),'report_quality':('report_quality','score'),'source_precision':('source_traceability','source_precision'),'source_recall':('source_traceability','source_recall')}

def baseline_rows(base):
 out=[]
 for p in sorted(Path(base).glob('baseline/iteration-*/OSINT-*/candidate-result.json')):
  iteration=int(next(x.split('-')[-1] for x in p.parts if x.startswith('iteration-'))); cid=p.parent.name
  out.append((iteration,cid,p,p))
 return out

def v6_rows(base):
 # Group all preserved candidate artifacts; highest attempt is the terminal rerun.
 groups={}
 for p in sorted(Path(base).glob('iteration-*/OSINT-*/attempt-*/io/candidate-result.json')):
  iteration=int(next(x.split('-')[-1] for x in p.parts if x.startswith('iteration-'))); cid=p.parents[2].name
  key=(iteration,cid); attempt=int(p.parents[1].name.split('-')[-1])
  if key not in groups or attempt>groups[key][0]: groups[key]=(attempt,p)
 return [(i,c,p,p) for (i,c),(_,p) in sorted(groups.items())]

def external_rows(base):
 out=[]
 for p in sorted(Path(base).glob('runs/OSINT-*/io/candidate-result.json')):
  cid=p.parent.parent.name
  if re.fullmatch(r'OSINT-\d{3}',cid): out.append((1,cid,p,p))
 return out

def score_one(cid,p,kind):
 case=load_case(cid); raw=json.loads(p.read_text(encoding='utf8'))
 if kind=='baseline':
  output=dict(raw.get('output',{})); output.update(_report_output(case,raw.get('trace',{}).get('final_report','')))
 else:
  report=raw.get('report',raw.get('content','')); parsed=_report_output(case,report)
  available={s['source_id'] for s in case.data.get('sources',[])}
  refs=sorted(set(re.findall(r'\bSRC-[A-Za-z0-9_-]+\b',report)) & available)
  output={'entities':[],'relations':[],'available_source_references':sorted(available),'source_references':refs,'report':report,**parsed}
 output=adapt_report_output(case,output); metrics=score_case(case.data,output)
 return {'iteration':1 if kind in ('gpt-researcher','open-deep-research') else int(next(x.split('-')[-1] for x in p.parts if x.startswith('iteration-'))),'case_id':cid,'artifact':p.relative_to(ROOT).as_posix(),'artifact_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'structured_output_valid':bool(output.get('structured_output_valid')),'structured_output_errors':output.get('structured_output_errors',[]),'metrics':{k:metrics[a][b] for k,(a,b) in MET.items()}}

def aggregate(rows):
 def agg(rs): return {'n_rows':len(rs),'metrics':{k:{'mean':statistics.fmean([r['metrics'][k] for r in rs]) if rs else None} for k in MET}}
 valid=[r for r in rows if r['structured_output_valid']]
 return {'completed_output':agg(rows),'valid_only':agg(valid),'validity_rate':len(valid)/len(rows) if rows else 0}

def run(kind,base):
 pairs=(baseline_rows(base) if kind=='baseline' else v6_rows(base) if kind=='openosint-v6' else external_rows(base)); rows=[score_one(cid,p,kind) for _,cid,p,_ in pairs]
 result={'protocol':'common-contract-track-v1','candidate':kind,'benchmark_snapshot_sha256':SNAP,'rows':rows,**aggregate(rows)}
 out=Path(base)/'scoring'; out.mkdir(parents=True,exist_ok=True); (out/'common-contract-aggregate.json').write_text(json.dumps(result,indent=2),encoding='utf8'); return result
if __name__=='__main__':
 targets=[('baseline',ROOT/'outputs/multi-iteration-runs/baseline-v15-structured-contract'),('openosint-v6',ROOT/'outputs/multi-iteration-runs/openosint-v6-contract-10workers'),('gpt-researcher',ROOT/'outputs/candidate-runs/gpt-researcher'),('open-deep-research',ROOT/'outputs/candidate-runs/open-deep-research')]
 results=[run(k,p) for k,p in targets]
 for x in results: print(x['candidate'],json.dumps({k:{m:(round(z['mean'],4) if z['mean'] is not None else None) for m,z in q['metrics'].items()} for k,q in x.items() if k in ('completed_output','valid_only')},indent=2))
