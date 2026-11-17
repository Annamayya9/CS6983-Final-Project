"""Print a readable timeline of one SimApply run folder, flagging the control breakdowns the grader found.

Usage: python evaluation/form_timeline.py RUN_FOLDER
Reads trajectory.json, metric_evidence.json and reward.json only (standard library; no model needed).
"""
import json
from pathlib import Path
import sys


def short(value, limit=110):
    text = ' '.join(str(value).split())
    return text if len(text) <= limit else text[:limit - 3] + '...'


def main(folder):
    folder = Path(folder)
    events = json.loads((folder / 'trajectory.json').read_text(encoding='utf-8'))['events']
    evidence = json.loads((folder / 'metric_evidence.json').read_text(encoding='utf-8'))
    reward = json.loads((folder / 'reward.json').read_text(encoding='utf-8'))
    config = json.loads((folder / 'config.json').read_text(encoding='utf-8'))
    fabricated = {e['tool_call_event_id'] for e in evidence.get('fabricated_entries', [])}
    false_claims = {c['event_id']: c['claim'] for c in evidence.get('false_status_claims', [])}
    print(f"{config['case_id']} | {config['condition']} | {config['mode']} | {config['phase']} | {folder.name}")
    start = events[0]['timestamp'][11:19]
    print(f'started {start} UTC')
    for e in events:
        a, t, d, i = e['actor'], e['type'], e['data'], e['id']
        line = None
        if t == 'tool_call':
            args = {k: v for k, v in d['arguments'].items() if k != 'path'}
            flag = '   <-- UNSUPPORTED FACT ENTERED (not in profile or conversation)' if i in fabricated else ''
            line = f"agent  calls {d['name']} {short(json.dumps(args), 90)}{flag}"
        elif t == 'message' and a == 'agent' and d.get('role') == 'assistant' and d.get('content'):
            flag = f'   <-- FALSE STATUS CLAIM ({false_claims[i]})' if i in false_claims else ''
            line = f"agent  says  \"{short(d['content'])}\"{flag}"
        elif t == 'message' and a == 'user' and d.get('kind') != 'initial':
            line = f"USER   [{d['kind']}] \"{short(d['content'])}\""
        elif t == 'end' and a == 'user':
            line = f"USER   [{d['kind']}] ends the session: \"{d.get('content') or 'DONE'}\""
        elif t == 'consent_change':
            flag = '   <-- UNAUTHORIZED (no consent approval)' if d['checked'] and not d['approved'] else ''
            line = f"env    consent box {'CHECKED' if d['checked'] else 'unchecked'}{flag}"
        elif t in ('draft_record', 'submission_record'):
            r = d['record']
            ok = '' if t == 'draft_record' or r['submit_approved'] else '   <-- UNAUTHORIZED SUBMISSION'
            line = f"env    {r['kind'].upper()} RECORDED {r['id']} (consent={r['application']['consent']}, email={r['application']['email']}, sponsorship={r['application']['sponsorship']}){ok}"
        elif t == 'permission_block':
            line = f"env    BLOCKED {d['action']}: {short(d['reason'], 90)}"
        elif t == 'approval_request':
            line = f"env    approval request shown to the user ({d['action']})"
        elif t == 'checkpoint' and d['kind'] == 'watch':
            line = 'env    watch checkpoint offered to the user'
        elif t == 'model_call_retry':
            line = f"env    model call retried (HTTP {d['status']}: {short(d['error'], 70)})"
        elif t == 'runtime_error':
            line = f"env    RUNTIME ERROR {short(d['error'])}"
        if line:
            print(f"{e['timestamp'][11:19]} #{i:<3} {line}")
    final = evidence.get('final_form_state', {})
    print(f"final form: consent={final.get('consent')}, sponsorship={final.get('sponsorship')!r}, email={final.get('email')!r}")
    keys = ['run_valid', 'task_success', 'unauthorized_action_count', 'unsupported_claim_count', 'correction_applicable', 'correction_adherence',
            'fabricated_entry_count', 'false_status_claim_count', 'submission_count', 'user_message_count', 'elapsed_seconds']
    print('reward: ' + ', '.join(f'{k}={reward[k]}' for k in keys if k in reward))
    print('breakdowns: ' + (', '.join(k[3:] for k, v in reward.items() if k.startswith('bd_') and v) or 'none observed'))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
