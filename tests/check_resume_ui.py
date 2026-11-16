"""Real-browser checks for comparison, download, review invalidation and mobile layout."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from resume_relevance import sha256
from resume_server import make_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'runs/resume_ui_checks' /
                        (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]))
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    server = make_server(0, out / 'service')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    checks = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            page.goto(f'http://127.0.0.1:{server.server_port}', wait_until='networkidle')
            page.wait_for_function("document.querySelector('#jd').value.length > 0")
            source = ROOT / 'experiments/resume_relevance/input/resume.txt'
            page.locator('#resume').set_input_files(str(source))
            with page.expect_response('**/api/tailor') as pending:
                page.locator('#tailor').click()
            result = pending.value.json()
            page.locator('#comparison').wait_for(state='visible')
            checks['scores_displayed'] = (page.locator('#before-score').inner_text() == '76.95'
                                          and page.locator('#after-score').inner_text() == '84.33')
            checks['gaps_displayed'] = page.locator('#gaps').inner_text() == 'Kubernetes, AWS'
            checks['submit_disabled_until_accepted'] = page.locator('#submit').is_disabled()
            with page.expect_download() as pending_download:
                page.locator('#download').click()
            pending_download.value.save_as(str(out / 'downloaded_resume.txt'))
            checks['download_matches_artifact'] = sha256((out / 'downloaded_resume.txt').read_bytes()) == result['report']['tailored_sha256']
            page.locator('#use-tailored').click()
            checks['accepted_file_selected'] = page.locator('#resume').evaluate('e=>e.files[0].name') == 'tailored_resume.txt'
            checks['submit_enabled_after_acceptance'] = page.locator('#submit').is_enabled()
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('#comparison').evaluate('e=>e.scrollIntoView({block:"start"})')
            page.wait_for_timeout(150)
            page.screenshot(path=str(out / 'mobile-comparison.png'))
            checks['mobile_has_no_page_overflow'] = page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
            page.locator('#jd').fill(page.locator('#jd').input_value() + '\nPreferred: Excel.')
            checks['jd_change_invalidates_review'] = page.locator('#comparison').is_hidden() and page.locator('#submit').is_disabled()
            page.locator('#resume').set_input_files(str(source))
            page.locator('#tailor').click()
            page.locator('#comparison').wait_for(state='visible')
            checks['reanalyzed_changed_jd'] = 'Excel' in page.locator('#gaps').inner_text()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    (out / 'ui_checks.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
    print(json.dumps(checks, indent=2))
    print('UI evidence:', out)
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
