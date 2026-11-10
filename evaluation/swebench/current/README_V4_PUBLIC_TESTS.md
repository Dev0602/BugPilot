# BugPilot v4 — optional public-test verification

## What this adds

When a trusted image is explicitly configured for a public repository, BugPilot
checks the proposed Python module name against **existing pytest test files in
that repository's base checkout** (`test_<module>.py` or `<module>_test.py`).
Only exact conventional filenames in test directories, or beside the module,
are selected; up to three matching files run in an isolated, offline Docker
container. The source tree is mounted read-only; the test runner copies it to a
temporary sandbox, executes pytest with no network access and no privilege
escalation, and reports a bounded amount of diagnostic output.

A failed test rolls the patch back and triggers BugPilot's existing bounded
repair retry. Docker failures/collection errors stop generation for that item;
**they are not treated as failed bug fixes**. If no matching public tests are
found, the patch may pass the existing *static safety* checks but is explicitly
recorded with `public_test_status: skipped` — **not tested and not resolved**.

## Opt-in configuration

Save a local JSON file (an example is supplied) with only public repository
names and image tags:

```json
{
  "schema_version": 1,
  "images": {
    "sympy/sympy": "bugpilot-public-tests:sympy-local"
  }
}
```

Build the referenced image locally **before** starting prediction generation.
It must contain a compatible pinned Python/test environment for that public
repo and revision, without the gold patch, SWE-bench evaluation test patch,
FAIL_TO_PASS/PASS_TO_PASS test details, or private tests. The v4 smoke image
`bugpilot-public-tests:smoke` has pytest only; **do not use it for real
SWE-bench prediction generation**. The verifier never installs dependencies,
never pulls images and never runs arbitrary model-generated shell commands.

Dry-run dataset selection, without model calls or image checks:

```bash
python -m evaluation.swebench.current.generate --dry-run --count 2 --seed bugpilot-v4-dev --output-dir evaluation/swebench/current/runs/v4_dev_dry --public-test-images evaluation/swebench/current/public_test_images.example.json
```

After building and validating repo-specific images, supply the manifest to a
normal generation command (omit `--dry-run`). Only configured repositories use
public-test verification. Repositories without a configured image retain static
verification and are recorded as `disabled`.

## Limitations that matter

- This is **not** the official SWE-bench correctness harness. Public passing
  tests are regression signals, not proof that the issue was solved.
- Filenames are matched conservatively, so many issues will have *no* selected
  tests, especially Django's custom test runner and tests with unrelated names.
  The current verifier runs pytest only; do not claim it supports every repo.
- Dependencies must be pre-built in appropriate test images. A missing image,
  collection error, timeout, or missing dependency is an *infrastructure error*.
- The current strategy does not compare baseline failures against patched
  failures. A pre-existing failing public test can cause an unnecessary retry.
- The source checkout must be the public base commit. Never use evaluation
  test patches or hidden-test metadata to select tests or configure images.
- Freeze the v4 implementation before evaluating a **fresh untouched held-out
  sample** and use the official SWE-bench harness for the end-to-end score.
  The historical v3 result remains 2 of 10 selected (20%).
