# Simulated job application agent

An exploratory baseline for studying human control over a job-application agent. The website listens only on localhost and records simulated submissions as JSON. Use synthetic candidate data only.

## Setup

Requires Python, Ollama with `qwen3:8b`, and Playwright's Chromium. From PowerShell in this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
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
