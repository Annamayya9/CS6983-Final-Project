"""Integration checks for separate origins and tabs in one conversation."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent
import two_site_server
from playwright.sync_api import sync_playwright


def call(name, **arguments):
    return {'function': {'name': name, 'arguments': arguments}}


def response(*calls, content=''):
    return {'message': {'role': 'assistant', 'content': content, 'tool_calls': list(calls)}}


class TwoSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        source = Path(__file__).resolve().parents[1]
        shutil.copytree(source / 'site', cls.root / 'site')
        shutil.copytree(source / 'profiles', cls.root / 'profiles')
        cls.original_root, cls.original_output = two_site_server.ROOT, two_site_server.OUTPUT
        two_site_server.ROOT, two_site_server.OUTPUT = cls.root, cls.root / 'submissions'
        cls.servers = [two_site_server.ThreadingHTTPServer(('127.0.0.1', 0), two_site_server.make_handler(*spec))
                       for spec in [('site-a','job-a','site_a.html'), ('site-b','job-b','site_b.html')]]
        cls.threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in cls.servers]
        for thread in cls.threads: thread.start()
        cls.urls = [f'http://127.0.0.1:{s.server_port}/' for s in cls.servers]

    @classmethod
    def tearDownClass(cls):
        for s in cls.servers: s.shutdown(); s.server_close()
        for t in cls.threads: t.join()
        two_site_server.ROOT, two_site_server.OUTPUT = cls.original_root, cls.original_output
        cls.temp.cleanup()

    def test_separate_origins_tabs_drafts_and_submission_records(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            a, b = context.new_page(), context.new_page()
            a.goto(self.urls[0]); b.goto(self.urls[1])
            a.locator('[name="salary_expectation"]').fill('80000')
            a.locator('[name="resume"]').set_input_files(str(self.root / 'profiles/sample_resume.txt'))
            a.locator('[name="consent"]').check()
            self.assertFalse(b.locator('[name="processing_agreement"]').is_checked())
            self.assertEqual(b.locator('[name="desired_salary"]').input_value(), '')
            self.assertEqual(b.locator('[name="resume_file"]').evaluate('e => e.files.length'), 0)
            b.locator('[name="desired_salary"]').fill('90000')
            b.locator('[name="resume_file"]').set_input_files(str(self.root / 'profiles/sample_resume.txt'))
            b.locator('[name="processing_agreement"]').check()
            a.bring_to_front()
            self.assertEqual(a.locator('[name="salary_expectation"]').input_value(), '80000')
            self.assertEqual(a.locator('[name="resume"]').evaluate('e => e.files[0].name'), 'sample_resume.txt')
            self.assertEqual(b.locator('[name="desired_salary"]').input_value(), '90000')
            for page, values in [(a, {'full_name':'Alex Example','email':'a@example.test','education':'BS',
                                      'experience':'Intern','experience_duration':'6 months'}),
                                 (b, {'candidate_name':'Alex Example','contact_email':'b@example.test','qualification':'BS',
                                      'work_history':'Intern','work_duration':'6 months'})]:
                for name, value in values.items(): page.locator(f'[name="{name}"]').fill(value)
            a.locator('[name="sponsorship"]').select_option('no')
            b.locator('[name="work_sponsorship"]').select_option('no')
            result_a = agent.click_element(a, 'button[type="submit"]')
            result_b = agent.click_element(b, 'button[type="submit"]')
            self.assertEqual((result_a['submission'], result_b['submission']), ('recorded','recorded'))
            for result, site, salary_key, salary in [(result_a,'site-a','salary_expectation','80000'),
                                                      (result_b,'site-b','desired_salary','90000')]:
                record = json.loads((two_site_server.OUTPUT / (result['reference'] + '.json')).read_text(encoding='utf-8'))
                self.assertEqual(record['site_id'], site)
                self.assertEqual(result['site_id'], site)
                self.assertEqual(record['application'][salary_key], salary)
            context.close(); browser.close()

    def test_agent_retains_conversation_and_switches_between_real_tabs(self):
        first_response = response(call('fill', selector='[name="salary_expectation"]', value='80000'))
        first_response['message']['thinking'] = 'A previous internal reasoning block.'
        responses = iter([
            first_response,
            response(content='Site A updated.'),
            response(call('open_site', url=self.urls[1]), call('fill', selector='[name="desired_salary"]', value='90000')),
            response(content='Site B updated.'),
            response(call('switch_site', site_id='site-a'), call('fill', selector='[name="salary_expectation"]', value='85000')),
            response(content='Site A corrected.'),
        ])
        history = []
        def fake_chat(messages, model, multi_job=False, two_sites=False):
            self.assertTrue(two_sites)
            history.append(json.loads(json.dumps(messages)))
            return next(responses)
        inputs = iter(['Open site B and set salary to 90000.', 'Return to site A and change salary to 85000.', '/quit'])
        args = ['agent.py', '--profile', str(self.root / 'profiles/sample.json'), '--headless', '--two-sites',
                '--site-url', self.urls[0], '--second-site-url', self.urls[1],
                '--instruction', 'Set site A salary to 80000.', '--max-turns', '2']
        with patch.object(agent, 'ROOT', self.root), patch.object(agent, 'chat', side_effect=fake_chat), \
             patch('builtins.input', side_effect=lambda _: next(inputs)), patch.object(sys, 'argv', args):
            agent.main()
        user_messages = [m['content'] for m in history[-1] if m['role']=='user']
        self.assertTrue(any('Set site A salary to 80000' in x for x in user_messages))
        self.assertFalse(any('thinking' in m for m in history[-1] if m['role'] == 'assistant'))
        self.assertIn('Open site B and set salary to 90000.', user_messages)
        self.assertIn('Return to site A and change salary to 85000.', user_messages)
        navigation_results = [json.loads(m['content']) for m in history[-1]
                              if m.get('role') == 'tool' and m.get('tool_name') == 'open_site']
        self.assertEqual(navigation_results[0]['current_page']['site_id'], 'site-b')
        self.assertTrue(any(f['name'] == 'desired_salary' for f in navigation_results[0]['current_page']['fields']))
        self.assertEqual(navigation_results[0]['candidate_profile']['email'], 'alex@example.test')
        trace = max((self.root / 'runs').glob('*/trace.jsonl'), key=lambda p:p.stat().st_mtime_ns)
        events = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
        self.assertTrue(any(e['type']=='model_response' and e['data']['message'].get('thinking') for e in events))
        states = {x['site_id']:x for x in next(e['data'] for e in events if e['type']=='final_site_states')}
        self.assertTrue(states['site-a']['active'])
        self.assertFalse(states['site-b']['active'])
        for key, field, expected in [('site-a','salary_expectation','85000'), ('site-b','desired_salary','90000')]:
            self.assertEqual(next(f['value'] for f in states[key]['state']['fields'] if f['name']==field), expected)
            self.assertNotIn('Submitted. Reference:', states[key]['state']['text'])
        self.assertEqual(states['site-a']['state']['url'], self.urls[0])
        self.assertEqual(states['site-b']['state']['url'], self.urls[1])
        self.assertEqual([e['data']['active_site'] for e in events if e['type'] in ('site_opened','site_switched')], ['site-b','site-a'])
        self.assertFalse(any(e['type']=='limit' for e in events))

    def test_agent_rejects_unconfigured_site_without_opening_it(self):
        responses = iter([response(call('open_site', url='http://example.com/')), response(content='Cannot open that site.')])
        args = ['agent.py', '--profile', str(self.root / 'profiles/sample.json'), '--headless', '--two-sites',
                '--site-url', self.urls[0], '--second-site-url', self.urls[1], '--instruction', 'Open another site.']
        with patch.object(agent, 'ROOT', self.root), \
             patch.object(agent, 'chat', side_effect=lambda *a, **kw: next(responses)), \
             patch('builtins.input', return_value='/quit'), patch.object(sys, 'argv', args):
            agent.main()
        trace = max((self.root / 'runs').glob('*/trace.jsonl'), key=lambda p:p.stat().st_mtime_ns)
        events = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
        result = next(e['data']['result'] for e in events if e['type']=='tool_result' and e['data']['name']=='open_site')
        self.assertIn('Tool error:', result)
        self.assertFalse(any(e['type']=='site_opened' for e in events))
        states = {x['site_id']:x for x in next(e['data'] for e in events if e['type']=='final_site_states')}
        self.assertFalse(states['site-b']['opened'])

    def test_agent_can_upload_tailoring_handle(self):
        responses = iter([
            response(call('tailor_resume', path='profiles/sample_resume.txt')),
            response(call('upload', selector='[name="resume"]', file='@tailored/site-a')),
            response(call('tailor_resume_with_preferences', path='profiles/sample_resume.txt', education_first=True, preserve_wording=True)),
            response(call('upload', selector='[name="resume"]', path='@tailored/site-a')),
            response(content='Tailored résumé attached.'),
        ])
        args = ['agent.py', '--profile', str(self.root / 'profiles/sample.json'), '--headless', '--two-sites',
                '--site-url', self.urls[0], '--second-site-url', self.urls[1], '--instruction', 'Tailor and upload for Site A.']
        with patch.object(agent, 'ROOT', self.root), patch.object(agent, 'chat', side_effect=lambda *a, **kw: next(responses)), \
             patch('builtins.input', return_value='/quit'), patch.object(sys, 'argv', args):
            agent.main()
        trace = max((self.root / 'runs').glob('*/trace.jsonl'), key=lambda p:p.stat().st_mtime_ns)
        events = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
        results = [e['data'] for e in events if e['type'] == 'tool_result']
        self.assertEqual(results[0]['result']['tailored_path'], '@tailored/site-a')
        self.assertEqual(results[1]['result'], 'Uploaded.')
        self.assertNotEqual(results[0]['result']['artifact_path'], results[2]['result']['artifact_path'])
        self.assertEqual(results[3]['result'], 'Uploaded.')
        state = next(e['data'] for e in events if e['type'] == 'final_site_states')[0]['state']
        self.assertEqual(next(f['value'] for f in state['fields'] if f['name'] == 'resume'), ['tailored_resume.txt'])

    def test_plan_only_reply_is_retried_once_and_executes_tool(self):
        responses = iter([
            response(content="Here is the step-by-step action plan: fill the salary field."),
            response(call('fill', selector='[name="salary_expectation"]', value='80000')),
            response(content='The salary is set.'),
        ])
        args = ['agent.py', '--profile', str(self.root / 'profiles/sample.json'), '--headless', '--two-sites',
                '--site-url', self.urls[0], '--second-site-url', self.urls[1], '--instruction', 'Set salary to 80000.']
        with patch.object(agent, 'ROOT', self.root), patch.object(agent, 'chat', side_effect=lambda *a, **kw: next(responses)), \
             patch('builtins.input', return_value='/quit'), patch.object(sys, 'argv', args):
            agent.main()
        trace = max((self.root / 'runs').glob('*/trace.jsonl'), key=lambda p:p.stat().st_mtime_ns)
        events = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(sum(e['type'] == 'execution_retry' for e in events), 1)
        state = next(e['data'] for e in events if e['type'] == 'final_site_states')[0]['state']
        self.assertEqual(next(f['value'] for f in state['fields'] if f['name'] == 'salary_expectation'), '80000')

    def test_questions_and_ordinary_answers_do_not_trigger_plan_retry(self):
        self.assertFalse(agent.is_action_plan_without_tool_calls('Should I submit the application?'))
        self.assertFalse(agent.is_action_plan_without_tool_calls('The application has been submitted.'))
        self.assertTrue(agent.is_action_plan_without_tool_calls("I'll handle this step-by-step: upload the resume."))
        self.assertTrue(agent.is_action_plan_without_tool_calls('To proceed, follow these steps: switch to Site B.'))
        self.assertTrue(agent.is_action_plan_without_tool_calls("Here's the corrected approach: fill the required fields."))

    def test_repeated_plan_does_not_cause_unbounded_retry(self):
        responses = iter([response(content='Action plan: fill the application.'),
                          response(content='Action plan: fill the application.')])
        args = ['agent.py', '--profile', str(self.root / 'profiles/sample.json'), '--headless', '--two-sites',
                '--site-url', self.urls[0], '--second-site-url', self.urls[1], '--instruction', 'Fill the application.']
        with patch.object(agent, 'ROOT', self.root), patch.object(agent, 'chat', side_effect=lambda *a, **kw: next(responses)), \
             patch('builtins.input', return_value='/quit'), patch.object(sys, 'argv', args):
            agent.main()
        trace = max((self.root / 'runs').glob('*/trace.jsonl'), key=lambda p:p.stat().st_mtime_ns)
        events = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(sum(e['type'] == 'execution_retry' for e in events), 1)


if __name__ == '__main__': unittest.main()
