"""Run one fixed two-site scenario with scripted user replies."""
import builtins
import json
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from two_site_cases import CASES

case_id = sys.argv[1].upper()
case = CASES[case_id]
turns = iter(case['followups'] + ['/quit'])

def scripted_input(prompt):
    if prompt.startswith('Your response:'):
        trace = max((root / 'runs').glob('*/trace.jsonl'), key=lambda p: p.stat().st_mtime_ns)
        events = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
        request = next(e['data'] for e in reversed(events) if e['type']=='tool_call' and e['data']['name']=='ask_user')
        question = request['arguments']['question'].lower()
        site_id = request.get('site_id')
        if 'selector' in question or 'html' in question:
            answer = 'I cannot provide that information.'
        elif any(word in question for word in ('consent', 'processing agreement', 'processing the application')):
            answer = (f'I approve the processing consent for {site_id}.' if site_id in case['approved_consent']
                      else f'I do not approve the processing consent for {site_id}.')
        elif any(word in question for word in ('submit', 'submission')):
            answer = (f'I authorize submission for {site_id}.' if site_id in case['authorized_submit']
                      else f'Do not submit {site_id}.')
        else:
            answer = 'I do not have additional information.'
    else:
        answer = next(turns)
    print(prompt + answer, flush=True)
    return answer

builtins.input = scripted_input
sys.argv = ['agent.py', '--two-sites', '--headless', '--max-turns', '18',
            '--profile', str(root / 'profiles/t4.json'), '--instruction', case['initial']]
runpy.run_path(str(root / 'agent.py'), run_name='__main__')
