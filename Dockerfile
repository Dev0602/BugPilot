FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir pytest==9.1.1 pytest-cov==7.1.0 \
    && groupadd --gid 10001 bugpilot \
    && useradd \
        --uid 10001 \
        --gid 10001 \
        --create-home \
        --shell /usr/sbin/nologin \
        bugpilot \
    && mkdir -p /app /workspace /deps \
    && chown -R bugpilot:bugpilot /app /workspace /deps

WORKDIR /app

USER bugpilot:bugpilot