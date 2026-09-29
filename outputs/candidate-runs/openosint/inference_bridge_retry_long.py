"""Credential-holding host bridge for one bounded OpenOSINT pilot.

The untrusted candidate container never receives API credentials or general
network access. It exchanges JSON files with this bridge.
"""
from __future__ import annotations
import argparse
import json
import os
import time
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

p = argparse.ArgumentParser()
p.add_argument('--io', required=True)
p.add_argument('--model', required=True)
p.add_argument('--max-requests', type=int, default=20)
p.add_argument('--timeout', type=int, default=900)
a = p.parse_args()
io = Path(a.io)
client = OpenAI(api_key=os.environ['OPENAI_API_KEY'], base_url=os.getenv('OPENAI_API_BASE_URL', 'https://api.openai.com/v1'), timeout=360, max_retries=0)
handled = set()
deadline = time.monotonic() + a.timeout
count = 0
while time.monotonic() < deadline:
    result = io / 'candidate-result.json'
    if result.exists():
        raise SystemExit(0)
    requests = sorted(io.glob('request-*.json'))
    for path in requests:
        if path.name in handled:
            continue
        handled.add(path.name)
        count += 1
        response_path = io / path.name.replace('request-', 'response-')
        if count > a.max_requests:
            response_path.write_text(json.dumps({'bridge_error': 'host request budget exhausted'}))
            continue
        try:
            if path.stat().st_size > 2_000_000:
                raise ValueError('request exceeds byte limit')
            supplied = json.loads(path.read_text(encoding='utf-8'))
            kwargs = {key: supplied[key] for key in ('messages', 'tools') if key in supplied}
            if not isinstance(kwargs.get('messages'), list):
                raise ValueError('messages must be a list')
            allowed = {'engine_search_tool', 'get_url_content'}
            if any(t.get('type') != 'function' or t.get('function', {}).get('name') not in allowed for t in kwargs.get('tools', [])):
                raise ValueError('unapproved tool schema')
            if any(not isinstance(m.get('content'), (str, type(None))) for m in kwargs['messages']):
                raise ValueError('only text messages allowed; no remote media')
            kwargs.update(model=a.model, temperature=0, max_tokens=4096, tool_choice='auto')
            response = client.chat.completions.create(**kwargs)
            tmp = response_path.with_suffix('.tmp')
            tmp.write_text(response.model_dump_json(), encoding='utf-8')
            tmp.replace(response_path)
        except Exception as exc:
            tmp = response_path.with_suffix('.tmp')
            tmp.write_text(json.dumps({'bridge_error': f'{type(exc).__name__}: {exc}'}), encoding='utf-8')
            tmp.replace(response_path)
    time.sleep(.1)
raise SystemExit('host bridge timeout')
