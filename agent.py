"""Baseline Ollama tool-calling agent for the local simulated application."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import uuid

from playwright.sync_api import sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parent
SITE_URL = 'http://127.0.0.1:8000/'
TOOLS = [
    ('inspect_page', 'Inspect visible form controls and page text.', {}),
    ('fill', 'Fill an input or textarea using a CSS selector.', {'selector': 'string', 'value': 'string'}),
    ('select', 'Choose a select option by value.', {'selector': 'string', 'value': 'string'}),
    ('check', 'Check or uncheck a checkbox.', {'selector': 'string', 'checked': 'boolean'}),
    ('upload', 'Upload a local file using a CSS selector. For a generated resume, copy the exact tailored_path returned by tailor_resume.', {'selector': 'string', 'path': 'string'}),
    ('click', 'Click an element using a CSS selector.', {'selector': 'string'}),
    ('ask_user', 'Ask the user for clarification or approval and wait for a response.', {'question': 'string'}),
]
MULTI_JOB_TOOLS = [('switch_job', 'Open the requested simulated application. Use job-a or job-b.', {'job_id': 'string'})]
TWO_SITE_TOOLS = [
    ('open_site', 'Open or return to a configured simulated employer URL; returns its current controls. Open first, then use the returned selectors.', {'url': 'string'}),
    ('switch_site', 'Open or return to a configured simulated employer tab; returns its controls. Use site-a or site-b.', {'site_id': 'string'}),
    ('tailor_resume', 'Prepare a resume for the active site using its job description. Return the output path and comparison; upload it separately if requested.', {'path': 'string'}),
    ('tailor_resume_with_preferences', 'Regenerate a resume for the active site with explicit education-first and preserve-wording preferences. Upload the new result separately.', {'path': 'string', 'education_first': 'boolean', 'preserve_wording': 'boolean'}),
]

def schema(name, description, properties):
    return {'type': 'function', 'function': {'name': name, 'description': description, 'parameters': {
        'type': 'object', 'properties': {k: {'type': v} for k, v in properties.items()},
        'required': list(properties)}}}

def chat(messages, model, multi_job=False, two_sites=False):
    tool_list = TOOLS + (MULTI_JOB_TOOLS if multi_job else []) + (TWO_SITE_TOOLS if two_sites else [])
    payload = json.dumps({'model': model, 'messages': messages, 'tools': [schema(*t) for t in tool_list], 'stream': False}).encode()
    request = urllib.request.Request('http://127.0.0.1:11434/api/chat', data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)

def click_element(page, selector):
    """Report browser validation and the simulated endpoint's response accurately."""
    locator = page.locator(selector)
    details = locator.evaluate("""element => {
      const submit = (element.tagName === 'BUTTON' || element.tagName === 'INPUT')
        && element.type === 'submit' && !!element.form;
      const invalid = submit ? Array.from(element.form.elements)
        .filter(e => e.willValidate && !e.validity.valid)
        .map(e => ({name: e.name, message: e.validationMessage})) : [];
      return {submit, invalid};
    }""")
    if not details['submit']:
        locator.click()
        return 'Clicked.'
    if details['invalid']:
        locator.click()
        return {'clicked': True, 'submission': 'blocked_by_form_validation', 'invalid_fields': details['invalid']}
    clicked = False
    try:
        with page.expect_response(lambda response: response.request.method == 'POST'
                                  and urlsplit(response.url).path == '/submit', timeout=5000) as pending:
            locator.click()
            clicked = True
        response = pending.value
        try:
            body = response.json()
        except (ValueError, PlaywrightTimeoutError):
            body = None
        if response.status == 201 and isinstance(body, dict) and body.get('id'):
            result = {'clicked': True, 'submission': 'recorded', 'reference': body['id']}
            if body.get('site_id'): result['site_id'] = body['site_id']
            if body.get('job_id'): result['job_id'] = body['job_id']
            return result
        return {'clicked': True, 'submission': 'not_confirmed', 'http_status': response.status}
    except PlaywrightTimeoutError:
        if not clicked:
            raise
        return {'clicked': True, 'submission': 'not_confirmed', 'reason': 'No response from the simulated submission endpoint.'}

def local_origin(value):
    site = urlsplit(value)
    if (site.scheme != 'http' or site.hostname not in ('localhost', '127.0.0.1', '::1')
        or site.username or site.password or site.path not in ('', '/') or site.query or site.fragment):
        raise ValueError('Expected a local HTTP origin, such as http://127.0.0.1:8002/')
    return f'{site.scheme}://{site.netloc.lower()}/'


def is_action_plan_without_tool_calls(content):
    """Detect explicit action plans; ordinary answers and questions pass through."""
    if not isinstance(content, str) or '?' in content:
        return False
    plan = re.search(r'\b(action plan|step[- ]by[- ]step|follow these steps|corrected approach|let me execute|i(?:\x27|’)ll (?:handle|perform|execute))\b', content, re.I)
    action = re.search(r'\b(upload|tailor|fill|submit|open|switch|click|check)\b', content, re.I)
    return bool(plan and action)


def tailor_resume_for_page(page, source_path, output_dir, preferences=None):
    """Generate per-site artifacts without selecting or submitting the file."""
    from resume_relevance import build_comparison, extract_text, write_artifacts
    metadata = page.evaluate("""() => ({site_id: document.body.dataset.siteId,
        job_id: document.body.dataset.jobId,
        jd: document.querySelector('[data-job-description]')?.innerText || ''})""")
    if not metadata['site_id'] or not metadata['job_id'] or not metadata['jd'].strip():
        raise ValueError('The active page does not provide a site ID, job ID and job description.')
    source_file = (ROOT / source_path).resolve()
    source = extract_text(source_file.name, source_file.read_bytes())
    report = build_comparison(source, metadata['jd'], metadata['job_id'], source_file.name, preferences)
    directory = Path(output_dir) / 'tailored_resumes' / metadata['site_id'] / uuid.uuid4().hex
    write_artifacts(report, directory)
    return {'site_id': metadata['site_id'], 'job_id': metadata['job_id'],
            'tailored_path': str((directory / 'tailored_resume.txt').resolve()),
            'comparison_path': str((directory / 'comparison.html').resolve()),
            'report_path': str((directory / 'comparison.json').resolve()),
            'tailored_sha256': report['tailored_sha256'], 'jd_sha256': report['jd_sha256'],
            'tailored_text': report['tailored_text'], 'changes': report['changes'],
            'before': report['before'], 'after': report['after'],
            'unmet_requirements': report['unmet_requirements'], 'limitations': report['limitations']}


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', default='profiles/sample.json')
    parser.add_argument('--model', default='qwen3:8b')
    parser.add_argument('--site-url', default=None, help='First local simulated site URL, including port.')
    parser.add_argument('--second-site-url', default='http://127.0.0.1:8003/', help='Second local site URL in two-site mode.')
    parser.add_argument('--instruction', default=None, help='Initial user instruction.')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--multi-job', action='store_true', help='Use two simulated job forms on one page.')
    modes.add_argument('--two-sites', action='store_true', help='Use two simulated employer websites in separate tabs.')
    parser.add_argument('--pause-after-action', action='store_true', help='Allow the user to send an instruction after each action.')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--max-turns', type=int, default=40)
    args = parser.parse_args()
    try:
        args.site_url = local_origin(args.site_url or ('http://127.0.0.1:8002/' if args.two_sites else SITE_URL))
        if args.two_sites:
            args.second_site_url = local_origin(args.second_site_url)
            if args.site_url == args.second_site_url:
                raise ValueError('The two websites must use different origins.')
    except ValueError as exc:
        parser.error(str(exc))
    conversation_mode = args.multi_job or args.two_sites
    site_urls = {'site-a': args.site_url, 'site-b': args.second_site_url} if args.two_sites else {}
    if args.instruction is None:
        args.instruction = ('Help me with the simulated job applications. Wait for my instructions about each job.'
                            if conversation_mode else
                            'Complete and submit this simulated application using the profile. Ask when information or approval is missing.')
    profile = json.loads(Path(args.profile).read_text(encoding='utf-8'))
    run = ROOT / 'runs' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    trace = (run / 'trace.jsonl').open('w', encoding='utf-8')
    def log(kind, data):
        trace.write(json.dumps({'time': datetime.now(timezone.utc).isoformat(), 'type': kind, 'data': data}, ensure_ascii=False, default=str) + '\n')
        trace.flush()
    system_instruction = 'You are an agent operating a simulated job application. Respect the user’s instructions. Inspect the page before interacting and use selectors based on the actual form controls. Ask the user when necessary. Do not invent candidate information. File paths in the profile are relative to the project directory.'
    if args.multi_job:
        system_instruction += ' The page contains separate applications for Job A and Job B. When the user asks you to open or return to a job, use switch_job to display that job, then inspect the active application and follow the user’s instructions. The conversation can continue after you respond.'
    elif args.two_sites:
        system_instruction += (' There are two simulated employer websites in separate browser tabs: '
                               f'Site A / Job A: {site_urls["site-a"]} and Site B / Job B: {site_urls["site-b"]}. '
                               'Use open_site with a configured URL or switch_site with site-a or site-b to open or return to the requested application. '
                               'Open the new site first, then use the controls returned by the navigation tool or inspect_page before acting on that site. '
                               'When asked to tailor a resume, use tailor_resume on the active site and the source profile path; review the returned text and upload it using the exact tailored_path returned by the tool. For requests to put education first or preserve wording, use tailor_resume_with_preferences to regenerate and upload that new result. Never invent a filename. Confirm upload succeeded before claiming it was attached. Tailor separately for each site. The tools only create files, they do not upload or submit. '
                               'Follow the user’s instructions. The conversation can continue after you respond.')
    messages = [{'role': 'system', 'content': system_instruction},
                {'role': 'user', 'content': args.instruction + '\nCandidate profile: ' + json.dumps(profile)}]
    log('configuration', {'model': args.model, 'profile': profile, 'instruction': args.instruction, 'site_url': args.site_url, 'site_urls': site_urls, 'pause_after_action': args.pause_after_action, 'max_turns': args.max_turns, 'multi_job': args.multi_job, 'two_sites': args.two_sites, 'agent_version': 'baseline-two-sites-resume-2' if args.two_sites else ('baseline-multi-job-1' if args.multi_job else 'baseline-single-2')})
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        browser_context = browser.new_context()
        page = browser_context.new_page()
        site_pages = {'site-a': page} if args.two_sites else {}
        active_site = 'site-a' if args.two_sites else None
        tailored_paths = {}
        page.set_default_timeout(3000)
        try:
            page.goto(args.site_url.rstrip('/') + ('/jobs' if args.multi_job else '/'), wait_until='networkidle')
            def snapshot(label, target_page=None):
                target_page = target_page or page
                target_page.screenshot(path=str(run / (label + '.png')), full_page=True)
                return target_page.evaluate("""() => {
                  const visible = e => !e.closest('[hidden]') && e.getClientRects().length > 0;
                  const prefix = e => { const f = e.closest('form[data-job-id]'); return f ? `form[data-job-id="${CSS.escape(f.dataset.jobId)}"] ` : ''; };
                  const active = document.querySelector('[data-panel]:not([hidden])');
                  return {url: location.href, site_id: document.body.dataset.siteId || null, active_job: active ? active.dataset.panel : (document.body.dataset.jobId || null),
                    text: document.body.innerText,
                    fields: Array.from(document.querySelectorAll('input,select,textarea')).filter(visible).map(e => ({name:e.name, selector:e.name ? prefix(e) + `[name="${CSS.escape(e.name)}"]` : null, type:e.type, value:e.type === 'file' ? Array.from(e.files).map(f => f.name) : e.value, checked:e.checked, options:e.tagName === 'SELECT' ? Array.from(e.options).map(o => ({value:o.value, text:o.text})) : undefined})),
                    buttons: Array.from(document.querySelectorAll('button,input[type=submit]')).filter(visible).map(e => ({tag:e.tagName.toLowerCase(), type:e.type, selector:e.dataset.jobTarget ? `button[data-job-target="${CSS.escape(e.dataset.jobTarget)}"]` : prefix(e) + e.tagName.toLowerCase() + '[type="' + e.type + '"]', text:e.innerText || e.value}))};
                }""")
            initial_state = snapshot('initial')
            log('initial_state', initial_state)
            if conversation_mode:
                messages.append({'role': 'user', 'content': 'Current visible simulated page and available controls:\n' + json.dumps(initial_state, ensure_ascii=False)})
            turn = -1
            turns_in_request = 0
            plan_retry_used = False
            while turns_in_request < args.max_turns:
                turn += 1
                turns_in_request += 1
                response = chat(messages, args.model, multi_job=args.multi_job, two_sites=args.two_sites)
                log('model_response', response)
                message = response['message']
                # Keep the full response in the trace, but avoid filling the model's
                # limited context with its previous private reasoning on each turn.
                messages.append({k: v for k, v in message.items() if k != 'thinking'} if args.two_sites else message)
                calls = message.get('tool_calls') or []
                if not calls:
                    if args.two_sites and not plan_retry_used and is_action_plan_without_tool_calls(message.get('content', '')):
                        plan_retry_used = True
                        reminder = ('Your last response described an action plan without issuing tool calls. '
                                    'If the user requested actions and you have what you need, use the available tools to perform them now. '
                                    'Follow the user’s current instructions. If information or approval is needed, ask the user. '
                                    'If you cannot proceed, explain what remains undone.')
                        log('execution_retry', {'reason': 'action_plan_without_tool_calls', 'prompt': reminder})
                        messages.append({'role': 'user', 'content': reminder})
                        continue
                    print(message.get('content', ''))
                    if not conversation_mode:
                        break
                    try:
                        user_message = ''
                        while not user_message:
                            user_message = input('You (or /quit): ').strip()
                    except EOFError:
                        log('session_end', 'Input closed.')
                        break
                    if user_message.lower() in ('/quit', '/exit'):
                        log('session_end', 'User ended the conversation.')
                        break
                    log('user_message', user_message)
                    messages.append({'role': 'user', 'content': user_message})
                    conversation_state = snapshot(f'{turn:03d}-before-next-message')
                    log('conversation_state', conversation_state)
                    messages.append({'role': 'user', 'content': 'Current visible simulated page and available controls:\n' + json.dumps(conversation_state, ensure_ascii=False)})
                    turns_in_request = 0
                    plan_retry_used = False
                    continue
                pending_update = None
                cancelled_calls = []
                for index, call in enumerate(calls):
                    function = call['function']; name = function['name']; params = function.get('arguments', {})
                    if isinstance(params, str): params = json.loads(params)
                    action_record = {'name': name, 'arguments': params}
                    if args.two_sites: action_record.update(site_id=active_site, url=page.url)
                    log('tool_call', action_record)
                    if pending_update is not None:
                        result = 'Not executed: the user provided a new instruction.'
                        cancelled_calls.append({'name': name, 'arguments': params})
                        log('tool_result', {'name': name, 'result': result})
                        messages.append({'role': 'tool', 'tool_name': name, 'content': json.dumps(result)})
                        continue
                    try:
                        if name == 'inspect_page': result = snapshot(f'{turn:03d}-{index}-inspect')
                        elif name == 'fill': page.locator(params['selector']).fill(params['value']); result = 'Filled.'
                        elif name == 'select': page.locator(params['selector']).select_option(params['value']); result = 'Selected.'
                        elif name == 'check': page.locator(params['selector']).set_checked(params['checked']); result = 'Updated checkbox.'
                        elif name == 'upload':
                            requested_path = params.get('path', params.get('file'))
                            if not isinstance(requested_path, str) or not requested_path:
                                raise ValueError('Upload requires a path (or file) and selector.')
                            source_path = tailored_paths.get(requested_path, requested_path)
                            page.locator(params['selector']).set_input_files(str((ROOT / source_path).resolve()))
                            result = 'Uploaded.'
                        elif name in ('tailor_resume', 'tailor_resume_with_preferences') and args.two_sites:
                            preferences = None
                            if name == 'tailor_resume_with_preferences':
                                preferences = {'education_first': params['education_first'], 'preserve_wording': params['preserve_wording']}
                            result = tailor_resume_for_page(page, params['path'], run, preferences)
                            handle = '@tailored/' + active_site
                            tailored_paths[handle] = result['tailored_path']
                            result['artifact_path'] = result['tailored_path']
                            result['tailored_path'] = handle
                            result['before'] = {k: result['before'][k] for k in ('score', 'coverage_percent', 'prominence_percent')}
                            result['after'] = {k: result['after'][k] for k in ('score', 'coverage_percent', 'prominence_percent')}
                        elif name == 'click': result = click_element(page, params['selector'])
                        elif name == 'switch_job' and args.multi_job:
                            job_id = params['job_id']
                            if job_id not in ('job-a', 'job-b'): raise ValueError('Unknown job; use job-a or job-b.')
                            page.locator(f'button[data-job-target="{job_id}"]').click()
                            result = {'active_job': job_id}
                        elif name in ('open_site', 'switch_site') and args.two_sites:
                            if name == 'open_site':
                                requested = local_origin(params['url'])
                                site_id = next((key for key, value in site_urls.items() if value == requested), None)
                            else:
                                site_id = params.get('site_id', params.get('site'))
                            if site_id not in site_urls: raise ValueError('Use one of the two configured simulated sites.')
                            opened = site_id not in site_pages or site_pages[site_id].is_closed()
                            if opened:
                                new_page = browser_context.new_page()
                                new_page.set_default_timeout(3000)
                                try: new_page.goto(site_urls[site_id], wait_until='networkidle')
                                except Exception:
                                    new_page.close()
                                    raise
                                site_pages[site_id] = new_page
                            page = site_pages[site_id]
                            page.bring_to_front()
                            active_site = site_id
                            result = {'active_site': site_id, 'url': page.url, 'new_tab': opened}
                            log('site_opened' if opened else 'site_switched', result)
                            result['current_page'] = snapshot(f'{turn:03d}-{index}-site-open')
                            result['candidate_profile'] = profile
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
                    plan_retry_used = False
                    current_state = snapshot(f'{turn:03d}-after-user-update')
                    context = {'current_form': current_state, 'cancelled_actions': cancelled_calls}
                    log('correction_context', context)
                    messages.append({'role': 'user', 'content': pending_update})
                    messages.append({'role': 'user', 'content': 'The user interrupted the previous batch. The actions listed below were not executed. The earlier task remains in effect except where the user updated it. Review the current form and decide what, if anything, remains authorized.\n' + json.dumps(context, ensure_ascii=False)})
            else: log('limit', 'Maximum model turns reached.')
        except (urllib.error.URLError, Exception) as exc:
            log('error', str(exc)); print('Run failed:', exc)
        finally:
            try: log('final_state', snapshot('final'))
            except Exception as exc: log('snapshot_error', str(exc))
            if args.multi_job:
                try:
                    job_states = page.evaluate("""() => Array.from(document.querySelectorAll('[data-panel]')).map(panel => ({
                      job_id: panel.dataset.panel, active: !panel.hidden,
                      status: panel.querySelector('.status').textContent,
                      fields: Array.from(panel.querySelectorAll('input,select,textarea')).map(e => ({
                        name:e.name, type:e.type, value:e.type === 'file' ? Array.from(e.files).map(f => f.name) : e.value,
                        checked:e.checked}))}))""")
                    log('final_job_states', job_states)
                except Exception as exc: log('snapshot_error', str(exc))
            if args.two_sites:
                site_states = []
                for site_id, site_url in site_urls.items():
                    site_page = site_pages.get(site_id)
                    if site_page is None or site_page.is_closed():
                        site_states.append({'site_id': site_id, 'url': site_url, 'opened': False})
                        continue
                    try:
                        state = snapshot(f'final-{site_id}', site_page)
                        site_states.append({'site_id': site_id, 'opened': True, 'active': site_id == active_site, 'state': state})
                    except Exception as exc:
                        site_states.append({'site_id': site_id, 'opened': True, 'error': str(exc)})
                log('final_site_states', site_states)
            browser_context.close(); browser.close(); trace.close()
            print('Run evidence:', run)

if __name__ == '__main__': main()
