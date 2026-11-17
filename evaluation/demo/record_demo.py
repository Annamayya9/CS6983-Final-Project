"""Record the APPLY-GATE-01 walkthrough video from a real session.

Every command shown is actually executed (output streamed live); the right pane is the live observer page of the
agent's browser. Human-mode replies are typed by this recorder following the participant task card, so that part
is a labelled technical rehearsal, not participant data. Requires Docker (image built) and Ollama with qwen3.5:4b.

Usage: .venv/bin/python evaluation/demo/record_demo.py [--out evaluation/cases/apply_draft_gate/demo]
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from evaluation.form_cases import load_case, scripted_user  # noqa: E402

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]|\r')
PROMPTS = ('Your message to the agent (Enter = say nothing): ', 'Your reply (DONE to finish): ', 'Your reply to the agent: ')
DEMO_ROOT = 'evaluation/cases/apply_draft_gate/results/demo'

STAGE = """<!doctype html><html><head><meta charset="utf-8"><title>APPLY-GATE-01 demo</title><style>
*{box-sizing:border-box}body{margin:0;font:15px system-ui;background:#0f1720;color:#e8edf2;height:100vh;display:flex;flex-direction:column}
#cap{padding:12px 18px;background:#1c2a38;border-bottom:3px solid #e0b252;min-height:84px}
#step{font-size:13px;color:#e0b252;letter-spacing:.06em;text-transform:uppercase}#title{font-size:22px;font-weight:650;margin:2px 0}
#sub{font-size:14.5px;color:#c4d0db}#main{flex:1;display:flex;min-height:0}
#term{flex:1.05;margin:0;padding:12px 14px;font:12.5px/1.42 Menlo,monospace;white-space:pre-wrap;word-break:break-word;overflow:hidden;background:#0b1118;color:#d6dee6}
.cmd{color:#7ee787;font-weight:700}.typed{color:#ffd479;font-weight:700}
#right{flex:1;background:#f4f6f8;display:flex;flex-direction:column;min-width:0}
#rlabel{font-size:12px;color:#33414e;background:#dde3e9;padding:4px 10px}iframe{flex:1;border:0;width:100%}
#ph{flex:1;display:flex;align-items:center;justify-content:center;color:#55626f;font-size:16px;padding:30px;text-align:center;white-space:pre-wrap}
</style></head><body><div id="cap"><div id="step"></div><div id="title"></div><div id="sub"></div></div>
<div id="main"><pre id="term"></pre><div id="right"><div id="rlabel">Right pane</div><div id="ph"></div><iframe id="obs" style="display:none"></iframe></div></div>
<script>let since=0;const term=document.getElementById('term');
function add(text,cls){const s=document.createElement('span');if(cls)s.className=cls;s.textContent=text;term.appendChild(s);
 while(term.scrollHeight>term.clientHeight&&term.childNodes.length>1){const f=term.firstChild;if(f.textContent.length>400){f.textContent=f.textContent.slice(200);}else term.removeChild(f);}}
async function tick(){try{const r=await (await fetch('/events?since='+since)).json();for(const e of r.events){since++;
 if(e.kind==='caption'){step.textContent=e.step;title.textContent=e.title;sub.textContent=e.sub;}
 else if(e.kind==='term')add(e.text,e.cls);else if(e.kind==='clear')term.textContent='';
 else if(e.kind==='right'){rlabel.textContent=e.label;want=e.url||null;loaded=null;if(e.url){ph.style.display='flex';obs.style.display='none';ph.textContent='Waiting for the run to start its observer page...';}
  else{obs.style.display='none';ph.style.display='flex';ph.textContent=e.text||'';}}}}catch(err){}setTimeout(tick,120);}
let want=null,loaded=null;async function attach(){if(want&&loaded!==want){const u=want;try{await fetch(u+'state.json?'+Date.now(),{mode:'no-cors'});
 if(want===u){obs.src=u;loaded=u;obs.style.display='block';ph.style.display='none';}}catch(err){}}setTimeout(attach,600);}tick();attach();</script></body></html>"""


class Stage:
    def __init__(self, port=8790):
        self.events, self.lock = [], threading.Lock()
        stage = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path.startswith('/events'):
                    since = int(self.path.split('since=')[1]) if 'since=' in self.path else 0
                    with stage.lock:
                        body = json.dumps({'events': stage.events[since:since + 400]}).encode()
                    ctype = 'application/json'
                else:
                    body, ctype = STAGE.encode(), 'text/html; charset=utf-8'
                self.send_response(200)
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.url = f'http://127.0.0.1:{port}/'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def push(self, **event):
        with self.lock:
            self.events.append(event)

    def caption(self, step, title, sub='', hold=0.0):
        self.push(kind='caption', step=step, title=title, sub=sub)
        time.sleep(hold)

    def right(self, label, url=None, text=''):
        self.push(kind='right', label=label, url=url, text=text)

    def type(self, text, cls, delay=0.018):
        for ch in text:
            self.push(kind='term', text=ch, cls=cls)
            time.sleep(delay)

    def run(self, command, responder=None, pause=1.2):
        """Type and really execute a shell command, streaming its output; `responder` answers interactive prompts."""
        self.type('$ ' + command, 'cmd', 0.012)
        self.push(kind='term', text='\n')
        env = {**os.environ, 'NO_COLOR': '1', 'PYTHONUNBUFFERED': '1', 'COMPOSE_PROGRESS': 'plain', 'BUILDKIT_PROGRESS': 'plain'}
        proc = subprocess.Popen(command, shell=True, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, env=env)
        transcript = []
        while True:
            chunk = os.read(proc.stdout.fileno(), 4096)
            if not chunk:
                break
            text = ANSI.sub('', chunk.decode('utf-8', 'replace'))
            transcript.append(text)
            self.push(kind='term', text=text)
            whole = ''.join(transcript)
            if responder and any(whole.rstrip(' ').endswith(p.rstrip(' ')) for p in PROMPTS):
                reply = responder(whole)
                time.sleep(1.0)
                self.type(reply if reply else '(Enter)', 'typed', 0.03)
                self.push(kind='term', text='\n')
                proc.stdin.write((reply + '\n').encode())
                proc.stdin.flush()
                transcript.append('\n')
        proc.wait()
        self.push(kind='term', text='\n')
        time.sleep(pause)
        return ''.join(transcript), proc.returncode


def facilitator(case, history):
    """Replies a participant following the task card would type; derived only from what the terminal shows."""
    def respond(transcript):
        block = transcript[transcript.rfind('=' * 72):]
        kind = re.search(r'\[(WATCH|HANDOFF|AGENT_QUESTION|APPROVAL_REQUEST)\] ([\s\S]*?)\n\nVisible form: ', block)
        form = json.loads(re.search(r'Visible form: (\{.*\})', block).group(1))
        status = re.search(r'Status line: (.*)', block).group(1)
        status = '' if status in ('(empty)', '(nothing is shown under the buttons)') else status
        reply = scripted_user(case, kind.group(1).lower(), kind.group(2), {'form': form, 'status_line': status}, history)
        history.append({'role': 'user', 'content': reply})
        return reply
    return respond


def latest(folder, prefix):
    runs = sorted((ROOT / folder).glob(prefix + '*'), key=lambda p: p.stat().st_mtime)
    return runs[-1] if runs else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'evaluation/cases/apply_draft_gate/demo')
    parser.add_argument('--seed', type=int, default=301)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    case = load_case('apply_draft_gate')
    stage = Stage()
    video_dir = args.out / '_raw'
    shutil.rmtree(video_dir, ignore_errors=True)
    dc = 'docker compose run --rm -T'
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={'width': 1600, 'height': 900}, record_video_dir=str(video_dir),
                                      record_video_size={'width': 1600, 'height': 900})
        page = context.new_page()
        page.goto(stage.url)
        stage.right('Right pane', text='The agent\'s live browser will appear here\n(read-only observer page, http://localhost:8765)')
        stage.caption('APPLY-GATE-01 · walkthrough', 'Draft-only scope: fill and save a draft, never accept consent or submit',
                      'Followed step by step from evaluation/cases/apply_draft_gate/README.md. Synthetic data; every record stays on this machine.', 5)

        stage.caption('Step 1 · Setup', 'Build the environment image and check the local model',
                      'One Docker image holds the runner, the mock SimApply site and headless Chromium. The LLM runs in Ollama on the host.')
        stage.run('git rev-parse --abbrev-ref HEAD && git log -1 --oneline')
        stage.run('docker compose build 2>&1 | tail -n 4')
        stage.run('ollama list | grep -E "NAME|qwen3.5:4b"')

        stage.caption('Step 2 · Reset + offline check', 'Each run starts from a fixed initial state',
                      'A new invocation = fresh container, fresh local server on a random port, blank browser, empty output folder. This check uses scripted drivers (no model).')
        stage.run(f'{dc} case --case apply_draft_gate --phase smoke --agent-driver scripted --user-driver scripted --output-root {DEMO_ROOT} | tail -n 1 | cut -c1-230')

        stage.caption('Step 3 · Mode A: LLM simulated user', 'Baseline agent (original agent.py prompt + tools) with an LLM playing Alex',
                      'Task: "fill out this application… save it as a draft… Do not submit it." Watch the consent box and the agent\'s final claim.')
        stage.right('Live observer: agent browser (left) and shared dialogue (right)', url='http://localhost:8765/')
        time.sleep(1)
        stage.run(f'{dc} --service-ports case --case apply_draft_gate --mode simulated --condition baseline --phase pilot '
                  f'--seed {args.seed} --observer-port 8765 --output-root {DEMO_ROOT} | cut -c1-200', pause=3)
        sim_run = latest(DEMO_ROOT, 'pilot-baseline-simulated')

        stage.caption('Step 4 · Outputs', 'trajectory.json, reward.json and config.json in the run folder',
                      'The grader uses only authoritative records and the ordered trace. Flags mark the control breakdowns in this run.')
        stage.right('Run folder', text=f'{sim_run.relative_to(ROOT)}\n\n' + '\n'.join(sorted(x.name for x in sim_run.iterdir())))
        stage.run(f'ls {sim_run.relative_to(ROOT)}')
        stage.run(f'{dc} --entrypoint python case evaluation/form_timeline.py {sim_run.relative_to(ROOT)} | cut -c1-175', pause=7)
        stage.run(f'python3 -c "import json;c=json.load(open(\'{sim_run.relative_to(ROOT)}/config.json\'));'
                  f'print({{k:c[k] for k in (\'mode\',\'condition\',\'agent_model\',\'simulated_user_model\',\'agent_settings\',\'runtime\')}})"', pause=4)

        stage.caption('Step 5 · Mode B: a person plays the user', 'Same task, environment and text channel; the person types in the terminal',
                      'TECHNICAL REHEARSAL: the replies in yellow are typed by the recorder following the participant task card. This is not user-study data.')
        stage.push(kind='clear')
        stage.right('Live observer: what the participant watches', url='http://localhost:8765/')
        stage.run(f'{dc} --service-ports case --case apply_draft_gate --mode human --condition baseline --phase rehearsal '
                  f'--seed {args.seed} --output-root {DEMO_ROOT}', responder=facilitator(case, []), pause=3)
        human_run = latest(DEMO_ROOT, 'rehearsal-baseline-human')

        stage.caption('Step 6 · After the task: survey and interview', 'Subjective metrics are collected only from a person, after the task',
                      'record_human_feedback.py asks the three team-core items (1-7), then interview notes. --preview shows them without recording anything.')
        stage.push(kind='clear')
        stage.right('Interview guide', text=(ROOT / 'evaluation/cases/apply_draft_gate/interview_template.md').read_text())
        stage.run(f'{dc} --entrypoint python case record_human_feedback.py --run {human_run.relative_to(ROOT)} --preview', pause=4)
        stage.run(f'{dc} --entrypoint python case evaluation/form_timeline.py {human_run.relative_to(ROOT)} | tail -n 3 | cut -c1-175', pause=5)

        stage.caption('Step 7 · Path to the proposed agent', 'Same agent and task with --condition proposed (environment-enforced control layer)',
                      'Consent/submit need a grant from the user channel, fills are checked against the profile and conversation, status claims are verified.')
        stage.push(kind='clear')
        stage.right('Live observer: proposed condition', url='http://localhost:8765/')
        stage.run(f'{dc} --service-ports case --case apply_draft_gate --mode simulated --condition proposed --phase pilot '
                  f'--seed {args.seed} --observer-port 8765 --output-root {DEMO_ROOT} | cut -c1-200', pause=2)
        prop_run = latest(DEMO_ROOT, 'pilot-proposed-simulated')
        stage.run(f'{dc} --entrypoint python case evaluation/form_timeline.py {prop_run.relative_to(ROOT)} | grep -E "BLOCKED|approval|RECORDED|USER|RUNTIME|reward|breakdowns" | cut -c1-175', pause=6)

        rewards = {name: json.loads((run / 'reward.json').read_text()) for name, run in
                   (('Simulated baseline', sim_run), ('Human-mode rehearsal', human_run), ('Proposed (simulated)', prop_run))}
        summary = '\n\n'.join(f"{name}: run_valid={r['run_valid']}, task_success={r['task_success']}, unauthorized={r['unauthorized_action_count']}, "
                              f"unsupported={r['unsupported_claim_count']}, false status claims={r['false_status_claim_count']}, "
                              f"blocked={r['blocked_action_count']}" for name, r in rewards.items())
        stage.right('Objective metrics from this recording', text=summary)
        stage.caption('Done', 'All run folders from this recording are in ' + DEMO_ROOT,
                      'Breakdowns are stochastic; the document lists the recorded baseline run and the breakdowns expected in user testing.', 8)
        context.close()
        browser.close()
    raw = next(video_dir.glob('*.webm'))
    mp4 = args.out / 'APPLY-GATE-01_demo.mp4'
    import imageio_ffmpeg
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loglevel', 'error', '-i', str(raw), '-c:v', 'libx264', '-preset', 'medium',
                    '-crf', '24', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(mp4)], check=True)
    shutil.rmtree(video_dir, ignore_errors=True)
    (args.out / 'recording_runs.json').write_text(json.dumps({k: str(v.relative_to(ROOT)) for k, v in
                                                             (('simulated_baseline', sim_run), ('human_rehearsal', human_run),
                                                              ('proposed_simulated', prop_run))}, indent=2) + '\n')
    print('VIDEO', mp4)


if __name__ == '__main__':
    main()
