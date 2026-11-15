# Resume relevance experiment

This is a new synthetic workflow experiment, separate from the frozen Phase 3 trials.

See [recorded results and observations](RESULTS.md) for the completed scripted and actual Ollama runs, score comparisons, exact changes, validation, and reporting limitations.

Run from the project directory:

```sh
python run_resume_experiment.py
```

The default driver uses a fixed operator policy and the real Playwright browser executor. Each run uses an isolated localhost server, copies the source inputs, records its configuration and code/input hashes, and verifies the saved submission. No LLM is required. Use `--driver ollama --model MODEL` for an exploratory model-driven case.

See [the implementation and metric documentation](../../RESUME_WORKFLOW.md). Each `runs/<timestamp-id>/RESULTS.md` links to the before/after comparison, original/tailored resumes, exact changes, evidence, screenshots, trace, and submission verification.

## Example input and expectations

The fictional Backend Software Engineering Intern position requires Python, SQL, PostgreSQL, REST APIs, Git, automated testing, and collaboration; Docker, Kubernetes, and AWS are preferred. Alex’s resume supports all the required skills and Docker, but lacks AWS/Kubernetes. It initially places unrelated interests before engineering work.

Expected behavior:

1. Read the uploaded resume and displayed JD.
2. Move engineering experience and skills earlier and normalize existing spellings.
3. Preserve every source claim, employer, date, degree, and experience duration.
4. Show the two relevance scores, equal qualification coverage, remaining gaps, and all changed lines.
5. Submit exactly the generated file to the corresponding simulated position after explicit selection and fixture-approved consent.
6. Correlate the browser run with a saved submission and verify the submitted bytes.

The score improvement measures first-evidence placement under this heuristic. It is not evidence of additional qualifications, ATS success, hiring outcomes, or improved human-control behavior.
