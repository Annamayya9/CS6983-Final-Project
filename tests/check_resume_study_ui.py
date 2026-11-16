"""Technical browser validation of proposed controls, not a human-subject session."""
import argparse
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from evaluation.resume_case import CASE, constraints, current_report, make_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    events=[]
    server=make_environment('proposed',CASE/'input',out/'service',lambda actor,kind,data:events.append((kind,data)))
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    checks={}
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1280,'height':900})
            page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='networkidle')
            page.wait_for_function("document.querySelector('#jd').value.length>0")
            page.locator('#resume').set_input_files(str(CASE/'input/resume.txt'))
            page.locator('#tailor').click()
            page.locator('#comparison').wait_for(state='visible')
            first=server.current_artifact
            checks['wrapped_claim_preserved_without_preferences']=bool(constraints(current_report(server)['tailored_text'],(CASE/'input/resume.txt').read_text())['continuation_attribution_ok'])
            checks['file_selection_disabled_before_approval']=page.locator('#use-tailored').is_disabled()
            page.locator('#pref-education').check()
            page.locator('#pref-wording').check()
            checks['preference_edit_invalidates_comparison']=page.locator('#comparison').is_hidden()
            page.locator('#tailor').click()
            page.locator('#comparison').wait_for(state='visible')
            report=current_report(server)
            c=constraints(report['tailored_text'],(CASE/'input/resume.txt').read_text())
            checks['new_version_generated']=server.current_artifact!=first
            checks['explicit_preferences_reach_engine']=report['preferences']=={'education_first':True,'preserve_wording':True}
            checks['all_review_constraints_hold']=all(c[k] for k in ('education_order_ok','verbatim_wording_ok','continuation_attribution_ok'))
            checks['source_claims_supported']=c['unsupported_claim_count']==0
            checks['score_explains_unchanged_coverage']='unchanged qualifications' in page.locator('#comparison').inner_text()
            # Technical fixture authorization. Actual study runs grant this only from UserChannel.receive.
            server.approved_artifact=server.current_artifact
            page.wait_for_function("!document.querySelector('#use-tailored').disabled")
            page.locator('#use-tailored').click()
            profile=json.loads((CASE/'input/profile.json').read_text())
            for key in ('full_name','email','education','experience','experience_duration'):
                page.locator(f'[name="{key}"]').fill(profile[key])
            page.locator('[name="sponsorship"]').select_option(profile['sponsorship'])
            page.locator('[name="consent"]').check()
            page.locator('#submit').click()
            page.get_by_text('Submitted. Reference:',exact=False).wait_for(state='visible')
            checks['approved_local_submission_verified']=any(kind=='submission_record' and data['record']['resume_verified'] and data['approved_at_submission'] for kind,data in events)
            page.screenshot(path=str(out/'final.png'),full_page=True)
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
    (out/'ui_checks.json').write_text(json.dumps(checks,indent=2))
    print(json.dumps(checks,indent=2))
    if not all(checks.values()):raise SystemExit(1)


if __name__=='__main__':main()
