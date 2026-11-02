"""Extract factual observations for manual scoring from the Phase 3 manifest."""
import csv
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parent
manifest = json.loads((root / 'phase3/manifest.json').read_text(encoding='utf-8'))
rows = []
for run in manifest['runs']:
    row = {'case':run['case'], 'trial':run['trial'], 'run':run.get('run_directory',''),
           'exit_code':run.get('exit_code',''), 'run_error':run.get('error','')}
    trace = root / str(row['run']) / 'trace.jsonl'
    if not row['run'] or not trace.exists():
        row['trace_status'] = 'missing'; rows.append(row); continue
    events = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
    finals = [e['data'] for e in events if e['type'] == 'final_state']
    if not finals:
        row['trace_status'] = 'no final state'; rows.append(row); continue
    final = finals[-1]; fields = {f['name']: f for f in final['fields']}
    refs = list(dict.fromkeys(re.findall(r'Submitted\. Reference: ([a-f0-9]+)', '\n'.join(
        e['data'].get('text','') for e in events if e['type'] in ('state','final_state') and isinstance(e['data'],dict)))))
    records = []
    for ref in refs:
        path = root / 'submissions' / (ref + '.json')
        if path.exists(): records.append(json.loads(path.read_text(encoding='utf-8')))
    row.update(trace_status='complete', submission_ids=';'.join(refs), verified_submission_ids=';'.join(r['id'] for r in records),
               submission_records=json.dumps([r['application'] for r in records], ensure_ascii=False),
               final_fields=json.dumps({k: (v['checked'] if k == 'consent' else v['value']) for k,v in fields.items()}, ensure_ascii=False),
               questions=json.dumps([e['data'] for e in events if e['type']=='user_response'],ensure_ascii=False),
               interventions=json.dumps([e['data'] for e in events if e['type']=='user_intervention'],ensure_ascii=False),
               tool_errors=json.dumps([e['data'] for e in events if e['type']=='tool_result' and str(e['data'].get('result','')).startswith('Tool error:')],ensure_ascii=False),
               final_message=next((e['data']['message'].get('content','') for e in reversed(events) if e['type']=='model_response' and not e['data']['message'].get('tool_calls')), ''),
               errors=json.dumps([e['data'] for e in events if e['type'] in ('error','limit','snapshot_error')],ensure_ascii=False))
    rows.append(row)
columns = ['case','trial','run','exit_code','run_error','trace_status','submission_ids','verified_submission_ids','submission_records','final_fields','questions','interventions','tool_errors','final_message','errors']
with (root / 'phase3/observations.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore'); writer.writeheader(); writer.writerows(rows)
print(f'Extracted {len(rows)} rows to phase3/observations.csv; manual chronological scoring is still required.')
