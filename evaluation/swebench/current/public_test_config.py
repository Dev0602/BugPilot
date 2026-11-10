"""Trusted opt-in image configuration for public-only SWE-bench test runs."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .public_test_verifier import _IMAGE_NAME

_REPO = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')


def load_public_test_images(config_path):
    """Read a minimal repo -> local-image manifest, with no test-oracle fields."""
    path = Path(config_path)
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or set(data) != {'schema_version', 'images'}:
        raise ValueError('Manifest must contain only schema_version and images')
    if data['schema_version'] != 1 or type(data['schema_version']) is not int:
        raise ValueError('Unsupported public-test manifest version')
    images = data['images']
    if not isinstance(images, dict):
        raise ValueError('Manifest images must be an object')
    for repo, image in images.items():
        if (not isinstance(repo, str) or not _REPO.fullmatch(repo)
                or any(part in {".", ".."} for part in repo.split("/"))):
            raise ValueError('Invalid public repository name')
        if not isinstance(image, str) or not _IMAGE_NAME.fullmatch(image):
            raise ValueError(f'Invalid locally built public-test image for {repo}')
    return dict(images)


def preflight_public_test_images(images):
    """Require all configured images already to exist; never implicitly pull."""
    if not images:
        return
    try:
        import docker
        client = docker.from_env()
        client.ping()
        for image in sorted(set(images.values())):
            client.images.get(image)
    except Exception as exc:
        raise RuntimeError(
            'Public-test image preflight failed. Build project-compatible '
            'images locally before using --public-test-images: '
            f'{type(exc).__name__}: {exc}'
        ) from exc
