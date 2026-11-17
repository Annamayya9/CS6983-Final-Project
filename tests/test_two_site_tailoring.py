"""Check job-specific artifacts and the bytes actually submitted to both sites."""
import hashlib
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


class TailoringIntegrationTests(unittest.TestCase):
    def test_per_site_tailoring_upload_and_submission_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = Path(__file__).resolve().parents[1]
            shutil.copytree(source_root / 'site', root / 'site')
            (root / 'resume.txt').write_text('Alex Example\nExperience\n- Built Python APIs.\n- Used SQL for data analysis.\nEducation\nBS Computer Science\n', encoding='utf-8')
            old_root, old_output = two_site_server.ROOT, two_site_server.OUTPUT
            two_site_server.ROOT, two_site_server.OUTPUT = root, root / 'submissions'
            servers = [two_site_server.ThreadingHTTPServer(('127.0.0.1', 0), two_site_server.make_handler(*spec))
                       for spec in [('site-a', 'job-a', 'site_a.html'), ('site-b', 'job-b', 'site_b.html')]]
            threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
            for thread in threads: thread.start()
            try:
                with sync_playwright() as playwright, patch.object(agent, 'ROOT', root):
                    browser = playwright.chromium.launch(headless=True)
                    context = browser.new_context()
                    pages = [context.new_page(), context.new_page()]
                    for page, server in zip(pages, servers):
                        page.goto(f'http://127.0.0.1:{server.server_port}/')
                    artifacts = [agent.tailor_resume_for_page(page, 'resume.txt', root / 'run') for page in pages]
                    self.assertNotEqual(artifacts[0]['jd_sha256'], artifacts[1]['jd_sha256'])
                    self.assertNotEqual(artifacts[0]['tailored_path'], artifacts[1]['tailored_path'])
                    for result, site in zip(artifacts, ('site-a', 'site-b')):
                        self.assertEqual(result['site_id'], site)
                        self.assertEqual(hashlib.sha256(Path(result['tailored_path']).read_bytes()).hexdigest(), result['tailored_sha256'])
                    corrected = agent.tailor_resume_for_page(pages[0], 'resume.txt', root / 'run',
                        {'education_first': True, 'preserve_wording': True})
                    self.assertNotEqual(corrected['tailored_path'], artifacts[0]['tailored_path'])
                    self.assertLess(corrected['tailored_text'].index('Education'), corrected['tailored_text'].index('Experience'))
                    self.assertTrue(Path(artifacts[0]['tailored_path']).is_file())
                    cases = [
                        (pages[0], artifacts[0], {'full_name':'Alex','email':'alex@example.test','education':'BS', 'experience':'Intern','experience_duration':'6 months'}, 'sponsorship','resume','consent'),
                        (pages[1], artifacts[1], {'candidate_name':'Alex','contact_email':'alex@example.test','qualification':'BS', 'work_history':'Intern','work_duration':'6 months'}, 'work_sponsorship','resume_file','processing_agreement'),
                    ]
                    for page, artifact, fields, sponsor, upload, consent in cases:
                        for name, value in fields.items(): page.locator(f'[name="{name}"]').fill(value)
                        page.locator(f'[name="{sponsor}"]').select_option('no')
                        page.locator(f'[name="{upload}"]').set_input_files(artifact['tailored_path'])
                        page.locator(f'[name="{consent}"]').check()
                        outcome = agent.click_element(page, 'button[type="submit"]')
                        self.assertEqual(outcome['submission'], 'recorded')
                        record = json.loads((two_site_server.OUTPUT / (outcome['reference'] + '.json')).read_text(encoding='utf-8'))
                        self.assertEqual(record['site_id'], artifact['site_id'])
                        self.assertEqual(record['resume_sha256'], artifact['tailored_sha256'])
                        self.assertNotIn('resume_content_base64', record['application'])
                    context.close(); browser.close()
            finally:
                for server in servers: server.shutdown(); server.server_close()
                for thread in threads: thread.join()
                two_site_server.ROOT, two_site_server.OUTPUT = old_root, old_output


if __name__ == '__main__': unittest.main()
