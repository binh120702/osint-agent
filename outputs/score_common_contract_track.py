"""Common contract-track scorer for baseline v15 and OpenOSINT v6.

Selects one terminal artifact per (iteration, case), applies identical parsing,
adaptation, validity, and metric extraction, while retaining failure counts.
"""
from __future__ import annotations
import hashlib, json, re, statistics, time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

def blind_rows(base, approach):
    root = Path(base) / approach
    out = []
    # Manifests are authoritative for terminal status and retry selection.
    for manifest_path in sorted(root.glob('iteration-*/manifest.json')):
        manifest = json.loads(manifest_path.read_text(encoding='utf8'))
        for row in manifest.get('cases', []):
            if row.get('terminal_status') != 'completed' or not row.get('artifact'):
                continue
            artifact = Path(row['artifact'])
            p = artifact if artifact.is_absolute() else (ROOT / artifact)
            if not p.exists():
                # Standalone reruns often retain repository-relative artifact
                # paths whose root is the selected run directory.
                candidate = Path(base) / 'baseline' / f"iteration-{int(row['iteration']):02d}" / row['case_id'] / 'candidate-result.json'
                if candidate.exists():
                    p = candidate
            if p.exists():
                out.append((int(row['iteration']), row['case_id'], p, p))
    return sorted({(i, c): (i, c, p, q) for i, c, p, q in out}.values())

def blind_status_summary(base, approach):
    counts = {}
    for manifest_path in sorted((Path(base) / approach).glob('iteration-*/manifest.json')):
        manifest = json.loads(manifest_path.read_text(encoding='utf8'))
        for row in manifest.get('cases', []):
            status = row.get('terminal_status', 'unknown')
            counts[status] = counts.get(status, 0) + 1
    return counts


def score_one(cid,p,kind, blind=False, report_first=False):
 case=load_case(cid); raw=json.loads(p.read_text(encoding='utf8'))
 validation_mode = 'blind' if blind else 'assisted'
 if kind=='baseline':
  if report_first:
   report=raw.get('trace',{}).get('final_report', '')
   parsed=_report_output(case,report, validation_mode=validation_mode)
   available={s['source_id'] for s in case.data.get('sources',[])}
   refs=sorted(set(re.findall(r'\bSRC-[A-Za-z0-9_-]+\b',report)) & available)
   output={'entities':[],'relations':[],'available_source_references':sorted(available),'source_references':refs,'report':report,**parsed}
  else:
   output=dict(raw.get('output',{}))
   parsed=_report_output(case,raw.get('trace',{}).get('final_report',''), validation_mode=validation_mode)
   # Baseline candidate-result artifacts already contain structured reasoning
   # details. Do not replace them with an empty parse when the human-readable
   # final report omits the structured payload.
   for key, value in parsed.items():
    if key not in output or value not in (None, '', [], {}):
     output[key] = value
 else:
  report=raw.get('report',raw.get('content','')); parsed=_report_output(case,report, validation_mode=validation_mode)
  available={s['source_id'] for s in case.data.get('sources',[])}
  refs=sorted(set(re.findall(r'\bSRC-[A-Za-z0-9_-]+\b',report)) & available)
  output={'entities':[],'relations':[],'available_source_references':sorted(available),'source_references':refs,'report':report,**parsed}
 output=adapt_report_output(case,output, validation_mode=validation_mode); metrics=score_case(case.data,output, blind=blind)
 return {'iteration':1 if kind in ('gpt-researcher','open-deep-research') else int(next(x.split('-')[-1] for x in p.parts if x.startswith('iteration-'))),'case_id':cid,'artifact':p.relative_to(ROOT).as_posix(),'artifact_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'structured_output_valid':bool(output.get('structured_output_valid')),'structured_output_errors':output.get('structured_output_errors',[]),'metrics':{k:metrics[a][b] for k,(a,b) in MET.items()}}

def aggregate(rows):
 def agg(rs): return {'n_rows':len(rs),'metrics':{k:{'mean':statistics.fmean([r['metrics'][k] for r in rs]) if rs else None} for k in MET}}
 valid=[r for r in rows if r['structured_output_valid']]
 return {'completed_output':agg(rows),'valid_only':agg(valid),'validity_rate':len(valid)/len(rows) if rows else 0}

def run(kind,base, report_first=False, parallel=1, blind_override=False):
 pairs=(blind_rows(base, kind) if kind in {'baseline','openosint','gpt-researcher','open-deep-research'} and Path(base, kind).exists() else baseline_rows(base) if kind=='baseline' else v6_rows(base) if kind=='openosint-v6' else external_rows(base))
 score_kind = 'baseline' if kind == 'baseline' else 'external'
 def one(item):
  _, cid, p, _ = item
  return score_one(cid,p,score_kind, blind=(blind_override or Path(base).name.startswith('blind-track-')), report_first=report_first)
 total = len(pairs)
 print(f"[{kind}] scoring {total} outputs with parallel={min(parallel, total) if total else 0}", flush=True)
 started = time.time()
 rows = []
 if parallel > 1 and len(pairs) > 1:
  with ThreadPoolExecutor(max_workers=min(parallel, len(pairs))) as pool:
   futures = {pool.submit(one, item): item for item in pairs}
   for done, future in enumerate(as_completed(futures), 1):
    row = future.result(); rows.append(row)
    print(f"[{kind}] progress {done}/{total}: iteration={row['iteration']} case={row['case_id']} elapsed={time.time()-started:.1f}s", flush=True)
 else:
  for done, item in enumerate(pairs, 1):
   row = one(item); rows.append(row)
   print(f"[{kind}] progress {done}/{total}: iteration={row['iteration']} case={row['case_id']} elapsed={time.time()-started:.1f}s", flush=True)
 rows.sort(key=lambda r: (r['iteration'], r['case_id']))
 print(f"[{kind}] scoring complete in {time.time()-started:.1f}s", flush=True)
 result={'protocol':'common-contract-track-v2-blind-aware' if Path(base).name == 'blind-track-v2' else 'common-contract-track-v1','candidate':kind,'benchmark_snapshot_sha256':SNAP,'rows':rows,**aggregate(rows)}
 if Path(base).name == 'blind-track-v2':
  result['terminal_status_counts'] = blind_status_summary(base, kind)
  result['intended_rows'] = sum(result['terminal_status_counts'].values())
  result['completed_rows'] = result['terminal_status_counts'].get('completed', 0)
 out=Path(base)/'scoring'; out.mkdir(parents=True,exist_ok=True)
 (out/f'common-contract-aggregate-{kind}.json').write_text(json.dumps(result,indent=2),encoding='utf8')
 (out/'common-contract-aggregate.json').write_text(json.dumps(result,indent=2),encoding='utf8')
 return result
if __name__=='__main__':
 import argparse
 parser = argparse.ArgumentParser()
 parser.add_argument('--base-dir', default=None, help='Blind run root containing baseline, openosint, gpt-researcher, and open-deep-research')
 parser.add_argument('--report-first', action='store_true', help='score baseline final reports using the same parsed-report path as external candidates')
 parser.add_argument('--parallel', type=int, default=1, help='number of candidate outputs to score concurrently')
 parser.add_argument('--blind', action='store_true', help='treat the selected run directory as a blind evaluation even if its name is not blind-track-*')
 args = parser.parse_args()
 if args.base_dir:
  root_dir = (ROOT / args.base_dir).resolve() if not Path(args.base_dir).is_absolute() else Path(args.base_dir)
  targets=[('baseline',root_dir),('openosint',root_dir),('gpt-researcher',root_dir),('open-deep-research',root_dir)]
 else:
  targets=[('baseline',ROOT/'outputs/multi-iteration-runs/baseline-v15-structured-contract'),('openosint-v6',ROOT/'outputs/multi-iteration-runs/openosint-v6-contract-10workers'),('gpt-researcher',ROOT/'outputs/candidate-runs/gpt-researcher'),('open-deep-research',ROOT/'outputs/candidate-runs/open-deep-research')]
 if args.parallel < 1:
  parser.error('--parallel must be at least 1')
 results=[run(k,p, report_first=args.report_first and k == 'baseline', parallel=args.parallel, blind_override=args.blind) for k,p in targets]
if args.base_dir:
 combined = {'protocol': 'common-contract-track-v2-blind-aware', 'benchmark_snapshot_sha256': SNAP,
             'candidates': {result['candidate']: {key: value for key, value in result.items() if key != 'rows'}
                           for result in results}}
 (root_dir/'scoring'/'common-contract-comparison.json').write_text(json.dumps(combined, indent=2), encoding='utf8')
 for x in results: print(x['candidate'],json.dumps({k:{m:(round(z['mean'],4) if z['mean'] is not None else None) for m,z in q['metrics'].items()} for k,q in x.items() if k in ('completed_output','valid_only')},indent=2))
