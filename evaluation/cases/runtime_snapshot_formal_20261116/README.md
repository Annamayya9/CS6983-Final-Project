# Runtime snapshot for the recorded formal baseline runs (2026-11-16)

`run_form_case.py` here is the exact runner baked into the Docker image that produced the formal baseline runs of
APPLY-GATE-01 and APPLY-CORRECT-01. Its SHA-256 (`75ce1f8e…f9f0fd`) equals `code_sha256["run_form_case.py"]` in both
runs' `config.json`. Later changes to the repository copy (compare with
`diff evaluation/cases/runtime_snapshot_formal_20261116/run_form_case.py run_form_case.py`):

1. `--phase rehearsal` for the demo video's human-mode walkthrough.
2. A lowercase `done` also ends a human session at the handoff.
3. Bounded model-call retry: Ollama answers HTTP 500 when the model emits a malformed tool call. The runner now retries
   up to twice with a shifted seed and logs each `model_call_retry` event; `evaluation/form_cases.py` counts them as
   `model_call_retry_count`. No HTTP error occurred in the formal runs, so their trajectories are unaffected. One demo
   run hit the error before this change and is kept as an inconclusive run (`run_valid=0`).
4. The observer's file server no longer writes HTTP access logs to the terminal.

Agent prompt, tools, environment, simulator persona and grading rules are unchanged.
