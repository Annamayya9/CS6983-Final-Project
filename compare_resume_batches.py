"""Summarize new study batches without overwriting the archived course report."""
import argparse
import json
from pathlib import Path
import statistics
from summarize_resume_study import load_batch

CORE = ('task_success', 'unauthorized_action_count', 'unsupported_claim_count', 'correction_adherence',
        'tool_error_count', 'user_message_count', 'agent_user_question_count', 'elapsed_seconds')


def summarize(rows):
    valid = [r for r in rows if r['reward']['run_valid']]
    applicable = [r for r in valid if r['reward']['correction_applicable']]
    return {'total_runs': len(rows), 'valid_runs': len(valid), 'inconclusive_runs': len(rows) - len(valid),
            'task_successes': sum(r['reward']['task_success'] for r in valid),
            'runs_with_unauthorized_actions': sum(r['reward']['unauthorized_action_count'] > 0 for r in valid),
            'runs_with_unsupported_claims': sum(r['reward']['unsupported_claim_count'] > 0 for r in valid),
            'correction_applicable_runs': len(applicable),
            'corrections_satisfied': sum(r['reward']['correction_adherence'] for r in applicable),
            'core_means': {k: round(statistics.mean(r['reward'][k] for r in (applicable if k == 'correction_adherence' else valid)), 3)
                           if (applicable if k == 'correction_adherence' else valid) else None for k in CORE}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline-batch', type=Path, required=True)
    p.add_argument('--proposed-batch', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        p.error('Choose a new output path to preserve earlier summaries.')
    batches, groups = [], []
    for path, condition in [(args.baseline_batch, 'baseline'), (args.proposed_batch, 'proposed')]:
        batch, rows = load_batch(path)
        if batch['condition'] != condition or not rows or batch['planned_trials'] != len(rows):
            p.error('Wrong condition or incomplete batch: ' + str(path))
        if any(r['config']['mode'] != 'simulated' for r in rows):
            p.error('This comparison is for objective simulated-user batches only.')
        batches.append(batch); groups.append(rows)
    by_seed = [{r['config']['agent_settings']['seed']: r['config'] for r in rows} for rows in groups]
    fields = ('input_sha256', 'initial_prompt', 'agent_system_prompt', 'simulator_system_prompt',
              'agent_driver', 'user_driver', 'agent_model', 'simulated_user_model',
              'agent_settings', 'user_settings', 'model_versions')
    matched = (by_seed[0].keys() == by_seed[1].keys() and all(
        all(by_seed[0][seed].get(k) == by_seed[1][seed].get(k) for k in fields) for seed in by_seed[0]))
    result = {'baseline_batch': str(args.baseline_batch.resolve()), 'proposed_batch': str(args.proposed_batch.resolve()),
              'matched_task_models_settings_and_seeds': matched,
              'baseline': summarize(groups[0]), 'proposed': summarize(groups[1]),
              'subjective_metrics_collected': False,
              'limitations': 'Audit actual user corrections before final reporting. Scripted smoke checks are technical validation only. Small samples do not estimate human perception or general performance.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
