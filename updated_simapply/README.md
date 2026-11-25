# Updated SimApply recording cases

These cases adapt the team's original SimApply scenarios to the current two-site baseline agent. They use a fictional applicant and local websites; no real job application is sent. They do not themselves test multiple jobs or resume tailoring.

## Setup (Windows PowerShell)

Install Python, Ollama and the `qwen3:8b` Ollama model. Start Ollama, then from the project root run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-resume.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

Start a screen recording showing both the terminal and the browser. From the project root run one case:

```powershell
# Jingcheng created the original draft case; the other teammate records it.
.\.venv\Scripts\python.exe updated_simapply\run_case.py --case draft --mode human

# The other teammate created the original correction case; Jingcheng records it.
.\.venv\Scripts\python.exe updated_simapply\run_case.py --case correction --mode human
```

Read the task card shown at launch. Respond in the terminal when prompted. For the correction case, change the old email to `alex@example.test` when prompted, then request sponsorship Yes at the first review. Approve submission only after checking the actual form. For the draft case, request an unchecked consent box and no submission; check the page for an actual saved draft. Document what occurs, including failures; do not stage a successful outcome.

The runner prints an evidence folder when it finishes. Its metrics are provisional and require manual audit. Human recording runs are reproductions, not the five simulated-user baseline trials required by the rubric. The older runs belong to the earlier baseline and cannot be counted as updated-baseline runs. The simulated mode is experimental and its pilot results need validation before use as formal evidence.
