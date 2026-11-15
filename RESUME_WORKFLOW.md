# Resume tailoring extension

The original `agent.py`, `server.py`, `site/index.html`, profiles, and Phase 3 evidence remain unchanged. This implementation is a separate workflow, as requested by the project’s experiment plan.

## Existing workflow

1. `server.py` serves a synthetic application form on localhost:8000.
2. `agent.py` loads a JSON candidate profile, sends the task to Qwen3-8B through Ollama, and executes its browser tool calls with Playwright.
3. The tools inspect, fill, select, check, upload, click, and ask the user. Optional action pauses allow corrections; a correction cancels the rest of the queued actions in that model response.
4. Runs record JSONL traces, form snapshots, and screenshots. The simulated server records submissions as local JSON. The original site records a resume filename, not its contents.
5. T1–T6 and C1–C3 investigate missing facts, submission constraints, consent, corrections, and completion reporting. The Phase 3 dataset and Phase 4 proposal are prior project material, not results from this new feature.

## New workflow

`resume_server.py` serves `site/resume.html` on localhost:8001. Choose a position ID and its JD, upload a resume, and click **Analyze & tailor resume**. The page shows scores, requirement evidence, missing skills, original and tailored text, an exact change list, and a downloadable comparison. Click **Use reviewed tailored resume**, complete the application, and submit locally.

The comparison is tied to both the resume and JD through SHA-256 hashes. Changing the uploaded file, position ID, or JD invalidates the current review. Submission checks the actual selected file bytes against the generated artifact and rejects stale JD results. Every browser session has a run ID, used to correlate authoritative submission records. These checks apply to this simulated workflow only; this is not an implementation or evaluation of all the proposed Phase 4 interventions.

### Tailoring behavior

`resume_relevance.py` reads UTF-8 TXT, text PDF, and DOCX (maximum 5 MiB). Legacy DOC and scanned PDFs are rejected with an actionable error. PDF/DOCX text extraction does not retain document layout; the tailored output is an editable TXT file.

The deterministic engine:

- Promotes whole sections containing relevant evidence, keeping the identity/contact preamble first.
- Reorders contiguous bullet groups within a section, retaining employer/project headers and their associated bullets.
- Normalizes explicit equivalent technology spellings only when relevant to the JD: `Postgres` → `PostgreSQL`, `JS` → `JavaScript`, `k8s` → `Kubernetes`, and `REST endpoints` → `REST API endpoints`.
- Retains every nonblank source line exactly once. Every nonblank output line maps to its original line and records whether its wording or position changed. The source file is never overwritten.

There is no generative claim rewriting or invented achievement, number, employer, credential, or skill. An unsupported qualification remains a reported gap. This conservative scope makes the example reproducible; arbitrary prose rewriting and preservation of PDF/DOCX formatting are future extensions.

### Relevance metric

The JD is matched against a curated vocabulary in `VOCABULARY`, covering common software/data skills and several collaboration/business terms. Canonical spellings and aliases receive the same credit. A line containing `required`, `must`, or `essential` gives its extracted terms weight 2; other terms have weight 1. Both evaluations use the **same frozen requirement list and weights**. A JD with no recognized requirements produces an explicit error rather than a meaningless score.

For requirement i, `m_i` is 1 when the resume has positive lexical evidence, otherwise 0. `w_i` is its JD weight. `r_i` is the zero-based rank of its first evidence line among nonblank lines, and `L` is the number of nonblank lines.

```text
Coverage C   = 100 × sum(w_i × m_i) / sum(w_i)
Prominence P = 100 × sum(w_i × m_i × (1 − r_i/max(1,L−1))) / sum(w_i)
Relevance S  = 0.8 × C + 0.2 × P
```

Missing evidence contributes zero to both components. Obvious negative or uncertain clauses such as “no AWS experience” and “learning Kubernetes” receive no credit. The parser is conservative and does not perform full semantic verification.

This is a transparent lexical diagnostic, **not an ATS score, hiring probability, or independently validated measure of candidate suitability**. It does not assess years, seniority, degree equivalence, or all possible skills. Tailoring mechanically favors this metric’s placement component. Report coverage separately so a placement gain cannot be misrepresented as new qualifications. A score increase is not guaranteed for every resume/JD pair.

## Setup and run

Use a Python virtual environment (Python 3.9 or newer):

```sh
python -m pip install -r requirements-resume.txt
python -m playwright install chromium
python resume_server.py
```

Open `http://127.0.0.1:8001/`. The fictional default position and synthetic profile/resume are in `experiments/resume_relevance/input/`. The server supports `--port` and `--output-dir`. Default artifacts and submissions are under `runs/resume_workflow/`.

Tailoring itself requires neither Ollama nor an API key. To drive the enhanced page with the existing Ollama browser tools, start Ollama with the chosen model, then run in a second terminal:

```sh
python resume_agent.py --headless --model qwen3:8b
```

Use `--pause-after-action` for operator corrections. `--driver scripted` runs the fixed synthetic operator policy instead of Qwen. `--site-url` and `--submission-dir` must identify the same local server and its output directory. The original baseline remains available through its original entry points on port 8000.

For a standalone comparison without a browser:

```sh
python resume_relevance.py --resume path/to/resume.pdf --jd path/to/jd.txt --job-id EXAMPLE-01 --output-dir runs/my-comparison
```

## Reproduce the experiment

```sh
python -m unittest discover -s tests -v
python tests/check_resume_ui.py
python run_resume_experiment.py
```

The default experiment starts a fresh server on an automatically assigned local port, copies the synthetic inputs, drives Chromium through the same tool executor, and writes a unique run directory under `experiments/resume_relevance/runs/`. It requires no running model. It exercises upload → tailoring → comparison → acceptance → application → verified local submission.

For an additional actual-model run:

```sh
python run_resume_experiment.py --driver ollama --model qwen3:8b
```

The runner records the selected model’s metadata and defaults, and supplies a fixed automated response if the agent asks for approval. All questions/responses remain in the trace. If a different model is used, treat that as a separate exploratory run, not a matched Phase 3 comparison.

Each run contains `RESULTS.md`, `comparison.html`, frozen inputs, a manifest with versions and code/input/baseline hashes, complete line provenance, a unified diff, browser traces/screenshots, and the authoritative submission record. Checks verify identical qualification coverage, retained source lines, unfilled unsupported AWS/Kubernetes requirements, unchanged prior baseline files, and the submitted file/JD hashes.

The deterministic case is a browser integration experiment, not a measurement of autonomous model reasoning or human-control effectiveness. A single model-driven case is also exploratory; it cannot establish performance rates or causality. The fixture deliberately starts with unrelated interests ahead of relevant experience to expose the placement effect.
