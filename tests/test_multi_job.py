"""End-to-end checks for two applications in one browser and conversation."""
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
import server
from playwright.sync_api import sync_playwright


def call(name, **arguments):
    return {'function': {'name': name, 'arguments': arguments}}


def response(*calls, content=''):
    return {'message': {'role': 'assistant', 'content': content, 'tool_calls': list(calls)}}


class MultiJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        source = Path(__file__).resolve().parents[1]
        shutil.copytree(source / 'site', cls.root / 'site')
        shutil.copytree(source / 'profiles', cls.root / 'profiles')
        cls.original_root, cls.original_output = server.ROOT, server.OUTPUT
        server.ROOT, server.OUTPUT = cls.root, cls.root / 'submissions'
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.http.server_port}/'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.http.server_close(); cls.thread.join()
        server.ROOT, server.OUTPUT = cls.original_root, cls.original_output
        cls.temp.cleanup()

    def test_forms_keep_independent_fields_files_and_submission_records(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(self.url + 'jobs')
            def fill_job(job, salary, email):
                form = page.locator(f'form[data-job-id="{job}"]')
                for name, value in {'full_name':'Alex Example','email':email,'education':'BS',
                                    'experience':'Intern','experience_duration':'6 months',
                                    'salary_expectation':salary}.items():
                    form.locator(f'[name="{name}"]').fill(value)
                form.locator('[name="sponsorship"]').select_option('no')
                form.locator('[name="resume"]').set_input_files(str(self.root / 'profiles/sample_resume.txt'))
                form.locator('[name="consent"]').check()
                return form

            form_a = fill_job('job-a', '80000', 'a@example.test')
            page.locator('button[data-job-target="job-b"]').click()
            form_b = page.locator('form[data-job-id="job-b"]')
            self.assertEqual(form_b.locator('[name="salary_expectation"]').input_value(), '')
            self.assertFalse(form_b.locator('[name="consent"]').is_checked())
            self.assertEqual(form_b.locator('[name="resume"]').evaluate('e => e.files.length'), 0)
            fill_job('job-b', '90000', 'b@example.test')
            b_result = agent.click_element(page, 'form[data-job-id="job-b"] button[type="submit"]')
            self.assertEqual(b_result['submission'], 'recorded')
            page.locator('button[data-job-target="job-a"]').click()
            self.assertEqual(form_a.locator('[name="salary_expectation"]').input_value(), '80000')
            self.assertEqual(form_a.locator('[name="resume"]').evaluate('e => e.files[0].name'), 'sample_resume.txt')
            self.assertTrue(form_a.locator('[name="consent"]').is_checked())
            self.assertEqual(page.locator('[data-panel="job-a"] .status').inner_text(), '')
            a_result = agent.click_element(page, 'form[data-job-id="job-a"] button[type="submit"]')
            self.assertEqual(a_result['submission'], 'recorded')
            for result, job, salary, email in [(a_result,'job-a','80000','a@example.test'),
                                                (b_result,'job-b','90000','b@example.test')]:
                record = json.loads((server.OUTPUT / (result['reference'] + '.json')).read_text(encoding='utf-8'))
                self.assertEqual(record['job_id'], job)
                self.assertEqual(record['application']['job_id'], job)
                self.assertEqual(record['application']['salary_expectation'], salary)
                self.assertEqual(record['application']['email'], email)
            browser.close()

    def test_conversation_keeps_prior_messages_and_switches_jobs(self):
        responses = iter([
            response(call('fill', selector='form[data-job-id="job-a"] [name="salary_expectation"]', value='80000')),
            response(content='Job A updated.'),
            response(call('switch_job', job_id='job-b'),
                     call('fill', selector='form[data-job-id="job-b"] [name="salary_expectation"]', value='90000')),
            response(content='Job B updated.'),
            response(call('switch_job', job_id='job-a'),
                     call('fill', selector='form[data-job-id="job-a"] [name="salary_expectation"]', value='85000')),
            response(content='Job A corrected.'),
        ])
        history = []
        def fake_chat(messages, model, multi_job=False, two_sites=False):
            history.append(json.loads(json.dumps(messages)))
            return next(responses)
        inputs = iter(['Now set Job B salary to 90000.', 'Return to Job A and change it to 85000.', '/quit'])
        args = ['agent.py', '--profile', str(self.root / 'profiles/sample.json'), '--headless', '--multi-job',
                '--instruction', 'Set Job A salary to 80000.', '--max-turns', '2']
        with patch.object(agent, 'ROOT', self.root), patch.object(agent, 'SITE_URL', self.url), \
             patch.object(agent, 'chat', side_effect=fake_chat), patch('builtins.input', side_effect=lambda _: next(inputs)), \
             patch.object(sys, 'argv', args):
            agent.main()
        last_history = history[-1]
        user_messages = [m['content'] for m in last_history if m['role']=='user']
        self.assertTrue(any('Job A salary to 80000' in x for x in user_messages))
        self.assertIn('Now set Job B salary to 90000.', user_messages)
        self.assertIn('Return to Job A and change it to 85000.', user_messages)
        trace = max((self.root / 'runs').glob('*/trace.jsonl'), key=lambda p:p.stat().st_mtime_ns)
        events = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
        self.assertEqual([e['data'] for e in events if e['type']=='user_message'],
                         ['Now set Job B salary to 90000.', 'Return to Job A and change it to 85000.'])
        final = next(e['data'] for e in events if e['type']=='final_state')
        self.assertEqual(final['active_job'], 'job-a')
        self.assertEqual(next(f['value'] for f in final['fields'] if f['name']=='salary_expectation'), '85000')
        states = {item['job_id']:item for item in next(e['data'] for e in events if e['type']=='final_job_states')}
        self.assertEqual(next(f['value'] for f in states['job-a']['fields'] if f['name']=='salary_expectation'), '85000')
        self.assertEqual(next(f['value'] for f in states['job-b']['fields'] if f['name']=='salary_expectation'), '90000')
        self.assertFalse(any(e['type']=='limit' for e in events))
        self.assertTrue(any(e['type']=='state' and e['data']['active_job']=='job-b' and
                            any(f['name']=='salary_expectation' and f['value']=='90000' for f in e['data']['fields'])
                            for e in events))


if __name__ == '__main__': unittest.main()
