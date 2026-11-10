# BugPilot v2 — SWE-bench Lite Clean Held-Out Run

## Protocol
- Dataset: `princeton-nlp/SWE-bench_Lite`
- Split: `test`
- Deterministic seed: `bugpilot-v2-heldout`
- Selected instances: 10
- Model: `claude-haiku-4-5`
- No gold patch, test patch, FAIL_TO_PASS, PASS_TO_PASS, target file, or target function was exposed to BugPilot.
- Exact SWE-bench base commits were used.
- Final verification used the official SWE-bench harness.

## Generation
- Selected: 10
- Predictions generated: 6
- Generation failures: 4
- Prediction-generation rate: 60%

## Official Results
- Officially evaluated predictions: 6
- Resolved: 0
- Unresolved: 6
- Infrastructure errors: 0
- End-to-end resolved: 0/10

### Evaluated predictions
- `sympy__sympy-24102` — unresolved
- `pallets__flask-4045` — unresolved
- `django__django-15789` — unresolved
- `sphinx-doc__sphinx-8474` — unresolved
- `matplotlib__matplotlib-26011` — unresolved
- `sympy__sympy-14817` — unresolved

## Interpretation
BugPilot v2 improved repository localization and prediction generation, but generated patches did not pass the official SWE-bench tests on this held-out sample.

This sample is now considered development data and must not be reused as the final clean v3 benchmark.
