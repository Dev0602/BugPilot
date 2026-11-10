# BugPilot v4: real SymPy public-test smoke test

This package adds one Dockerfile and one dev diagnostic script. It does not overwrite the solver or evaluation code. Run in your existing BugPilot project root:

```bash
docker build -t bugpilot-public-tests:sympy-local -f evaluation/swebench/current/docker/PublicTestSymPy.Dockerfile evaluation/swebench/current/docker && python -m scripts.smoke_v4_sympy_public_tests
```

It uses the existing local v3 development checkout of `sympy__sympy-18835`, and runs only `sympy/utilities/tests/test_iterables.py`, selected from the public repository file layout. It doesn't invoke Claude, change the checkout, access hidden tests, or calculate a SWE-bench score.

The Docker image contains only pinned pytest and mpmath packages. Dependency download occurs at Docker build time. Runtime testing is offline inside the restricted Docker verifier.

If the result is `infrastructure_error`, inspect the last diagnostic lines: the historical repo may need a different compatible Python / pytest / mpmath combination. Do not treat infrastructure errors as patch failures. If `failed`, compare against unpatched baseline before using a failure to justify repair retries.

Do not substitute the generic `smoke` image for this image. A successful run verifies infrastructure, not the target issue resolution. Subsequent work will configure a test-image manifest and validate image support for each repo/version before final frozen held-out evaluation.
