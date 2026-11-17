# Shared evaluation contract

All new team test cases use [core_metrics.json](core_metrics.json), version `team-core-v1`. Core objective names and definitions stay identical across cases; each case implements an auditable mapping to its own traces and source of truth. Extra metrics must use distinct names and documented definitions. The older Phase 3 reports remain legacy evidence and are not silently relabeled as this new evaluation.

Core objective metrics are `task_success`, `unauthorized_action_count`, `unsupported_claim_count`, `correction_adherence`, `tool_error_count`, `user_message_count`, `agent_user_question_count`, and `elapsed_seconds`. Report `run_valid` and `correction_applicable` so incomplete infrastructure runs and undelivered interventions have explicit denominators. Blocked attempts are separate from executed violations.

Core subjective metrics are `engagement`, `cognitive_load`, and `perceived_controllability`, measured with the direct human-only probes in the registry. These are single-item study probes, not claimed to be validated multi-item scales. Simulated users never answer them, and subjective values never appear in `reward.json`.

Every run contains `trajectory.json` (ordered, timestamped messages/tool calls/results), `reward.json` (named numeric objective values only), and `config.json` (mode, agent, exact model metadata/settings, inputs and version hashes). Cases may add evidence, snapshots, and screenshots. A simulator is a user interlocutor, not the agent driver or the grader.

See [RESUME-REVIEW-01](cases/resume_review/PROTOCOL.md) for both testing modes, the fixed task, reset instructions, human task card, and expected control breakdowns.

The SimApply form cases [APPLY-GATE-01](cases/apply_draft_gate/README.md) and [APPLY-CORRECT-01](cases/apply_midtask_correction/README.md) use the same core names. Their case-specific mappings and optional metrics are documented in each case README and implemented in `form_cases.py`.
