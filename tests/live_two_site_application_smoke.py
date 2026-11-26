"""Development smoke check filling two different local application forms with Qwen."""
import builtins
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parents[1]
turns = iter([
    'Open http://127.0.0.1:8003/ for Site B. Fill its application using the profile. Do not submit.',
    'Return to Site A and report whether the application is filled. Do not submit.',
    '/quit',
])

def scripted_input(prompt):
    if prompt.startswith('Your response:'):
        answer = 'Use the information already provided and do not submit either application.'
    else:
        answer = next(turns)
    print(prompt + answer, flush=True)
    return answer

builtins.input = scripted_input
sys.argv = ['agent.py', '--two-sites', '--headless', '--profile', str(root / 'profiles/sample.json'),
            '--instruction', 'Fill the Site A application using the profile. Do not submit.']
runpy.run_path(str(root / 'agent.py'), run_name='__main__')
