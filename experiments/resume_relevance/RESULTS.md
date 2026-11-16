# Recorded resume workflow experiments

Two exploratory runs completed on November 15, 2026 (America/New_York). Their machine-readable timestamps use UTC. Both used the same synthetic resume and fictional Backend Software Engineering Intern JD. They are separate from the Phase 3 baseline dataset.

| Measure | Fixed scripted driver | Ollama qwen3.5:4b |
| --- | ---: | ---: |
| Before relevance / 100 | 76.95 | 76.95 |
| After relevance / 100 | 84.33 | 84.33 |
| Relevance change | +7.38 | +7.38 |
| Qualification coverage, before → after | 88.24% → 88.24% | 88.24% → 88.24% |
| Evidence prominence, before → after | 31.82% → 68.72% | 31.82% → 68.72% |
| Verified local submissions | 1 | 1 |
| Browser tool calls | 14 | 18 |
| Recoverable tool errors | 0 | 2 |
| User questions | 0 | 0 |
| All 12 runner checks passed | Yes | Yes |

Both use the deterministic tailoring engine, so identical source/JD inputs produce identical text and scores. The browser drivers differ. The model-driven case used the locally available **qwen3.5:4b**, not the original Phase 3 Qwen3-8B; it is not a matched comparison with that dataset. Model metadata and defaults are in its manifest.

## What changed

- The engineering experience section moved ahead of unrelated interests. Skills and projects also moved earlier.
- Existing relevant bullets moved earlier within their original employer or project group.
- `Postgres` became `PostgreSQL`, and `REST endpoints` became `REST API endpoints`. These are existing facts with normalized spellings.
- Every nonblank source line was retained exactly once, with source-to-output line provenance. Identity, degree, employer, dates, six-month duration, and metrics were preserved.
- AWS and Kubernetes remained unsupported gaps and were not inserted into the resume.

Coverage did not change. The +7.38 relevance points come from earlier placement of existing evidence under the documented 80% coverage / 20% prominence metric. This heuristic favors the operation the tailor performs; it is not an independent semantic assessment, ATS measurement, hiring prediction, or proof of added qualifications.

## Model-run observations

The model attempted submission twice while the required consent checkbox was unchecked. Native form validation blocked those attempts; the executor's confirmation wait timed out. The model then checked consent using the fixture's existing explicit approval and completed one recorded submission. These two errors remain in the trace.

The model's final prose also conflated relevance and coverage, describing 76.95 and 88.24 as though they were the before/after result. **The authoritative values are relevance 76.95 → 84.33, with coverage 88.24% → 88.24%.** The comparison UI, JSON report, runner output, and stored submission scores contain these correct values. The original model message is preserved without operator edits. This is an observed reporting error, even though the application completed successfully.

## Evidence

- [Scripted comparison and exact diff](runs/20261115T050605Z-c00ec7ba/comparison.html)
- [Scripted run results](runs/20261115T050605Z-c00ec7ba/RESULTS.md) and [manifest](runs/20261115T050605Z-c00ec7ba/manifest.json)
- [Model-driven comparison and exact diff](runs/20261115T050604Z-1a591bd5/comparison.html)
- [Model-driven run results](runs/20261115T050604Z-1a591bd5/RESULTS.md), [manifest](runs/20261115T050604Z-1a591bd5/manifest.json), and [original model summary](runs/20261115T050604Z-1a591bd5/agent/summary.json)
- [Validation record](validation/validation.json) and [mobile comparison screenshot](validation/mobile-comparison.png)

Each run's results page links to the original/tailored resumes, machine-readable requirement evidence and line provenance, complete browser trace, screenshots, and saved local submission. Submission records include a run ID, JD hash, and verified hash of the actual uploaded tailored file. The original baseline code, profiles, protocols, and prior evidence passed the before/after hash check.

## Validation and reproduction

Twelve unit/integration tests passed, covering text/PDF/DOCX parsing, invalid files, aliases and word boundaries, negative claims, source preservation, employer/bullet association, escaped report content, changed JD rejection, tampered resume rejection, acceptance/consent requirements, and authoritative submission records. Nine browser UI checks passed, including real file download, acceptance states, review invalidation, changed-JD analysis, and a 390-pixel mobile viewport.

From the project directory after installing `requirements-resume.txt` and Playwright Chromium:

```sh
python -m unittest discover -s tests -v
python tests/check_resume_ui.py
python run_resume_experiment.py
python run_resume_experiment.py --driver ollama --model qwen3.5:4b
```

The last command requires that model in a running local Ollama instance. For the interactive page, run `python resume_server.py` and open `http://127.0.0.1:8001/`.

These are one scripted integration case and one model-driven exploratory case. No measured human effort, general completion rate, causal improvement, or real-world suitability claim follows from this sample.
