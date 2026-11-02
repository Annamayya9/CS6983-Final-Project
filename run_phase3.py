"""Sequentially run the fixed Phase 3 scripts and persist an incremental manifest."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
out = ROOT / 'phase3'
out.mkdir(exist_ok=True)
manifest_path = out / 'manifest.json'
if manifest_path.exists():
    raise SystemExit('phase3/manifest.json already exists; preserve it and inspect before starting another batch.')
tracked = [ROOT / p for p in ['agent.py', 'pilot.py', 'scripted_responses.py', 'server.py', 'site/index.html', 'PHASE3_PROTOCOL.md', 'SCENARIOS.md', 'requirements.txt']]
tracked += sorted((ROOT / 'profiles').glob('*'))
def hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked if p.is_file()}
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def command_output(args):
    try: return subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30).stdout.strip()
    except Exception as exc: return str(exc)
ollama = Path(os.environ['LOCALAPPDATA']) / 'Programs/Ollama/ollama.exe'
data = {'started_utc': now(), 'model': 'qwen3:8b', 'ollama_version': command_output([str(ollama), '--version']),
        'ollama_models': command_output([str(ollama), 'list']), 'python': sys.version,
        'playwright': command_output([sys.executable, '-m', 'pip', 'show', 'playwright']),
        'model_parameters': command_output([str(ollama), 'show', 'qwen3:8b', '--parameters']),
        'sampling': 'Ollama defaults; no seed explicitly set', 'headless': True,
        'file_sha256': hashes(), 'runs': []}
def save(): manifest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
save()
for case in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'C']:
    for trial in range(1, 4):
        if hashes() != data['file_sha256']:
            data['stopped'] = 'Tracked files changed during the batch'; save(); raise SystemExit(data['stopped'])
        print(f'START {case} {trial}', flush=True)
        before = {p.name for p in (ROOT / 'runs').iterdir() if p.is_dir()}
        row = {'case': case, 'trial': trial, 'started_utc': now()}
        data['runs'].append(row); save()
        try:
            env = dict(os.environ, PYTHONUTF8='1')
            result = subprocess.run([sys.executable, str(ROOT / 'pilot.py'), case], cwd=ROOT,
                                    capture_output=True, text=True, encoding='utf-8', errors='replace',
                                    timeout=900, env=env)
            row.update(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired as exc:
            row.update(error='Trial timed out after 900 seconds', stdout=str(exc.stdout), stderr=str(exc.stderr))
        created = [p for p in (ROOT / 'runs').iterdir() if p.is_dir() and p.name not in before]
        row['run_directory'] = str(created[0].relative_to(ROOT)) if len(created) == 1 else None
        row['finished_utc'] = now(); save()
        print(f"DONE {case} {trial}: {row.get('run_directory')} exit={row.get('exit_code')}", flush=True)
data['finished_utc'] = now(); save()
