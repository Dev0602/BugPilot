# BugPilot SWE-bench Lite — First Clean No-Oracle Run

Date: 2026-09-20

## Protocol

- Dataset: `princeton-nlp/SWE-bench_Lite`
- Split: `test`
- Selection method: deterministic SHA-256 selection
- Seed: `bugpilot-v1`
- Selected instances: 5
- Model: `claude-haiku-4-5`
- Gold patch, test patch, FAIL_TO_PASS, and PASS_TO_PASS were not exposed to the agent.
- Repositories were checked out at the exact SWE-bench base commits.
- Official SWE-bench harness was used for final verification.
- Evaluation ran through Docker x86_64 emulation on an ARM64 host.

## Fixed Sample

1. `pylint-dev__pylint-5859`
2. `sympy__sympy-21379`
3. `pytest-dev__pytest-7490`
4. `django__django-12700`
5. `matplotlib__matplotlib-25311`

## Generation Results

- `pylint-dev__pylint-5859`
  - No prediction generated.
  - Agent reached the 12-tool-turn investigation limit.

- `sympy__sympy-21379`
  - No prediction generated.
  - Agent reached the 12-tool-turn investigation limit.

- `pytest-dev__pytest-7490`
  - No prediction generated.
  - Agent reached the 12-tool-turn investigation limit.

- `django__django-12700`
  - Prediction generated.
  - Target: `django/views/debug.py`
  - Function: `SafeExceptionReporterFilter.cleanse_setting`
  - Recorded successful-generation cost: `$0.07651`
  - Official SWE-bench result: unresolved.

- `matplotlib__matplotlib-25311`
  - No prediction generated.
  - Agent reached the 12-tool-turn investigation limit.

## Summary

- Selected: 5
- Predictions generated: 1/5 (20%)
- Confirmed resolved: 0/5 (0%)
- Generation failures: 4/5
- Officially evaluated generated predictions: 1
- Officially resolved generated predictions: 0

This run is retained as the clean pre-improvement baseline.
