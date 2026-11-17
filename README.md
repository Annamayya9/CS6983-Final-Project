# Simulated job application agent

An exploratory baseline for studying human control over a job-application agent. The website listens only on localhost and records simulated submissions as JSON. Use synthetic candidate data only.

## Setup

Requires Python, Ollama with `qwen3:8b`, and Playwright's Chromium. From PowerShell in this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-resume.txt
.\.venv\Scripts\python -m playwright install chromium
ollama pull qwen3:8b
```

Install and start Ollama separately if it is not already available. Keep Ollama running at its default local address.

## Run

In one terminal, start the simulated site:

```powershell
.\.venv\Scripts\python server.py
```

In another terminal, start the agent:

```powershell
.\.venv\Scripts\python agent.py --pause-after-action
```

The browser is visible by default. Press Enter at an action pause to continue, or type an instruction to send it to the agent. The agent may also ask a question and wait for a response. Use `--headless` to hide the browser, `--profile PATH` for another JSON profile, or `--instruction "..."` for a different task. Run `python agent.py --help` for options.

Each run writes a timestamped directory under `runs/` containing JSONL events and screenshots. The final snapshot records form values; successful simulated submissions are saved under `submissions/`. Résumé contents are not stored by the site, only the selected filename. Both output directories are excluded from Git.

The agent is an unenhanced baseline, not an approval-gated system. Do not point it at real applications or use real personal information. See [SCENARIOS.md](SCENARIOS.md) for draft scripts and the intervention protocol. Finalize the scripts before collecting experimental results.

## Correction-flow repair

`agent.py` is the repaired single-application baseline. After an interrupted action batch it gives the model the current form state and a list of cancelled actions, so the model can decide what remains authorized. Submit-button tool results now report browser validation failures or the simulated endpoint's response instead of treating a button click as a submission. These are tool-loop changes, not a consent or submission approval gate. The model can still make mistakes or report an inaccurate final answer.

`agent_phase3_original.py` preserves the exact original agent used for the November 2 Phase 3 trials. Do not mix those original results with future runs of the repaired agent. See [BASELINE_REPAIR.md](BASELINE_REPAIR.md) for the changes, checks, and limitations.

Run the isolated integration checks with:

```powershell
$env:PYTHONUTF8 = "1"
python -m unittest discover -s tests -v
```

## Multiple applications in one conversation

Start (or restart) `server.py` after updating the code. The original single-application form remains at `http://127.0.0.1:8000/`; the two-job site is at `http://127.0.0.1:8000/jobs`. Start the agent from another terminal:

```powershell
.\.venv\Scripts\python agent.py --multi-job
```

If your environment is located at `phase3\.venv` instead, replace `.\.venv\Scripts\python` with `.\phase3\.venv\Scripts\python`. This environment must have the dependencies in `requirements.txt` and Playwright's Chromium installed. The agent opens Job A and waits for instructions. For example:

```text
Fill Job A, but do not submit it.
Now open Job B and set the salary expectation to 90000. Do not submit it.
Return to Job A and tell me what is on the form.
/quit
```

Enter each instruction after the `You (or /quit):` prompt. The same conversation and browser remain open. Job A and Job B each keep their own inputs, selected file and consent state while that browser page stays open. This is an in-memory session: closing or refreshing the page loses the editable form state, and files are not restored after a refresh. A submitted record persists locally and includes its job ID; the site stores the résumé filename, not its contents. Run traces include each user message, the active job, and final states for both jobs. `--max-turns` limits model turns per user request. `--pause-after-action` also permits mid-action updates; `--site-url http://127.0.0.1:8011/` selects a different local server port.

There is no consent or submission approval gate in this baseline. Job-specific answers and permissions are supplied in the conversation; the model may still confuse them or ignore instructions. A new multi-job baseline evaluation is required before drawing conclusions. See [MULTI_JOB_BASELINE.md](MULTI_JOB_BASELINE.md).

## Two separate simulated websites

Run the two-site server in a terminal from this project directory:

```powershell
.\.venv\Scripts\python.exe two_site_server.py
```

The sites run at `http://127.0.0.1:8002/` (Example Labs, Site A) and `http://127.0.0.1:8003/` (Sample Analytics, Site B). In another terminal start one continuing agent conversation:

```powershell
.\.venv\Scripts\python.exe agent.py --two-sites
```

If your virtual environment is `.venv` at the project root, use its Python instead. After the initial reply, try instructions such as “Fill Site A but do not submit,” then “Open http://127.0.0.1:8003/ and fill Site B,” and “Return to Site A.” Enter `/quit` to finish. `--pause-after-action` also allows interruptions within a tool batch.

The agent opens the sites in separate tabs of the same browser and retains the conversation. Switching back to an open tab preserves that tab's form values and file selection, but closing or refreshing it loses the draft. Submitted records stay local and identify the site and job. They include the selected résumé filename and a SHA-256 digest calculated from the uploaded bytes, but not the bytes themselves. Traces contain navigation events, URLs, action context, and end-of-session state and screenshots for each opened site.

The full conversation is kept in the harness during the session, but Qwen has a finite context window and may lose access to older messages in a long conversation. On navigation, the agent receives the target site's visible controls and the candidate profile again; this does not guarantee that it will use them correctly.

Only the two configured **localhost** origins can be opened by the navigation tools. Use `--site-url` and `--second-site-url` alongside `two_site_server.py --port-a` and `--port-b` to choose different local ports. The restriction keeps this test environment on the two simulated sites; it is not a consent or submission approval gate. The model may still mix up jobs, invent values, or fail to respect an instruction. See [TWO_SITE_BASELINE.md](TWO_SITE_BASELINE.md) for observed smoke-test limitations and proposed evaluation cases.

## Résumé tailoring for two sites

Install `requirements-resume.txt` for PDF support. Restart `two_site_server.py`, then start `agent.py --two-sites --profile profiles/tailoring.json`. Ask the agent to tailor the profile résumé for Site A, then ask it to open Site B and tailor the original résumé for that site. For example: “Tailor and upload my résumé for Site A, fill the application, but do not submit.” You can follow up with instructions for Site B and return to either tab.

The `tailor_resume` tool reads the active site's displayed job description and the supplied source file, creates a separate artifact folder under the run for that site and returns a comparison, an artifact path, and an upload handle such as `@tailored/site-a`. The handle refers to the latest generated version for that site during this run. It does not automatically upload or submit. Ask the agent to upload the result if desired; inspect `comparison.html` and `changes.diff` in the artifact folder to review changes. The submitted record's `resume_sha256` can be compared to `tailored_sha256` in that artifact's `comparison.json`. This records what the simulated form received; it is not a gate preventing an incorrect file selection.

The tailoring engine is adapted from PR #2's block-preserving `resume_relevance.py` and `resume_claims.py`. It rearranges existing text and normalizes a few technology names rather than writing new achievements. It supports UTF-8 TXT, text PDF, and DOCX; scanned PDFs and legacy DOC are not supported, and PDF/DOCX formatting is not preserved in the TXT output. Its relevance score is a limited lexical and placement diagnostic, not an ATS score or evidence of new qualifications. Review generated text for accuracy.

The agent can regenerate a résumé with Education first and/or original wording preserved using `tailor_resume_with_preferences`. Regeneration produces a new artifact; a previously selected upload is not automatically replaced. Other free-form changes to résumé content are not implemented by these tools. This is an available capability, not a guarantee the model will understand or execute a user's correction.

This version adds a tailoring tool to the baseline; it does not add PR #2's deterministic review controller or approval gate. An agent may upload a wrong file, ignore a correction, accept consent without permission, or misreport submission. Previous Phase 3 and two-site results apply to older versions, not this one. Traces and résumé artifacts contain synthetic profile data and remain under ignored `runs/`; use synthetic data only.

## Resume tailoring extension

The separate [resume workflow](RESUME_WORKFLOW.md) adds TXT/PDF/DOCX upload, tailoring to a position’s JD, before/after relevance scores, requirement evidence, an exact change comparison, and verified upload of the generated resume. The original Phase 3 agent is preserved separately; the current baseline has since been extended for multiple applications.

```sh
python -m pip install -r requirements-resume.txt
python -m playwright install chromium
python resume_server.py
```

Open `http://127.0.0.1:8001/`. To run the synthetic end-to-end browser experiment, use `python run_resume_experiment.py`. See [experiment inputs and results](experiments/resume_relevance/README.md) and [scoring limitations](RESUME_WORKFLOW.md#relevance-metric).

## Two-mode evaluation case

[RESUME-REVIEW-01](evaluation/cases/resume_review/README.md) adds a resettable whole-workflow task, a separate LLM simulated user, a human-user mode using the same text channel, shared core metrics, five new baseline trials, and human survey/interview probes. See the [protocol](evaluation/cases/resume_review/PROTOCOL.md) and [recorded results and proposed fixes](evaluation/cases/resume_review/RESULTS.md). The proposed condition preserves wrapped claim blocks, supports explicit wording/order preferences, and scopes approval to the current resume version. The original baseline remains available.

## Review-executor update and self-service testing

Start with the [step-by-step test guide](TEST_CASE_GUIDE.md). The new production engine moves complete claim blocks, preserves wording on request, and exposes section-order preferences. The proposed study condition adds an audited deterministic executor so supported review feedback changes the actual browser controls and regenerated file, with approval bound to the visible artifact and browser session. This is a hybrid intervention around the LLM planner.

```sh
python run_resume_study.py --mode simulated --condition proposed --phase smoke --agent-driver scripted --user-driver scripted --output-root runs/my-first-case
```

This first check needs no Ollama. Historical results remain dated snapshots; see the [v4 update report in Chinese](UPDATE_REPORT_ZH.md) for new validation, including failed diagnostic runs, and the guide for LLM and human modes. Close Ollama processes after model runs; keep the installed models.
## Two-site study cases

See [TWO_SITE_STUDY.md](TWO_SITE_STUDY.md) for the permissions and correction cases, user modes, metrics, and recorded trials. These use the two-site baseline and are separate from RESUME-REVIEW-01.
