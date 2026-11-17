"""Re-grade SimApply run folders from their trajectories with the current grader (evaluation/form_cases.py).

The original reward.json / metric_evidence.json are kept as reward.recorded.json / metric_evidence.recorded.json
when the values change, and batch manifests are updated. Usage: python evaluation/regrade_form_runs.py
"""
import hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.form_cases import CASES, grade, load_case  # noqa: E402

grader = hashlib.sha256((ROOT / 'evaluation/form_cases.py').read_bytes()).hexdigest()
for name, folder in CASES.items():
    case = load_case(name)
    profile = json.loads((folder / 'input/profile.json').read_text())
    for run in sorted(p.parent for p in (folder / 'results').rglob('trajectory.json')):
        old = json.loads((run / 'reward.json').read_text())
        events = json.loads((run / 'trajectory.json').read_text())['events']
        reward, evidence = grade(case, events, profile, old['elapsed_seconds'])
        if reward != old:
            if not (run / 'reward.recorded.json').exists():
                (run / 'reward.json').rename(run / 'reward.recorded.json')
                (run / 'metric_evidence.json').rename(run / 'metric_evidence.recorded.json')
            evidence['regraded_with_form_cases_sha256'] = grader
            (run / 'reward.json').write_text(json.dumps(reward, indent=2))
            (run / 'metric_evidence.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False, default=str))
            changed = {k: (old.get(k), v) for k, v in reward.items() if old.get(k) != v}
            print(run.relative_to(ROOT), changed)
    for batch in (folder / 'results').rglob('batch-*.json'):
        data = json.loads(batch.read_text())
        for entry in data['runs']:
            r = batch.parent / entry['directory'] / 'reward.json'
            if r.exists():
                entry['reward'] = json.loads(r.read_text())
        batch.write_text(json.dumps(data, indent=2))
