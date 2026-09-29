from __future__ import annotations
import argparse,json,os,time
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
p=argparse.ArgumentParser();p.add_argument('--io',required=True);p.add_argument('--model',required=True);p.add_argument('--max-requests',type=int,default=80);p.add_argument('--timeout',type=int,default=1800);a=p.parse_args()
io=Path(a.io); handled=set(); deadline=time.monotonic()+a.timeout; count=0
client=OpenAI(api_key=os.environ['OPENAI_API_KEY'],base_url=os.getenv('OPENAI_API_BASE_URL','https://api.openai.com/v1'),timeout=180,max_retries=0)
while time.monotonic()<deadline:
 for path in sorted(io.glob('request-*.json')):
  if path.name in handled: continue
  handled.add(path.name);count+=1;rp=io/path.name.replace('request-','response-')
  try:
   if count>a.max_requests: raise RuntimeError('host request budget exhausted')
   supplied=json.loads(path.read_text(encoding='utf8'))
   kwargs={k:supplied[k] for k in ('messages',) if k in supplied}
   kwargs.update(model=a.model,temperature=0,max_tokens=4096)
   response=client.chat.completions.create(**kwargs)
   rp.write_text(response.model_dump_json(),encoding='utf8')
  except Exception as e: rp.write_text(json.dumps({'bridge_error':f'{type(e).__name__}: {e}'}),encoding='utf8')
 if (io/'candidate-result.json').exists(): raise SystemExit(0)
 time.sleep(.1)
raise SystemExit('host bridge timeout')
