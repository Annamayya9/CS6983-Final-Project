# Demo walkthrough and explanation

Start the app with `python resume_server.py` and open http://127.0.0.1:8001/. A fresh visit starts a blank application. The [archived live comparison](experiments/resume_relevance/live_demo/comparison.html) and the evidence linked below can be inspected without running the app.

## A short explanation you can give

“I extended a simulated job-application agent with a resume preparation step. It reads an uploaded resume and the target job description, brings existing relevant experience forward, and shows the original and tailored versions with exact changes. It scores both versions against the same requirements, reports missing skills, and lets the operator review the file before using it. The local server verifies that the submitted file is exactly the generated version for that job. The original baseline remains available for comparison.”

## What happened in this live example

1. Loaded fictional position SIM-BE-001, Backend Software Engineering Intern at Northstar Software.
2. Uploaded `experiments/resume_relevance/input/resume.txt`, a synthetic resume for Alex Example.
3. Clicked **Analyze & tailor resume**.
4. Inspected before/after scores, source evidence, missing requirements, and exact changed lines.
5. Clicked **Use reviewed tailored resume** and filled the application using the synthetic profile.
6. Accepted the fixture-approved simulated consent and submitted the application locally.
7. Verified the saved server record: `experiments/resume_relevance/live_demo/submission.json`. Its `resume_verified` value is true, and it records the job ID, run ID, resume/JD hashes, and both scores.

This is a local demonstration with synthetic data, not an application sent to an employer.

## Before and after

| Measure | Before | After |
| --- | ---: | ---: |
| Relevance / 100 | 76.95 | 84.33 |
| Weighted requirement coverage | 88.24% | 88.24% |
| Weighted evidence prominence | 31.82% | 68.72% |

The improvement is +7.38 relevance points. Coverage is unchanged because no qualifications were added. AWS and Kubernetes remain missing.

Before section order:

`Interests → Education → Experience → Projects → Technical Skills`

After section order:

`Experience → Technical Skills → Projects → Education → Interests`

Within the existing engineering role, the Python/API/SQL bullet moved above onboarding notes. Within the existing academic project, the Docker bullet moved above the installation-guide bullet.

Exact wording example:

> Before: Built Python REST endpoints for an internal inventory tool using Postgres and SQL.

> After: Built Python REST API endpoints for an internal inventory tool using PostgreSQL and SQL.

The skills line also changed `Postgres` to `PostgreSQL`. In total, two lines received terminology changes and 21 lines changed position with their sections or bullet groups. Every nonblank source line was retained once, with a source-to-output line mapping. Identity, education, employers, dates, duration, and other claims were retained.

## What the implementation adds

| Component | Added behavior |
| --- | --- |
| `resume_relevance.py` | Reads TXT/PDF/DOCX text, extracts recognized JD requirements, tailors section/bullet order and explicit spellings, calculates before/after scores, and produces HTML/JSON/diff artifacts with provenance. |
| `site/resume.html` | Adds JD input, resume upload, visible score comparison, requirement evidence, gaps, original/tailored text, changed-line inspection, download, and explicit file selection. |
| `resume_server.py` | Adds the separate localhost app, tailoring API and artifact downloads. Submission verifies selected resume bytes and the current JD against the reviewed result. |
| `resume_agent.py` | Lets the original browser-tool approach operate the enhanced workflow, using either Ollama or a fixed scripted driver. Completion is checked against a matching local submission record. |
| `run_resume_experiment.py` | Runs an isolated end-to-end browser experiment with frozen inputs, versions, hashes, traces, screenshots, checks and results. |
| `tests/` | Adds 12 parsing/scoring/server tests and nine reproducible browser checks. |

The original `agent.py`, `server.py`, `site/index.html`, candidate profiles and Phase 3 evidence were preserved. The existing README now links to the separate extension.

## How to explain the score honestly

`Relevance = 80% weighted requirement coverage + 20% evidence prominence`.

Coverage measures recognized JD terms with positive resume evidence. Required terms have weight 2; other recognized terms have weight 1. Aliases such as Postgres/PostgreSQL receive the same coverage credit. Prominence rewards the first evidence appearing earlier among the resume's nonblank lines. Both versions use the same extracted requirements, aliases and weights.

This example improves the prominence component. It does not show that the candidate gained skills or became more qualified. The metric is a transparent lexical heuristic, not an ATS score, hiring probability, or independent semantic evaluation. The fixture intentionally starts with unrelated interests before engineering experience, making the placement effect easy to inspect.

Tailoring is deterministic and preserves source claims; it does not use an LLM to generate new resume prose. Qwen/Ollama can drive the browser actions. Inputs can be TXT, text PDF or DOCX; the output is editable TXT, so original PDF/DOCX layout is not preserved. Full generative rewriting, arbitrary skill inference, and assessment of seniority or experience years are outside this version.

## Evidence and reproduction

- [Live resume comparison](experiments/resume_relevance/live_demo/comparison.html)
- [Exact diff](experiments/resume_relevance/live_demo/changes.diff)
- [Verified live submission](experiments/resume_relevance/live_demo/submission.json)
- [Live screenshot](experiments/resume_relevance/live_demo/demo-comparison.jpg)
- [Recorded scripted and Ollama experiments](experiments/resume_relevance/RESULTS.md)
- [Detailed implementation and scoring method](RESUME_WORKFLOW.md)

The earlier experiments include one successful scripted run and one successful `qwen3.5:4b` run. The model run recovered from two blocked submission attempts and mislabeled score/coverage in its final prose; those observations are preserved in the evaluation. Use the stored comparison JSON and UI values as the authoritative scores. This small sample does not establish performance rates or human-control effectiveness.

To repeat the default experiment:

```sh
python run_resume_experiment.py
```

To start the interactive app:

```sh
python resume_server.py --port 8001 --output-dir runs/live_demo
```
