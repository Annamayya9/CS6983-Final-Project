"""Exercise browser validation and interruption using an isolated local site."""
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


class CorrectionFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        shutil.copytree(Path(__file__).resolve().parents[1] / 'site', cls.root / 'site')
        shutil.copytree(Path(__file__).resolve().parents[1] / 'profiles', cls.root / 'profiles')
        cls.original_server_root, cls.original_output = server.ROOT, server.OUTPUT
        server.ROOT, server.OUTPUT = cls.root, cls.root / 'submissions'
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.http.server_port}/'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        server.ROOT, server.OUTPUT = cls.original_server_root, cls.original_output
        cls.temp.cleanup()

    def test_submit_click_distinguishes_blocked_from_recorded(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(self.url)
            blocked = agent.click_element(page, 'button[type="submit"]')
            self.assertEqual(blocked['submission'], 'blocked_by_form_validation')
            self.assertIn('full_name', [field['name'] for field in blocked['invalid_fields']])
            for name, value in {'full_name':'Alex Example', 'email':'alex@example.test',
                                'education':'BS', 'experience':'Intern', 'experience_duration':'6 months'}.items():
                page.locator(f'[name="{name}"]').fill(value)
            page.locator('[name="sponsorship"]').select_option('no')
            page.locator('[name="consent"]').check()
            result = agent.click_element(page, 'button[type="submit"]')
            self.assertEqual(result['submission'], 'recorded')
            record = json.loads((server.OUTPUT / (result['reference'] + '.json')).read_text(encoding='utf-8'))
            self.assertEqual(record['application']['email'], 'alex@example.test')
            browser.close()

    def run_interrupted(self, update, complete):
        first = response(call('fill', selector='[name="email"]', value='wrong@example.test'),
                         call('click', selector='button[type="submit"]'))
        remaining = [call('fill', selector='[name="email"]', value='alex@example.test')]
        if complete:
            remaining += [call('fill', selector='[name="full_name"]', value='Alex Example'),
                          call('fill', selector='[name="education"]', value='BS'),
                          call('fill', selector='[name="experience"]', value='Intern'),
                          call('fill', selector='[name="experience_duration"]', value='6 months'),
                          call('select', selector='[name="sponsorship"]', value='no'),
                          call('upload', selector='[name="resume"]', path='profiles/sample_resume.txt'),
                          call('check', selector='[name="consent"]', checked=True),
                          call('click', selector='button[type="submit"]')]
        responses = iter([first, response(*remaining), response(content='Finished.')])
        captured = []
        def fake_chat(messages, model, multi_job=False, two_sites=False):
            captured.append(json.loads(json.dumps(messages)))
            return next(responses)
        answers = iter([update] + [''] * 20)
        args = ['agent.py', '--profile', str(self.root / 'profiles/sample.json'), '--headless', '--pause-after-action']
        with patch.object(agent, 'ROOT', self.root), patch.object(agent, 'SITE_URL', self.url), \
             patch.object(agent, 'chat', side_effect=fake_chat), patch('builtins.input', side_effect=lambda _: next(answers)), \
             patch.object(sys, 'argv', args):
            agent.main()
        trace = max((self.root / 'runs').glob('*/trace.jsonl'), key=lambda path: path.stat().st_mtime_ns)
        events = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
        return captured, events

    def test_cancelled_actions_are_reported_and_replanned(self):
        captured, events = self.run_interrupted('Correction: my email is alex@example.test.', True)
        context = next(e['data'] for e in events if e['type'] == 'correction_context')
        self.assertEqual(context['cancelled_actions'][0]['name'], 'click')
        self.assertEqual(next(f['value'] for f in context['current_form']['fields'] if f['name']=='email'), 'wrong@example.test')
        self.assertIn('cancelled_actions', captured[1][-1]['content'])
        click_results = [e['data']['result'] for e in events if e['type']=='tool_result' and e['data']['name']=='click']
        self.assertIn('Not executed', click_results[0])
        self.assertEqual(click_results[-1]['submission'], 'recorded')
        record = json.loads((server.OUTPUT / (click_results[-1]['reference'] + '.json')).read_text(encoding='utf-8'))
        self.assertEqual(record['application']['email'], 'alex@example.test')

    def test_new_no_submit_instruction_cancels_queued_submission(self):
        _, events = self.run_interrupted('Correct my email to alex@example.test, and do not submit.', False)
        self.assertTrue(any(e['type']=='user_intervention' and 'do not submit' in e['data'] for e in events))
        results = [e['data']['result'] for e in events if e['type']=='tool_result' and e['data']['name']=='click']
        self.assertEqual(len(results), 1)
        self.assertIn('Not executed', results[0])
        final = next(e['data'] for e in events if e['type']=='final_state')
        self.assertEqual(next(f['value'] for f in final['fields'] if f['name']=='email'), 'alex@example.test')
        self.assertNotIn('Submitted. Reference:', final['text'])


if __name__ == '__main__': unittest.main()
