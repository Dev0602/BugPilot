"""Compare a public SymPy test on untouched HEAD and the v3 development patch.

This is a development diagnostic. Neither gold patches nor hidden SWE-bench tests
are read. The original v3 workspace and its saved evidence are never modified.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from evaluation.swebench.current.public_test_verifier import run_public_tests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = (
    PROJECT_ROOT / 'evaluation/swebench/current/runs/v3_final_clean/'
    'workspaces/sympy__sympy-18835'
)
TEST = 'sympy/utilities/tests/test_iterables.py'
SOURCE = 'sympy/utilities/iterables.py'
IMAGE = 'bugpilot-public-tests:sympy-local'


def archive_head(checkout: Path, destination: Path) -> None:
    """Export tracked HEAD files, without checkout/reset or editing the source repo."""
    # Pipe git's tar stream straight to tar; do not buffer large repos in memory.
    process = subprocess.Popen(
        ['git', '-C', str(checkout), 'archive', '--format=tar', 'HEAD'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        extraction = subprocess.run(
            ['tar', '-xf', '-', '-C', str(destination)],
            stdin=process.stdout, capture_output=True, text=True,
        )
    finally:
        if process.stdout is not None:
            process.stdout.close()
    stderr = process.stderr.read().decode('utf-8', errors='replace') if process.stderr else ''
    return_code = process.wait()
    if return_code != 0 or extraction.returncode != 0:
        raise RuntimeError(
            'Could not export clean HEAD snapshot: '
            + (stderr or extraction.stderr or 'unknown git/tar error')[-1000:]
        )
    if not (destination / TEST).is_file():
        raise RuntimeError('HEAD snapshot does not contain the public test file')


def interpret(baseline: dict, patched: dict) -> str:
    if baseline['status'] == 'infrastructure_error' or patched['status'] == 'infrastructure_error':
        return 'INFRASTRUCTURE ERROR: cannot compare public-test behavior.'
    if baseline['status'] == 'failed' and patched['status'] == 'passed':
        return 'USEFUL SIGNAL: public test fails at HEAD and passes with the v3 patch.'
    if baseline['status'] == 'passed' and patched['status'] == 'failed':
        return 'REGRESSION SIGNAL: patch breaks a public test that passes at HEAD.'
    if baseline['status'] == 'passed' and patched['status'] == 'passed':
        return 'REGRESSION COVERAGE ONLY: public tests pass both before and after the patch.'
    return 'BOTH FAILED: inspect whether failures are relevant to the reported issue.'


def main() -> int:
    if not (CHECKOUT / TEST).is_file() or not (CHECKOUT / SOURCE).is_file():
        print('Missing v3 development checkout:', CHECKOUT)
        return 2

    changes = subprocess.run(
        ['git', '-C', str(CHECKOUT), 'diff', '--name-only', 'HEAD', '--', SOURCE],
        capture_output=True, text=True,
    )
    if changes.returncode != 0:
        print('Could not inspect patch:', changes.stderr[-1000:]); return 2
    if SOURCE not in changes.stdout.splitlines():
        print('WARNING: source file has no uncommitted difference from HEAD.')
        print('The checkout might no longer contain the original v3 generated patch.')
        print('Stopping rather than presenting a misleading before/after comparison.')
        return 2

    print('Public test:', TEST)
    print('Image:', IMAGE)
    print('Original v3 development workspace will not be modified.')
    try:
        with tempfile.TemporaryDirectory(prefix='bugpilot-v4-sympy-head-') as temp:
            clean_checkout = Path(temp)
            archive_head(CHECKOUT, clean_checkout)
            baseline = run_public_tests(clean_checkout, [TEST], image=IMAGE, timeout_seconds=480)
            patched = run_public_tests(CHECKOUT, [TEST], image=IMAGE, timeout_seconds=480)
    except Exception as exc:
        print('Environment/setup error:', type(exc).__name__, str(exc)[-1000:])
        return 2

    print('\nClean HEAD baseline:', baseline['status'], '|', baseline.get('reason'))
    print('V3 patched checkout:', patched['status'], '|', patched.get('reason'))
    print('\n', interpret(baseline, patched))
    if baseline['status'] != 'passed':
        print('\nBaseline output (last 600 chars):', baseline.get('feedback', '')[-600:])
    if patched['status'] != 'passed':
        print('\nPatched output (last 600 chars):', patched.get('feedback', '')[-600:])
    print('\nDevelopment diagnostic only — NOT a new SWE-bench resolution score.')
    return 2 if 'infrastructure_error' in (baseline['status'], patched['status']) else 0


if __name__ == '__main__':
    sys.exit(main())
