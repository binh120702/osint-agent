"""Launch one isolated candidate pilot with a bounded host inference bridge."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import dotenv_values

root = Path(__file__).resolve().parent
p = argparse.ArgumentParser()
p.add_argument('--run-dir', default='OSINT-001')
p.add_argument('--prepare-from')
a = p.parse_args()
run = root / 'runs' / a.run_dir
if a.prepare_from:
    import shutil
    run.mkdir(parents=True, exist_ok=False)
    shutil.copytree(root / 'runs' / a.prepare_from / 'input', run / 'input')
    (run / 'io').mkdir()
io = run / 'io'
if any(io.glob('request-*.json')):
    raise SystemExit('Refusing to overwrite an existing run; archive and choose a new directory.')
values = dotenv_values(Path.cwd() / '.env')
provider = os.environ.get('LLM_PROVIDER', values.get('LLM_PROVIDER', 'openai'))
model = os.environ.get('OPENAI_MODEL_ID', values.get('OPENAI_MODEL_ID', ''))
if provider != 'openai' or model != 'gpt-5.6-luna':
    raise SystemExit('Configured provider/model differs from the approved pilot specification.')
image = subprocess.check_output(['docker', 'image', 'inspect', 'osint-bench-openosint:1ab71de', '--format', '{{.Id}}'], text=True).strip()
name = 'osint-openosint-pilot-' + str(int(time.time()))
command = ['docker', 'run', '--name', name, '--network', 'none', '--read-only', '--tmpfs', '/tmp:rw,noexec,nosuid,size=256m', '--security-opt', 'no-new-privileges', '--cap-drop', 'ALL', '--memory', '2g', '--cpus', '2', '--pids-limit', '128', '--mount', f'type=bind,source={run / "input"},target=/input,readonly', '--mount', f'type=bind,source={io},target=/io', image]
manifest = {'started_at': datetime.now(timezone.utc).isoformat(), 'model': model, 'provider': provider, 'upstream_commit': '1ab71de6cdb1e6f5423c46e154b7a838b233aae2', 'image_id': image, 'network': 'none; host file bridge permits inference only', 'credential_in_container': False, 'maximum_requests': 20, 'sdk_max_retries_per_request': 0, 'maximum_completion_tokens_per_request': 4096, 'temperature': 0, 'timeout_seconds': 900, 'docker_command': command, 'files': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in (root/'adapter.py', root/'inference_bridge.py', root/'replay.py', run/'input/case.json')}, 'evaluation': 'assisted; canonical entities and expected proof conclusions supplied; not blind', 'status': 'running'}
(run/'manifest.json').write_text(json.dumps(manifest, indent=2))
with (run/'bridge.log').open('w', encoding='utf-8') as bridge_log, (run/'container.log').open('w', encoding='utf-8') as log:
    bridge = subprocess.Popen([sys.executable, str(root/'inference_bridge.py'), '--io', str(io), '--model', model, '--max-requests', '20', '--timeout', '900'], stdout=bridge_log, stderr=subprocess.STDOUT)
    try:
        completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=920)
        manifest.update(status='completed' if completed.returncode == 0 else 'failed', exit_code=completed.returncode)
    except subprocess.TimeoutExpired:
        subprocess.run(['docker', 'stop', '-t', '5', name], capture_output=True)
        manifest.update(status='timeout')
    finally:
        if bridge.poll() is None:
            bridge.terminate()
        bridge.wait(timeout=10)
        inspect = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True)
        if inspect.returncode == 0:
            (run/'container-inspect.json').write_text(inspect.stdout)
        manifest['finished_at'] = datetime.now(timezone.utc).isoformat()
        (run/'manifest.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps({'status': manifest['status'], 'run': str(run), 'container': name}))
if manifest['status'] != 'completed':
    raise SystemExit(1)
