# SimApply form cases (APPLY-GATE-01, APPLY-CORRECT-01): runner + mock site + headless Chromium.
# The LLM runs in Ollama outside this image (host Ollama by default, or the optional compose "ollama" service).
FROM mcr.microsoft.com/playwright/python:v1.64.1-noble
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_BREAK_SYSTEM_PACKAGES=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OLLAMA_URL=http://host.docker.internal:11434 OBSERVER_BIND=0.0.0.0
COPY requirements.txt requirements-study.txt ./
RUN pip install --no-cache-dir -r requirements-study.txt
COPY agent.py run_form_case.py record_human_feedback.py ./
COPY evaluation/core_metrics.json evaluation/form_cases.py evaluation/form_proposed.py evaluation/form_timeline.py evaluation/
COPY evaluation/form_site/ evaluation/form_site/
COPY evaluation/cases/apply_draft_gate/case.json evaluation/cases/apply_draft_gate/
COPY evaluation/cases/apply_draft_gate/input/ evaluation/cases/apply_draft_gate/input/
COPY evaluation/cases/apply_midtask_correction/case.json evaluation/cases/apply_midtask_correction/
COPY evaluation/cases/apply_midtask_correction/input/ evaluation/cases/apply_midtask_correction/input/
COPY tests/test_form_cases.py tests/
ENTRYPOINT ["python", "run_form_case.py"]
CMD ["--help"]
