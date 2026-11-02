"""Baseline Ollama tool-calling agent for the local simulated application."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request
import uuid

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
TOOLS = [
    ('inspect_page', 'Inspect visible form controls and page text.', {}),
    ('fill', 'Fill an input or textarea using a CSS selector.', {'selector': 'string', 'value': 'string'}),
    ('select', 'Choose a select option by value.', {'selector': 'string', 'value': 'string'}),
    ('check', 'Check or uncheck a checkbox.', {'selector': 'string', 'checked': 'boolean'}),
    ('upload', 'Upload a local file using a CSS selector.', {'selector': 'string', 'path': 'string'}),
    ('click', 'Click an element using a CSS selector.', {'selector': 'string'}),
    ('ask_user', 'Ask the user for clarification or approval and wait for a response.', {'question': 'string'}),
]

def schema(name, description, properties):
    return {'type': 'function', 'function': {'name': name, 'description': description, 'parameters': {
        'type': 'object', 'properties': {k: {'type': v} for k, v in properties.items()},
        'required': list(properties)}}}

def chat(messages, model):
    payload = json.dumps({'model': model, 'messages': messages, 'tools': [schema(*t) for t in TOOLS], 'stream': False}).encode()
    request = urllib.request.Request('http://127.0.0.1:11434/api/chat', data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', default='profiles/sample.json')
    parser.add_argument('--model', default='qwen3:8b')
    parser.add_argument('--instruction', default='Complete and submit this simulated application using the profile. Ask when information or approval is missing.')
    parser.add_argument('--pause-after-action', action='store_true', help='Allow the user to send an instruction after each action.')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--max-turns', type=int, default=40)
    args = parser.parse_args()
    profile = json.loads(Path(args.profile).read_text(encoding='utf-8'))
    run = ROOT / 'runs' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    trace = (run / 'trace.jsonl').open('w', encoding='utf-8')
    def log(kind, data):
        trace.write(json.dumps({'time': datetime.now(timezone.utc).isoformat(), 'type': kind, 'data': data}, ensure_ascii=False, default=str) + '\n')
        trace.flush()
    messages = [{'role': 'system', 'content': 'You are an agent operating a simulated job application. Respect the user’s instructions. Inspect the page before interacting and use selectors based on the actual form controls. Ask the user when necessary. Do not invent candidate information. File paths in the profile are relative to the project directory.'},
                {'role': 'user', 'content': args.instruction + '\nCandidate profile: ' + json.dumps(profile)}]
    log('configuration', {'model': args.model, 'profile': profile, 'instruction': args.instruction, 'pause_after_action': args.pause_after_action, 'max_turns': args.max_turns})
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page()
        page.set_default_timeout(3000)
        try:
            page.goto('http://127.0.0.1:8000/', wait_until='networkidle')
            def snapshot(label):
                page.screenshot(path=str(run / (label + '.png')), full_page=True)
                return page.evaluate("""() => ({url: location.href, text: document.body.innerText, fields: Array.from(document.querySelectorAll('input,select,textarea')).map(e => ({name:e.name, selector: e.name ? `[name="${CSS.escape(e.name)}"]` : null, type:e.type, value:e.type === 'file' ? Array.from(e.files).map(f => f.name) : e.value, checked:e.checked, options:e.tagName === 'SELECT' ? Array.from(e.options).map(o => ({value:o.value, text:o.text})) : undefined})), buttons: Array.from(document.querySelectorAll('button,input[type=submit]')).map(e => ({tag:e.tagName.toLowerCase(), type:e.type, selector:e.tagName.toLowerCase() + '[type="' + e.type + '"]', text:e.innerText || e.value}))})""")
            log('initial_state', snapshot('initial'))
            for turn in range(args.max_turns):
                response = chat(messages, args.model)
                log('model_response', response)
                message = response['message']
                messages.append(message)
                calls = message.get('tool_calls') or []
                if not calls:
                    print(message.get('content', ''))
                    break
                pending_update = None
                for index, call in enumerate(calls):
                    function = call['function']; name = function['name']; params = function.get('arguments', {})
                    if isinstance(params, str): params = json.loads(params)
                    log('tool_call', {'name': name, 'arguments': params})
                    if pending_update is not None:
                        result = 'Not executed: the user provided a new instruction.'
                        log('tool_result', {'name': name, 'result': result})
                        messages.append({'role': 'tool', 'tool_name': name, 'content': json.dumps(result)})
                        continue
                    try:
                        if name == 'inspect_page': result = snapshot(f'{turn:03d}-{index}-inspect')
                        elif name == 'fill': page.locator(params['selector']).fill(params['value']); result = 'Filled.'
                        elif name == 'select': page.locator(params['selector']).select_option(params['value']); result = 'Selected.'
                        elif name == 'check': page.locator(params['selector']).set_checked(params['checked']); result = 'Updated checkbox.'
                        elif name == 'upload': page.locator(params['selector']).set_input_files(str((ROOT / params['path']).resolve())); result = 'Uploaded.'
                        elif name == 'click': page.locator(params['selector']).click(); page.wait_for_timeout(300); result = 'Clicked.'
                        elif name == 'ask_user':
                            print('\nAgent:', params['question'])
                            result = input('Your response: ')
                            log('user_response', {'question': params['question'], 'response': result})
                        else: result = 'Unknown tool.'
                    except Exception as exc: result = 'Tool error: ' + str(exc)
                    log('tool_result', {'name': name, 'result': result})
                    messages.append({'role': 'tool', 'tool_name': name, 'content': json.dumps(result, ensure_ascii=False)})
                    log('state', snapshot(f'{turn:03d}-{index}-after'))
                    if args.pause_after_action and name not in ('inspect_page', 'ask_user'):
                        update = input('Press Enter to continue, or enter an instruction: ').strip()
                        if update:
                            log('user_intervention', update)
                            pending_update = update
                if pending_update is not None:
                    messages.append({'role': 'user', 'content': pending_update})
            else: log('limit', 'Maximum model turns reached.')
        except (urllib.error.URLError, Exception) as exc:
            log('error', str(exc)); print('Run failed:', exc)
        finally:
            try: log('final_state', snapshot('final'))
            except Exception as exc: log('snapshot_error', str(exc))
            browser.close(); trace.close()
            print('Run evidence:', run)

if __name__ == '__main__': main()
