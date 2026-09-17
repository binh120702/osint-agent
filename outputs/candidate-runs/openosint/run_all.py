"""Run all ten OpenOSINT snapshot pilots sequentially and score them."""
from __future__ import annotations
import argparse, json, subprocess, sys, time
from pathlib import Path
root=Path(__file__).resolve().parent
repo=root.parents[2]
cases=sorted((repo/'dataset/cases').glob('case_*.json'))
p=argparse.ArgumentParser(); p.add_argument('--start',type=int,default=1); p.add_argument('--stop',type=int,default=10); a=p.parse_args()
rows=[]
for path in cases:
 n=int(path.stem.split('_')[1])
 if not a.start<=n<=a.stop: continue
 cid=f'OSINT-{n:03d}'; run=root/'runs'/cid
 if not (run/'input/case.json').exists(): subprocess.run([sys.executable,str(root/'prepare_case.py'),'--case',path.name],check=True,cwd=repo)
 started=time.time()
 proc=subprocess.run([sys.executable,str(root/'run_pilot.py'),'--run-dir',cid],cwd=repo,timeout=1000)
 row={'case_id':cid,'status':'completed' if proc.returncode==0 else 'failed','elapsed_seconds':round(time.time()-started,2)}
 try:
  score=subprocess.run(['uv','run','--project','src','python',str(root/'score_pilot_case.py'),'--case',path.name],cwd=repo,capture_output=True,text=True,timeout=180)
  row['score_status']='completed' if score.returncode==0 else 'failed'; row['score']=json.loads(score.stdout)
 except Exception as e: row['score_status']='failed'; row['score_error']=f'{type(e).__name__}: {e}'
 rows.append(row); (root/'runs'/ 'all-progress.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
print(json.dumps(rows,indent=2))
