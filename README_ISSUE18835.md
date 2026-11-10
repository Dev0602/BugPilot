# SymPy issue 18835 — public issue reproduction

The public issue says `uniq` can silently produce incorrect output if its input list changes size while the generator is being consumed. The two new pytest tests (injected into temporary exports of the public repository only) check:

1. Shrinking the list between yields must raise `RuntimeError`.
2. Without changes, `uniq` still returns the correct sequence.

The script imports `archive_head` from the baseline comparison script already installed in the previous update. It requires `bugpilot-public-tests:sympy-local`, also already built.

Run from your project root:

```bash
unzip -o ~/Downloads/BugPilot_v4_SymPy_issue18835_reproduction.zip -d . && python -m pytest -q tests/test_v4_sympy_issue18835.py && python -m scripts.check_v4_sympy_issue18835
```

This is a **development-only** test for a **previously attempted** issue. Do **not** add it to the held-out SWE-bench selection or treat it as official harness evidence. No gold patch, hidden tests, oracle targets, Claude API calls, or modifications to the v3 workspace are involved.
