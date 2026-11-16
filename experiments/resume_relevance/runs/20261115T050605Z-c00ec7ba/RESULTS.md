# Resume relevance experiment

Driver: **scripted**. One synthetic case, separate from the Phase 3 baseline.

| Measure | Before | After |
| --- | ---: | ---: |
| Relevance score / 100 | 76.95 | 84.33 |
| Weighted requirement coverage | 88.24% | 88.24% |
| Weighted evidence prominence | 31.82% | 68.72% |

Change: +7.38 points. Remaining gaps: Kubernetes, AWS.
The coverage stays constant because tailoring preserves candidate qualifications. The score change reflects evidence placement.

The executor filled the application, uploaded the source, requested tailoring, inspected the comparison, selected the tailored file, accepted the fixture’s explicitly approved simulated consent, and submitted. The server verified the actual submitted bytes against the generated artifact and saved 1 submission record(s).

- [Full comparison and diff](comparison.html)
- [Original resume](service/artifacts/b45a3adbf0324a05a4d1b01f81963d15/original_resume.txt)
- [Tailored resume](service/artifacts/b45a3adbf0324a05a4d1b01f81963d15/tailored_resume.txt)
- [Machine-readable evidence and provenance](service/artifacts/b45a3adbf0324a05a4d1b01f81963d15/comparison.json)
- [Browser trace](agent/trace.jsonl)
- [Final browser screenshot](agent/final.png)
- [Manifest, checks, versions and hashes](manifest.json)

All checks passed: **True**.
Scripted mode is an integration test with a fixed operator policy, not evidence of Qwen performance, improved hiring outcomes, or measured human effort. The scoring vocabulary and weights are heuristic; inspect the report’s limitations.

See [the cross-run evaluation and model-reporting observations](../../RESULTS.md).

- [Verified local submission 81f03b79df6c460daa6a83aba77bc273](service/submissions/81f03b79df6c460daa6a83aba77bc273.json)
