from __future__ import annotations
import argparse, json, os, time
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
p=argparse.ArgumentParser(); p.add_argument('--io',required=True); p.add_argument('--model',required=True); p.add_argument('--max-requests',type=int,default=80); p.add_argument('--timeout',type=int,default=1800); a=p.parse_args()
io=Path(a.io); handled=set(); deadline=time.monotonic()+a.timeout; count=0
client=OpenAI(api_key=os.environ['OPENAI_API_KEY'], base_url=os.getenv('OPENAI_API_BASE_URL','https://api.openai.com/v1'), timeout=180, max_retries=0)
SCHEMA_ALIASES={
 'ResearchQuestion':{
  'required':['research_brief'],
  'alt':{
   'research_brief':['research_brief','research_question','brief','topic','topic_brief','research_topic'],
   'topic':['research_brief','topic','topic_brief','research_topic'],
   'goal':['research_brief','topic','topic_brief','research_topic'],
   'query':['research_brief','topic','topic_brief','research_topic'],
  }
 },
 'ResearchBrief':{
  'required':['research_brief'],
  'alt':{
   'research_brief':['research_brief','research_question','brief','topic','topic_brief','research_topic'],
   'topic':['research_brief','topic','topic_brief','research_topic'],
   'goal':['research_brief','topic','topic_brief','research_topic'],
   'query':['research_brief','topic','topic_brief','research_topic'],
  }
 },
 'ResearchResponse':{
  'required':['summary','key_excerpts'],
  'alt':{
   'summary':['summary','findings','compressed_research','compressed_findings'],
   'key_excerpts':['key_excerpts','excerpts','sources','evidence','summary'],
  }
 },
 'Summary':{
  'required':['summary','key_excerpts'],
  'alt':{
   'summary':['summary','findings','compressed_research','compressed_findings'],
   'key_excerpts':['key_excerpts','excerpts','sources','evidence','summary'],
  }
 },
}
def _best(inline, schema_name):
    schema = SCHEMA_ALIASES.get(schema_name)
    if not schema: return inline
    out = dict(inline)
    for required in schema['required']:
        if required not in out:
            candidates = schema['alt'].get(required, [required])
            for candidate in candidates:
                if candidate in out:
                    out[required] = out[candidate]
                    break
            else:
                # Synthesize a best-effort fallback from the inline text.
                if required == 'research_brief':
                    out[required] = out.get('research_brief') or out.get('research_question') or ' '.join(str(v) for v in out.values() if isinstance(v, str) and len(v) > 5)[:4000]
                elif required == 'summary':
                    out[required] = ' '.join(str(v) for v in out.values() if isinstance(v, str))[:8000]
                elif required == 'key_excerpts':
                    out[required] = out.get('key_excerpts') or out.get('summary') or ''
    return out
while time.monotonic()<deadline:
    for path in sorted(io.glob('request-*.json')):
        if path in handled: continue
        handled.add(path); count += 1; rp=io/(path.name.replace('request','response'))
        try:
            if count > a.max_requests: raise RuntimeError('host request budget exhausted')
            supplied=json.loads(path.read_text(encoding='utf8'))
            schema_name = supplied.get('schema_name') or (supplied.get('response_format') or {}).get('json_schema', {}).get('name', '')
            kwargs={'model':a.model, 'messages':supplied.get('messages',[]), 'temperature':0}
            for key in ('max_tokens','tools','tool_choice','response_format'):
                if key in supplied: kwargs[key]=supplied[key]
            response=client.chat.completions.create(**kwargs)
            data=response.model_dump(); first=data['choices'][0]['message']; content=first.get('content') or ''
            if schema_name:
                try: inline=json.loads(content)
                except Exception: inline=None
                if isinstance(inline, dict):
                    content=json.dumps(_best(inline, schema_name), ensure_ascii=False)
                elif schema_name in ('ResearchQuestion', 'ResearchBrief'):
                    content=json.dumps({'research_brief': content}, ensure_ascii=False)
                elif schema_name in ('ResearchResponse', 'Summary'):
                    content=json.dumps({'summary': content, 'key_excerpts': content}, ensure_ascii=False)
            first['content']=content; first['tool_calls']=first.get('tool_calls') or []
            data['choices'][0]['message']=first; rp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf8')
        except Exception as e:
            rp.write_text(json.dumps({'bridge_error':f'{type(e).__name__}: {e}'}),encoding='utf8')
    if (io/'candidate-result.json').exists(): raise SystemExit(0)
    time.sleep(.1)
raise SystemExit('host bridge timeout')
