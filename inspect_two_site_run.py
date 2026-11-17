"""Show the actual user dialogue, visible agent replies and authoritative final state for a trace audit."""
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
events = [json.loads(line) for line in (path / 'agent_trace/trace.jsonl').read_text(encoding='utf-8').splitlines()]
for index, event in enumerate(events):
    kind, data = event['type'], event['data']
    if kind in ('user_message', 'user_response', 'user_intervention'):
        print(index, 'USER', data)
    elif kind == 'model_response':
        message = data.get('message', {})
        if message.get('content') and not message.get('tool_calls'):
            print(index, 'AGENT', message['content'])
    elif kind == 'final_site_states':
        print(index, 'FINAL STATES')
        for state in data:
            if 'state' in state:
                print(state['site_id'], [(f['name'], f.get('value'), f.get('checked')) for f in state['state']['fields']])
print('SUBMISSIONS', [p.name for p in (path / 'submissions').glob('*.json')])
