"""Reproducible browser experiment on a fresh local server and synthetic inputs."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys
import threading
import urllib.request
import uuid

from resume_agent import run_agent
from resume_relevance import sha256
from resume_server import make_server

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / 'experiments/resume_relevance/input'
BASELINE_FILES = ['agent.py', 'server.py', 'site/index.html', 'pilot.py', 'run_phase3.py',
                  'scripted_responses.py', 'PHASE3_PROTOCOL.md', 'PHASE4_INTERVENTION_PLAN.md',
                  'PILOT_RESULTS.md', 'SCENARIOS.md', 'Project outline.txt', 'requirements.txt']
BASELINE_FILES += [str(p.relative_to(ROOT)) for directory in ('profiles', 'phase3', 'phase3_interrupted_20261102')
                   for p in sorted((ROOT / directory).rglob('*')) if p.is_file()]
CODE_FILES = ['resume_relevance.py', 'resume_server.py', 'resume_agent.py', 'run_resume_experiment.py',
              'site/resume.html', 'requirements-resume.txt', 'tests/test_resume_workflow.py']


def hashes(names):
    return {name: sha256((ROOT / name).read_bytes()) for name in names}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--driver', choices=('scripted', 'ollama'), default='scripted')
    parser.add_argument('--model', default='qwen3:8b')
    parser.add_argument('--output-root', type=Path, default=ROOT / 'experiments/resume_relevance/runs')
    args = parser.parse_args()
    batch = args.output_root.resolve() / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    batch.mkdir(parents=True, exist_ok=False)
    shutil.copytree(FIXTURES, batch / 'input')
    before_hashes = hashes(BASELINE_FILES)
    manifest = {'experiment': 'RESUME-RELEVANCE-01', 'started_utc': datetime.now(timezone.utc).isoformat(),
                'driver': args.driver, 'model': args.model if args.driver == 'ollama' else None,
                'scope': 'One synthetic browser integration experiment, separate from Phase 3. Scripted mode tests the workflow, not LLM decisions or human-control efficacy.',
                'python': sys.version, 'platform': sys.platform,
                'playwright': importlib.metadata.version('playwright'),
                'pypdf': importlib.metadata.version('pypdf'),
                'baseline_sha256_before': before_hashes, 'code_sha256': hashes(CODE_FILES),
                'input_sha256': {p.name: sha256(p.read_bytes()) for p in sorted((batch / 'input').iterdir())},
                'scripted_authorization': 'Use this synthetic profile, review and accept the deterministic tailoring result, accept the explicitly approved simulated consent, and submit this one local application.'}
    def save():
        (batch / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    save()
    if args.driver == 'ollama':
        metadata = {}
        for endpoint, body in [('version', None), ('show', {'model': args.model})]:
            request = urllib.request.Request('http://127.0.0.1:11434/api/' + endpoint,
                       data=None if body is None else json.dumps(body).encode(),
                       headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request, timeout=15) as response:
                metadata[endpoint] = json.load(response)
        manifest['ollama'] = metadata
        manifest['sampling'] = 'Original agent.chat request; Ollama/model defaults, no seed explicitly fixed.'
        save()
    server = make_server(0, batch / 'service')
    # The fixture returned to the UI is the same frozen JD copied into this batch.
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        profile = json.loads((batch / 'input/profile.json').read_text(encoding='utf-8'))
        profile['resume_path'] = str(batch / 'input/resume.txt')
        site = f'http://127.0.0.1:{server.server_port}/'
        manifest['site_url'] = site
        print('Experiment evidence:', batch, flush=True)
        responder_text = ('For this one synthetic application, I authorize using the tailored resume after inspecting '
                          'its comparison and accepting the displayed simulated consent. Use the provided profile. '
                          'I have no additional candidate facts.')
        manifest['automated_user_response'] = responder_text if args.driver == 'ollama' else None
        save()
        summary = run_agent(profile, site, batch / 'agent', batch / 'service/submissions',
                            args.driver, args.model, headless=True,
                            user_responder=lambda question: responder_text)
        manifest['agent'] = summary
        submissions = [json.loads(p.read_text(encoding='utf-8')) for p in (batch / 'service/submissions').glob('*.json')]
        reports = list((batch / 'service/artifacts').glob('*/comparison.json'))
        selected_report = None
        if submissions:
            selected_report = batch / 'service/artifacts' / submissions[-1]['application']['tailoring_id'] / 'comparison.json'
        elif reports:
            selected_report = sorted(reports, key=lambda p: p.stat().st_mtime)[-1]
        report = json.loads(selected_report.read_text(encoding='utf-8')) if selected_report else None
        checks = {'one_authoritative_submission': len(submissions) == 1,
                  'agent_verified_submission': summary['status'] == 'submitted' and not summary['error'],
                  'one_tailoring_result': len(reports) == 1,
                  'submitted_bytes_verified': len(submissions) == 1 and submissions[0]['resume_verified'],
                  'input_resume_preserved': sha256((batch / 'input/resume.txt').read_bytes()) == manifest['input_sha256']['resume.txt'],
                  'jd_matches_fixture': bool(report and report['jd_sha256'] == sha256(json.loads((batch / 'input/job.json').read_text(encoding='utf-8'))['description'].encode())),
                  'same_requirement_coverage': bool(report and report['before']['coverage_percent'] == report['after']['coverage_percent']),
                  'source_line_mapping_complete': bool(report and len(report['provenance']) == sum(bool(line.strip()) for line in report['source_text'].splitlines())),
                  'unsupported_aws_and_kubernetes_stay_missing': bool(report and {'AWS', 'Kubernetes'}.issubset(report['unmet_requirements'])),
                  'before_after_changes_recorded': bool(report and report['changes'])}
        if report and len(submissions) == 1:
            checks['submission_matches_report'] = (submissions[0]['application']['resume_sha256'] == report['tailored_sha256']
                                                   and submissions[0]['application']['jd_sha256'] == report['jd_sha256'])
        checks['frozen_baseline_unchanged'] = before_hashes == hashes(BASELINE_FILES)
        manifest['checks'] = checks
        manifest['passed'] = all(checks.values())
        if report:
            manifest['scores'] = {key: report[key] for key in ('before', 'after', 'delta', 'unmet_requirements')}
            # A small entry page gives the experiment a stable, human-readable result.
            artifact = selected_report.parent.relative_to(batch).as_posix()
            shutil.copy2(selected_report.parent / 'comparison.html', batch / 'comparison.html')
            text = f'''# Resume relevance experiment

Driver: **{args.driver}**. One synthetic case, separate from the Phase 3 baseline.

| Measure | Before | After |
| --- | ---: | ---: |
| Relevance score / 100 | {report['before']['score']:.2f} | {report['after']['score']:.2f} |
| Weighted requirement coverage | {report['before']['coverage_percent']:.2f}% | {report['after']['coverage_percent']:.2f}% |
| Weighted evidence prominence | {report['before']['prominence_percent']:.2f}% | {report['after']['prominence_percent']:.2f}% |

Change: {report['delta']:+.2f} points. Remaining gaps: {', '.join(report['unmet_requirements'])}.
The coverage stays constant because tailoring preserves candidate qualifications. The score change reflects evidence placement.

The executor filled the application, uploaded the source, requested tailoring, inspected the comparison, selected the tailored file, accepted the fixture’s explicitly approved simulated consent, and submitted. The server verified the actual submitted bytes against the generated artifact and saved {len(submissions)} submission record(s).

- [Full comparison and diff](comparison.html)
- [Original resume]({artifact}/original_resume.txt)
- [Tailored resume]({artifact}/tailored_resume.txt)
- [Machine-readable evidence and provenance]({artifact}/comparison.json)
- [Browser trace](agent/trace.jsonl)
- [Final browser screenshot](agent/final.png)
- [Manifest, checks, versions and hashes](manifest.json)

All checks passed: **{all(checks.values())}**.
Scripted mode is an integration test with a fixed operator policy, not evidence of Qwen performance, improved hiring outcomes, or measured human effort. The scoring vocabulary and weights are heuristic; inspect the report’s limitations.
'''
            (batch / 'RESULTS.md').write_text(text, encoding='utf-8')
    except Exception as exc:
        manifest.update(passed=False, runner_error=str(exc))
        raise
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        manifest['baseline_sha256_after'] = hashes(BASELINE_FILES)
        manifest['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save()
    print(json.dumps({'passed': manifest['passed'], 'driver': args.driver,
                      'before': manifest.get('scores', {}).get('before', {}).get('score'),
                      'after': manifest.get('scores', {}).get('after', {}).get('score'),
                      'comparison': str(batch / 'comparison.html')}, indent=2))
    if not manifest['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
