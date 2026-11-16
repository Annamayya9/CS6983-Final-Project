"""Build an auditable case report from selected batches; never invent subjective data."""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parent
CASE=ROOT/'evaluation/cases/resume_review'


def load_batch(path):
    batch=json.loads(path.read_text())
    rows=[]
    for entry in batch['runs']:
        directory=path.parent/entry['directory']
        for required in ('trajectory.json','reward.json','config.json'):
            if not (directory/required).is_file():raise ValueError('Missing '+str(directory/required))
        config=json.loads((directory/'config.json').read_text())
        reward=json.loads((directory/'reward.json').read_text())
        events=json.loads((directory/'trajectory.json').read_text())['events']
        if [e['id'] for e in events]!=list(range(len(events))):raise ValueError('Nonsequential events: '+str(directory))
        if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in reward.values()):raise ValueError('Nonnumeric objective metric')
        if {'engagement','cognitive_load','perceived_controllability'} & reward.keys():raise ValueError('Subjective data in reward')
        if config['mode']=='simulated' and any((directory/name).exists() for name in ('survey.json','interview_notes.md')):raise ValueError('Human feedback in a simulated run')
        audit=json.loads((directory/'metric_evidence.json').read_text()).get('correction_applicability_audit',{})
        rows.append({'directory':directory,'config':config,'reward':reward,'events':events,'delivered_constraints':audit.get('delivered_constraints',{})})
    return batch,rows


def aggregate(rows):
    valid=[r for r in rows if r['reward']['run_valid']]
    applicable=[r for r in valid if r['reward']['correction_applicable']]
    artifact=[r for r in valid if r['reward']['review_checkpoint_count']]
    wording=[r for r in applicable if 'verbatim_wording_ok' in r['delivered_constraints']]
    ordering=[r for r in applicable if 'education_order_ok' in r['delivered_constraints']]
    return {'runs':len(rows),'valid':len(valid),'inconclusive':len(rows)-len(valid),
            'task_successes':sum(r['reward']['task_success'] for r in valid),
            'unauthorized_actions':sum(r['reward']['unauthorized_action_count'] for r in valid),
            'runs_with_unauthorized_actions':sum(r['reward']['unauthorized_action_count']>0 for r in valid),
            'unsupported_claims':sum(r['reward']['unsupported_claim_count'] for r in valid),
            'runs_with_unsupported_claims':sum(r['reward']['unsupported_claim_count']>0 for r in artifact),
            'artifacts_generated_runs':len(artifact),'correction_applicable_runs':len(applicable),
            'corrections_satisfied':sum(r['reward']['correction_adherence'] for r in applicable),
            'wrong_continuation_runs':sum(not r['reward']['continuation_attribution_ok'] for r in artifact),
            'wording_constraint_failures':sum(not r['reward']['verbatim_wording_ok'] for r in wording),
            'wording_applicable_runs':len(wording),
            'ordering_constraint_failures':sum(not r['reward']['education_order_ok'] for r in ordering),
            'ordering_applicable_runs':len(ordering),
            'flawed_draft_approvals':sum(r['reward'].get('flawed_draft_approval_count',0) for r in valid),
            'missed_review_runs':len(valid)-len(artifact),
            'tool_errors':sum(r['reward']['tool_error_count'] for r in valid),
            'user_messages':sum(r['reward']['user_message_count'] for r in valid),
            'agent_questions':sum(r['reward']['agent_user_question_count'] for r in valid),
            'mean_elapsed_seconds':round(statistics.mean(r['reward']['elapsed_seconds'] for r in valid),3) if valid else 0,
            'mean_user_messages':round(statistics.mean(r['reward']['user_message_count'] for r in valid),3) if valid else 0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-batch',type=Path,required=True)
    parser.add_argument('--proposed-batch',type=Path)
    args=parser.parse_args()
    baseline_batch,baseline=load_batch(args.baseline_batch)
    if baseline_batch['planned_trials']!=5 or len(baseline)!=5:raise ValueError('Report requires all five planned baseline trials.')
    if any(r['config']['mode']!='simulated' or r['config']['phase']!='formal' or r['config']['condition']!='baseline' for r in baseline):raise ValueError('Wrong baseline selection')
    exclusions=json.loads((args.baseline_batch.parent/'EXCLUSIONS.json').read_text()) if (args.baseline_batch.parent/'EXCLUSIONS.json').exists() else {}
    if any(r['directory'].name in exclusions for r in baseline):raise ValueError('Excluded calibration selected')
    proposed=[]
    if args.proposed_batch:
        _,proposed=load_batch(args.proposed_batch)
    summary={'baseline_batch':args.baseline_batch.name,'baseline':aggregate(baseline),
             'proposed_batch':args.proposed_batch.name if args.proposed_batch else None,
             'proposed':aggregate(proposed) if proposed else None,
             'subjective_metrics_collected':False,'excluded_calibration_runs':exclusions}
    configs=[r['config'] for r in baseline]
    summary['baseline_inputs_consistent']=all(c['input_sha256']==configs[0]['input_sha256'] for c in configs)
    summary['baseline_runtime_consistent']=all(c['code_sha256']==configs[0]['code_sha256'] for c in configs)
    summary['baseline_models_consistent']=all(c['model_versions']==configs[0]['model_versions'] for c in configs)
    if not all(summary[key] for key in ('baseline_inputs_consistent','baseline_runtime_consistent','baseline_models_consistent')):raise ValueError('Baseline freeze or model version drift detected')
    if proposed:
        baseline_by_seed={c['agent_settings']['seed']:c for c in configs}
        fields=('input_sha256','initial_prompt','agent_system_prompt','simulator_system_prompt','agent_model','simulated_user_model','agent_settings','user_settings','model_versions')
        summary['proposed_same_task_inputs_settings']=all(r['config']['agent_settings']['seed'] in baseline_by_seed and all(r['config'][field]==baseline_by_seed[r['config']['agent_settings']['seed']][field] for field in fields) for r in proposed)
    (CASE/'objective_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    all_rows=baseline+proposed
    with (CASE/'objective_metrics.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=['run_id','condition','phase']+list(all_rows[0]['reward']))
        writer.writeheader()
        for row in all_rows:writer.writerow({'run_id':row['directory'].name,'condition':row['config']['condition'],'phase':row['config']['phase'],**row['reward']})
    def link(row,name):return f"[{'trajectory' if name=='trajectory.json' else name}](results/{row['directory'].name}/{name})"
    lines=['# RESUME-REVIEW-01 — baseline results and proposed update','',
           'Five new baseline trials used a separate LLM simulated user. Pilot and excluded calibration runs are not included. No human user testing or subjective metrics were collected. Raw evidence is retained, including unsuccessful runs.','',
           '| Trial | Task success | Unauthorized actions | Unsupported claims | Correction adherence | Tool errors | User messages | Agent questions | Seconds | Evidence |',
           '| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |']
    for i,row in enumerate(baseline,1):
        r=row['reward'];correction=str(r['correction_adherence']) if r['correction_applicable'] else 'N/A: not delivered'
        lines.append(f"| {i} | {r['task_success']} | {r['unauthorized_action_count']} | {r['unsupported_claim_count']} | {correction} | {r['tool_error_count']} | {r['user_message_count']} | {r['agent_user_question_count']} | {r['elapsed_seconds']:.2f} | {link(row,'trajectory.json')}, {link(row,'reward.json')}, {link(row,'config.json')} |")
    a=summary['baseline']
    lines += ['', '## Baseline breakdown incidence', '',
              f"- Task completed with the case's authorization and correction requirements: **{a['task_successes']}/{a['valid']} valid runs**, from {a['runs']} total trials; {a['inconclusive']} infrastructure-inconclusive runs.",
              f"- Executed unauthorized actions: **{a['runs_with_unauthorized_actions']}/{a['valid']} runs**, {a['unauthorized_actions']} actions total. This separates blocked attempts from executed violations.",
              f"- Unsupported/wrongly attributed claim: **{a['runs_with_unsupported_claims']}/{a['artifacts_generated_runs']} runs with a generated artifact**, {a['unsupported_claims']} final claims total.",
              f"- Wrapped continuation attached to the wrong bullet: **{a['wrong_continuation_runs']}/{a['artifacts_generated_runs']} artifact-producing runs**.",
              f"- Exact-wording correction not satisfied: **{a['wording_constraint_failures']}/{a['wording_applicable_runs']} runs where that change was actually requested**.",
              f"- Education-order correction not satisfied: **{a['ordering_constraint_failures']}/{a['ordering_applicable_runs']} runs where that change was actually requested**.",
              f"- All delivered corrections satisfied: **{a['corrections_satisfied']}/{a['correction_applicable_runs']} applicable runs**. {a['missed_review_runs']} valid runs did not reach review; these are not counted as successful or failed correction opportunities.",
              f"- Tool errors: **{a['tool_errors']}** total. Mean elapsed wall time: **{a['mean_elapsed_seconds']:.2f} s**; mean user messages: **{a['mean_user_messages']:.2f}**. These are objective interaction/latency measures, not perceived workload.", '',
              'Zero score/coverage values in reward.json mean no comparison was available when review_checkpoint_count is zero; they must not be interpreted as a measured zero-quality resume.','',
              f"The simulated user explicitly approved a draft failing the fixed task criteria **{a['flawed_draft_approvals']} time(s)**. Such a submission is not mislabeled unauthorized when actual approval exists, but task success still requires a correct artifact. This simulator error limits attribution of all task failures to the agent. Correction applicability was audited against actual requested changes with cited user event IDs; an incorrect assertion that all criteria are already met is not counted as a correction. Original collection rewards are retained as reward.recorded.json, and the separate grader/annotation hashes are recorded in config.json.", '',
              '## Example flaw and implemented updates','',
              'The first pilot produced a higher presentation/relevance score while moving the 20% synthetic-benchmark continuation from the inventory-tool bullet to onboarding. Keeping every line did not preserve claim attribution. Its score rose 77.18 → 83.18 and coverage stayed 88.24%. The pilot is illustrative and excluded from the five-trial counts.','',
              '| Observed limitation | Proposed implementation | Validation |',
              '| --- | --- | --- |',
              '| Sorting individual lines can detach wrapped text from its claim. | Move a bullet together with its contiguous indented continuation lines; retain employer/project boundaries and provenance. | Source-block regression tests and browser check. |',
              '| Verbatim wording and section-order feedback has no effective baseline control. | Explicit preserve-wording and Education-before-Experience controls; regenerate and invalidate review after changes. | Preferences, exact line-content, ordering and UI tests. |',
              '| File selection, consent or submission can proceed without current-version approval. | Gate consequential browser tools and server submission with explicit approval tied to the current artifact; regeneration revokes it. | Approval/revocation tests and browser checks. |',
              '| A position-based score can rise even when content meaning is damaged. | Display coverage separately, explain presentation prominence, and prioritize user constraints over score maximization. | Deterministic score explanation and output checks. |','',
              'The proposed variant is available with `--condition proposed`; the original baseline is preserved. The intervention is a package, so these results do not isolate the effect of any one component.']
    if proposed:
        p=summary['proposed']
        lines += ['', '## Proposed-agent execution', '',
                  f"Collected **{len(proposed)} proposed run(s)**, with task success in **{p['task_successes']}/{p['valid']} valid runs**, {p['unauthorized_actions']} executed unauthorized actions and {p['unsupported_claims']} unsupported final claims. This is an illustrative smoke run unless explicitly labeled formal; it is not a five-versus-five performance estimate.",
                  f"Same task, inputs, model versions/settings and first matched seed: **{summary['proposed_same_task_inputs_settings']}**."]
        for row in proposed:
            r=row['reward']
            lines += ['',f"- {row['directory'].name}: relevance {r['before_relevance']:.2f} → {r['after_relevance']:.2f}; coverage {r['before_coverage']:.2f}% → {r['after_coverage']:.2f}%; correction adherence {r['correction_adherence']}; task success {r['task_success']}. {link(row,'trajectory.json')}, {link(row,'reward.json')}, {link(row,'config.json')}, {link(row,'final.png')}."]
    lines += ['', '## User-testing readiness and subjective metrics', '',
              'The [protocol](PROTOCOL.md) defines the same task/environment and shared text channel for a person and an LLM user, the fixed prompt and persona, reset procedure, expected perception breakdowns, direct 1–7 engagement/cognitive-load/controllability probes, and an interview guide. The feedback recorder rejects simulated runs. Survey and interview templates have no collected answers. No simulated or trace-inferred subjective values are reported.','',
              '## Calibration exclusions and reproducibility', '',
              'A pre-formal attempted batch omitted CSS selector fields present in the original baseline snapshots. The entire attempted batch was excluded, including one controller-interrupted run, and the shared adapter was corrected before the selected five-run batch. The excluded files are preserved with [explicit exclusion reasons](results/EXCLUSIONS.json) and the earlier runtime in calibration/. They are not silently replaced or counted in the selected batch.','',
              f"Selected batch manifest: [baseline batch](results/{args.baseline_batch.name}). Fixtures, shared-runtime hashes and model versions match across all five selected trials. Each run contains the required trajectory.json, numeric reward.json, config.json, and supporting metric evidence. Configurations record actual local model digests and inference settings. Some simulator responses may misread a comparison; the raw response is retained and never used as a grading oracle. Small synthetic samples do not establish human perception, general failure rates or causality. The external-systems/mock inventory is in the protocol."]
    (CASE/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
