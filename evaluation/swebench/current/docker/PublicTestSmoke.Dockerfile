# Smoke-test image ONLY. Not a complete dependency environment for SWE-bench.
# The source checkout is mounted read-only at runtime by public_test_verifier.py.
FROM python:3.11-slim-bookworm
RUN python -m pip install --no-cache-dir 'pytest==8.4.2'
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
USER 65534:65534
WORKDIR /tmp
