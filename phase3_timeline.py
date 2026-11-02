"""Print compact trial timelines to support manual chronological scoring."""
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
manifest = json.loads((root / 'phase3/manifest.json').read_text(encoding='utf-8'))
for item in manifest['runs']:
    if len(sys.argv) > 1 and item['case'] != sys.argv[1]: continue
    if not item.get('run_directory'): continue
    trace = root / item['run_directory'] / 'trace.jsonl'
    if not trace.exists(): continue
    print('\n', item['case'], item['trial'], item['run_directory'])
    previous = {}
    submitted = False
    for line in trace.read_text(encoding='utf-8').splitlines():
        event = json.loads(line); kind = event['type']; d = event['data']
        if kind == 'state':
            fields = {f['name']: f['checked'] if f['name']=='consent' else f['value'] for f in d['fields']}
            for key in ('email','experience_duration','sponsorship','consent'):
                if fields.get(key) != previous.get(key): print('  FIELD',key,repr(fields.get(key)))
            previous = fields
            if 'Submitted. Reference:' in d['text'] and not submitted:
                print('  SUBMITTED',d['text'].split('Submitted. Reference:')[-1].strip()); submitted = True
        elif kind in ('user_response','user_intervention','error','limit'):
            print(' ',kind, d)
        elif kind == 'tool_result' and str(d.get('result','')).startswith('Tool error:'):
            print('  TOOL ERROR',d['name'], str(d['result']).splitlines()[0])
        elif kind == 'final_state':
            print('  FINAL', {f['name']:f['checked'] if f['name']=='consent' else f['value'] for f in d['fields']})
