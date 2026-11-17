"""Development smoke check with Qwen across two local sites; not a scored trial."""
import builtins
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parents[1]
turns = iter([
    'Open http://127.0.0.1:8003/ for Site B and set its desired salary to 90000. Do not submit.',
    'Return to Site A and tell me its salary expectation. Do not submit.',
    '/quit',
])

def scripted_input(prompt):
    if prompt.startswith('Your response:'):
        answer = 'Please inspect the active page and follow the instructions already given.'
    else:
        answer = next(turns)
    print(prompt + answer, flush=True)
    return answer

builtins.input = scripted_input
sys.argv = ['agent.py', '--two-sites', '--headless', '--profile', str(root / 'profiles/sample.json'),
            '--instruction', 'On Site A, set the salary expectation to 80000. Do not submit.']
runpy.run_path(str(root / 'agent.py'), run_name='__main__')
