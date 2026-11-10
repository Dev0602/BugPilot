"""Optional no-oracle public-test execution for BugPilot SWE-bench mode.

Use only with a locally prepared, project-compatible Docker image that was
built without any SWE-bench gold patch, evaluation test patch, or hidden tests.
This module does NOT select tests or install dependencies. The caller supplies
trusted, existing public-test paths from the checkout; never accept model-made
shell commands or SWE-bench evaluation metadata as test input.
"""

from __future__ import annotations

import re
from pathlib import Path

_IMAGE_NAME = re.compile(r"^bugpilot-public-tests:[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
_MAX_TEST_TARGETS = 8
_MAX_LOG_CHARS = 4000

# Fixed code executed inside the isolated container, not on the host.
# Preserve symlinks instead of following links outside the checkout.
_RUNNER = """
import os
import shutil
import sys
shutil.copytree(
    '/source', '/tmp/workspace', symlinks=True,
    ignore=shutil.ignore_patterns(
        '.git', '.env', '.env.*', '.venv', 'venv',
        'node_modules', '__pycache__', '.pytest_cache'
    ),
)
os.chdir('/tmp/workspace')
os.execv(sys.executable, [
    sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
    '--disable-warnings', *sys.argv[1:]
])
""".strip()


def _validate_test_targets(repository_path: Path, targets: list[str]) -> list[str]:
    """Accept paths to existing public Python test files, never CLI options."""
    if not isinstance(targets, (list, tuple)) or not 1 <= len(targets) <= _MAX_TEST_TARGETS:
        raise ValueError(f"Expected 1 to {_MAX_TEST_TARGETS} public-test targets")

    validated = []
    for target in targets:
        if not isinstance(target, str) or len(target) > 300 or not target:
            raise ValueError("Invalid public-test target")
        if any(char in target for char in ('\x00', '\n', '\r')):
            raise ValueError("Invalid characters in public-test target")
        file_part, separator, node_part = target.partition('::')
        if not file_part or file_part.startswith('-') or Path(file_part).is_absolute():
            raise ValueError("Public tests must use relative Python file paths")
        if separator and (not node_part or node_part.startswith('-')):
            raise ValueError("Invalid public-test node identifier")
        test_file = (repository_path / file_part).resolve()
        if not test_file.is_relative_to(repository_path) or not test_file.is_file():
            raise ValueError(f"Missing or outside-checkout public test: {file_part}")
        if test_file.suffix != '.py' or not (
            test_file.name.startswith('test_') or test_file.name.endswith('_test.py')
        ):
            raise ValueError(f"Not an explicitly named Python test file: {file_part}")
        validated.append(target)
    return validated


def run_public_tests(
    repository_path,
    test_targets,
    *,
    image,
    timeout_seconds=300,
    docker_client=None,
):
    """Run selected *public* tests in a restricted offline Docker container.

    Status is one of passed, failed, or infrastructure_error. Non-test outcomes
    (missing image, timeout, pytest setup error) must NOT be treated as an
    assertion failure or as evidence of a correct patch.

    This is optional verification, not the official SWE-bench harness.
    """
    repo = Path(repository_path).resolve()
    if not repo.is_dir():
        raise ValueError("Repository directory does not exist")
    targets = _validate_test_targets(repo, test_targets)
    if not isinstance(image, str) or not _IMAGE_NAME.fullmatch(image):
        raise ValueError("Use an approved local image: bugpilot-public-tests:<tag>")
    if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 1800:
        raise ValueError("timeout_seconds must be an integer in [1, 1800]")

    container = None
    try:
        if docker_client is None:
            import docker
            docker_client = docker.from_env()

        # The image must already exist. No implicit image pulls or networked
        # dependency installation are permitted in this executor.
        docker_client.images.get(image)
        container = docker_client.containers.run(
            image,
            command=['python', '-c', _RUNNER, *targets],
            volumes={str(repo): {'bind': '/source', 'mode': 'ro'}},
            working_dir='/tmp',
            environment={
                'PYTHONDONTWRITEBYTECODE': '1',
                'PYTHONNOUSERSITE': '1',
                'HOME': '/tmp',
                'TMPDIR': '/tmp',
            },
            detach=True,
            user='65534:65534',
            network_disabled=True,
            read_only=True,
            tmpfs={'/tmp': 'rw,nosuid,size=1024m'},
            mem_limit='3g',
            nano_cpus=2_000_000_000,
            pids_limit=128,
            cap_drop=['ALL'],
            security_opt=['no-new-privileges:true'],
        )
        try:
            finished = container.wait(timeout=timeout_seconds)
        except Exception as exc:
            # In particular, the Docker API can raise requests.ReadTimeout.
            try:
                container.kill()
            except Exception:
                pass
            return {
                'status': 'infrastructure_error',
                'reason': 'container_wait_failed_or_timed_out',
                'feedback': f'Public-test container did not finish: {type(exc).__name__}',
                'test_targets': targets,
            }

        exit_code = finished.get('StatusCode')
        logs = container.logs().decode('utf-8', errors='replace')
        if exit_code == 0:
            status, reason = 'passed', 'public_tests_passed'
        elif exit_code == 1 and re.search(r'\b[1-9]\d* failed\b|(?m:^FAILED\s)', logs):
            status, reason = 'failed', 'public_tests_failed'
        else:
            # Exit code 1 can also mean missing pytest, imports, or a crashed
            # environment. Never label these as confirmed test failures.
            status, reason = 'infrastructure_error', 'pytest_setup_or_collection_error'
        return {
            'status': status,
            'reason': reason,
            'exit_code': exit_code,
            'feedback': logs[-_MAX_LOG_CHARS:],
            'test_targets': targets,
        }
    except Exception as exc:
        return {
            'status': 'infrastructure_error',
            'reason': 'docker_setup_error',
            'feedback': f'Public-test Docker setup failed: {type(exc).__name__}: {exc}',
            'test_targets': targets,
        }
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
