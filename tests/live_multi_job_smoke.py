"""Development smoke check with Qwen, not a scored baseline trial."""
import builtins
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parents[1]
turns = iter([
    'Now open Job B and set its salary expectation to 90000. Do not submit.',
    'Return to Job A and tell me its salary expectation. Do not submit.',
    '/quit',
])

def scripted_input(prompt):
    if prompt.startswith('Your response:'):
        answer = 'Please inspect the page and follow the instructions already given.'
    else:
        answer = next(turns)
    print(prompt + answer, flush=True)
    return answer

builtins.input = scripted_input
sys.argv = ['agent.py', '--multi-job', '--headless', '--site-url', 'http://127.0.0.1:8011/',
            '--profile', str(root / 'profiles/sample.json'),
            '--instruction', 'For Job A, set the salary expectation to 80000. Do not submit.']
runpy.run_path(str(root / 'agent.py'), run_name='__main__')
