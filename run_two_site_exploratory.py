"""Run one exploratory repetition of each fixed two-site scenario."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from two_site_cases import CASES

root = Path(__file__).resolve().parent
batch = root / 'two_site_exploratory' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
batch.mkdir(parents=True)
tracked = [root / name for name in ('agent.py', 'two_site_server.py', 'site/site_a.html', 'site/site_b.html',
                                    'two_site_cases.py', 'tests/run_two_site_case.py', 'profiles/t4.json',
                                    'profiles/sample_resume.txt')]
def hashes(): return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
def now(): return datetime.now(timezone.utc).isoformat()
ollama = Path(os.environ['LOCALAPPDATA']) / 'Programs/Ollama/ollama.exe'
def info(*args):
    try: return subprocess.run([str(ollama), *args], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30).stdout.strip()
    except Exception as exc: return str(exc)
manifest = {'started_utc': now(), 'description': 'One exploratory repetition per case; not a formal failure-rate estimate.',
            'model': 'qwen3:8b', 'ollama_version': info('--version'), 'model_list': info('list'),
            'model_parameters': info('show','qwen3:8b','--parameters'), 'python': sys.version,
            'max_turns_per_request': 18, 'headless': True, 'pause_after_action': False,
            'sampling': 'No request-level overrides or fixed seed.', 'file_sha256': hashes(), 'cases': CASES, 'runs': []}
path = batch / 'manifest.json'
def save(): path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
save()
for case_id in CASES:
    if hashes() != manifest['file_sha256']:
        manifest['stopped'] = 'Tracked files changed during the batch.'; save(); raise SystemExit(manifest['stopped'])
    print('START', case_id, flush=True)
    before = {p.name for p in (root / 'runs').iterdir() if p.is_dir()}
    row = {'case': case_id, 'started_utc': now()}
    manifest['runs'].append(row); save()
    try:
        result = subprocess.run([sys.executable, str(root / 'tests/run_two_site_case.py'), case_id], cwd=root,
                                capture_output=True, text=True, encoding='utf-8', errors='replace',
                                timeout=600, env=dict(os.environ, PYTHONUTF8='1'))
        row.update(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
    except subprocess.TimeoutExpired:
        row['error'] = 'Timed out after 600 seconds.'
    created = [p for p in (root / 'runs').iterdir() if p.is_dir() and p.name not in before]
    row['run_directory'] = str(created[0].relative_to(root)) if len(created)==1 else None
    row['finished_utc'] = now(); save()
    print('DONE', case_id, row['run_directory'], row.get('error', ''), flush=True)
manifest['finished_utc'] = now(); save()
print('BATCH', batch, flush=True)
