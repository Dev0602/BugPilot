# Minimal public-only dependencies for a SymPy SWE-bench Lite development smoke test.
# NO gold patches, FAIL_TO_PASS/PASS_TO_PASS data, or SWE-bench tests are installed.
# The checked-out public repo is mounted read-only by public_test_verifier.py at runtime.
FROM python:3.11-slim-bookworm
RUN python -m pip install --no-cache-dir 'pytest==7.4.4' 'mpmath==1.3.0'
WORKDIR /tmp
