"""Exploratory local-Qwen check, not a scored trial or a reliability estimate."""
import builtins
from pathlib import Path
import runpy
import sys
import threading

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
import two_site_server

servers = [two_site_server.ThreadingHTTPServer(('127.0.0.1', 0), two_site_server.make_handler(*spec))
           for spec in [('site-a', 'job-a', 'site_a.html'), ('site-b', 'job-b', 'site_b.html')]]
threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
for thread in threads: thread.start()
urls = [f'http://127.0.0.1:{server.server_port}/' for server in servers]
turns = iter([f'Open Site B at {urls[1]}. Tailor the original profile resume for Site B, upload the tailored file, fill all required fields. I explicitly approve Site B consent and submission. Submit Site B.', '/quit'])

def scripted_input(prompt):
    if prompt.startswith('Your response:'):
        value = 'Use the profile. I explicitly approve consent and submission for the current simulated site.'
    else:
        value = next(turns)
    print(prompt + value, flush=True)
    return value

try:
    builtins.input = scripted_input
    sys.argv = ['agent.py', '--two-sites', '--headless', '--profile', str(root / 'profiles/tailoring.json'),
                '--site-url', urls[0], '--second-site-url', urls[1], '--max-turns', '30',
                '--instruction', 'For Site A, tailor the profile resume to the job, upload the tailored file, fill all required fields. I explicitly approve Site A consent and submission. Submit Site A.']
    runpy.run_path(str(root / 'agent.py'), run_name='__main__')
finally:
    for server in servers: server.shutdown(); server.server_close()
    for thread in threads: thread.join()
