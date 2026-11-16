# Resume review test case

This package implements the assignment's two-mode test-case requirements. Start with [the protocol](PROTOCOL.md), then [the recorded results](RESULTS.md).

| Requirement | Location |
| --- | --- |
| Resettable environment, fixed files/tools, external systems and mock inventory | PROTOCOL.md and input/ |
| Fixed task, initial prompt and simulated-user persona | PROTOCOL.md; run_resume_study.py TASK; input/user_persona.json |
| Same user/agent communication in both modes | UserChannel.receive in run_resume_study.py; parity regression test |
| Shared objective and subjective core metrics | evaluation/core_metrics.json and evaluation/README.md |
| Five baseline trials with an actual LLM user | RESULTS.md and its selected batch manifest |
| Per-run trajectory.json, numeric reward.json and config.json | results/ folders; links in RESULTS.md |
| Objective metrics and control-breakdown counts with denominators | RESULTS.md, objective_summary.json and objective_metrics.csv |
| Human testing ready, without fabricated human results | Participant task card, survey_template.json, interview_template.md and record_human_feedback.py |
| Path to a directly comparable proposed agent | resume_proposed.py and --condition proposed |
| Initial example and discovered resume flaws | Pilot in results/ and RESULTS.md |

From the repository root after installing requirements-resume.txt, Chromium and the selected local Ollama model:

```sh
python run_resume_study.py --mode simulated --condition baseline --phase formal --trials 5 --seed 101
python run_resume_study.py --mode human --condition baseline --phase formal
python run_resume_study.py --mode simulated --condition proposed --phase formal --trials 5 --seed 101
python run_resume_study.py --mode human --condition proposed --phase formal
```

The simulated user is a separate model conversation and never receives the grading function or subjective survey. The agent remains a model-driven browser agent. Human mode uses the same task, files, application and text channel with a person answering the prompts. No human sessions have been run for this submission.

The original current-extension baseline is preserved in baseline_v1/. Pilot and excluded calibration evidence are retained separately from the selected five formal baseline trials. Do not combine these denominators or treat one proposed smoke run as a five-versus-five study.

## Current intervention revision (v4)

The earlier `RESULTS.md` and Chinese course report describe the archived v2/v3 intervention, not the latest implementation. [The v4 Chinese update report](../../../UPDATE_REPORT_ZH.md) records the new validation. Use the [from-scratch guide](../../../TEST_CASE_GUIDE.md) for current commands. Frozen baseline source, runtime snapshots, failures and the selected five baseline trials are retained.

The v4 proposed condition combines the LLM planner with a deterministic review executor. It parses only actual shared-channel feedback (never the private persona or objective grader), applies supported requests using visible browser controls, regenerates and verifies the artifact, and requests explicit scoped approval. The executor's calls/results appear under `actor: controller`. Unsupported or ambiguous requests cause clarification or a bounded unresolved stop. The intervention is not a claim of improved unaided LLM reasoning.
