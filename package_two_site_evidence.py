"""Copy exact synthetic traces, screenshots, and referenced submissions for a batch."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

root = Path(__file__).resolve().parent
batch = Path(sys.argv[1]).resolve()
if batch.parent != (root / 'two_site_exploratory').resolve():
    raise SystemExit('Expected a batch directory inside two_site_exploratory.')
manifest = json.loads((batch / 'manifest.json').read_text(encoding='utf-8'))
evidence = batch / 'evidence'
if evidence.exists():
    raise SystemExit('Evidence directory already exists; do not overwrite it.')
evidence.mkdir()
files = []

def copy_verified(source, destination):
    if not source.is_file(): raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if hashlib.sha256(destination.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError(f'Copy verification failed: {destination}')
    files.append({'file': str(destination.relative_to(batch)), 'sha256': source_hash})

for row in manifest['runs']:
    if not row.get('run_directory'): raise ValueError(f"Missing run: {row['case']}")
    run = (root / row['run_directory']).resolve()
    if run.parent != (root / 'runs').resolve(): raise ValueError('Run path escaped runs directory.')
    case = evidence / row['case']
    copy_verified(run / 'trace.jsonl', case / 'trace.jsonl')
    for site in ('site-a', 'site-b'):
        image = run / f'final-{site}.png'
        if image.exists(): copy_verified(image, case / image.name)
    events = [json.loads(line) for line in (run / 'trace.jsonl').read_text(encoding='utf-8').splitlines()]
    references = {e['data']['result']['reference'] for e in events if e['type']=='tool_result'
                  and isinstance(e['data'].get('result'), dict)
                  and e['data']['result'].get('submission')=='recorded'}
    for reference in sorted(references):
        if not re.fullmatch('[a-f0-9]{32}', reference): raise ValueError('Invalid submission reference')
        source = root / 'submissions' / f'{reference}.json'
        record = json.loads(source.read_text(encoding='utf-8'))
        if record['id'] != reference: raise ValueError('Submission reference mismatch')
        copy_verified(source, case / 'submissions' / source.name)

(batch / 'evidence_manifest.json').write_text(json.dumps({'files': files}, indent=2), encoding='utf-8')
print(f'Copied and verified {len(files)} evidence files into {evidence}')
