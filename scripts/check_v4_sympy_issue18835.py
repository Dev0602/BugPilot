"""Development-only, public-issue reproduction for sympy__sympy-18835.

Tests an issue-derived behavior on a clean HEAD export and a copy with the
existing v3 development patch. Never reads gold patches, harness test patches,
FAIL_TO_PASS/PASS_TO_PASS, or hidden tests. Never changes the original checkout.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from evaluation.swebench.current.public_test_verifier import run_public_tests
from scripts.check_v4_sympy_baseline import CHECKOUT, IMAGE, SOURCE, archive_head

REPRO_PATH = 'sympy/utilities/tests/test_bugpilot_issue18835_repro.py'
REPRO_CONTENT = '''"""Public issue sympy__sympy-18835: uniq must reject resizing its list."""
import pytest
from sympy.utilities.iterables import uniq


def test_uniq_rejects_list_shrinking_during_iteration():
    values = list("THISTLE")
    unique_values = uniq(values)
    assert next(unique_values) == "T"
    values.remove("T")
    with pytest.raises(RuntimeError):
        list(unique_values)


def test_uniq_unchanged_list_still_returns_unique_values():
    assert list(uniq(list("THISTLE"))) == ["T", "H", "I", "S", "L", "E"]
'''


def classify(baseline: dict, patched: dict) -> str:
    a, b = baseline['status'], patched['status']
    if 'infrastructure_error' in (a, b):
        return 'INFRASTRUCTURE ERROR — comparison is inconclusive.'
    if (a, b) == ('failed', 'passed'):
        return 'RED TO GREEN — v3 patch fixes this public-issue reproduction.'
    if (a, b) == ('failed', 'failed'):
        return 'STILL FAILING — v3 patch does not fix this public-issue reproduction.'
    if (a, b) == ('passed', 'passed'):
        return 'BOTH PASS — reproduction does not distinguish baseline from patch.'
    if (a, b) == ('passed', 'failed'):
        return 'REGRESSION — patch breaks a behavior that passes at baseline.'
    return 'INCONCLUSIVE — inspect test result statuses.'


def _write_repro(checkout: Path) -> None:
    dest = checkout / REPRO_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise RuntimeError('Unexpected existing reproduction filename in checkout')
    dest.write_text(REPRO_CONTENT, encoding='utf-8')


def main() -> int:
    if not (CHECKOUT / SOURCE).is_file():
        print('Missing development checkout:', CHECKOUT)
        return 2
    changed = subprocess.run(
        ['git', '-C', str(CHECKOUT), 'diff', '--name-only', 'HEAD', '--', SOURCE],
        capture_output=True, text=True,
    )
    if changed.returncode != 0 or SOURCE not in changed.stdout.splitlines():
        print('Missing v3 working-tree patch for', SOURCE,
              '— cannot compare baseline and patch accurately.')
        return 2

    print('Case: sympy__sympy-18835 — uniq resized-list RuntimeError')
    print('Image:', IMAGE)
    print('Temporary checkouts only; original workspace is read-only to this script.')
    try:
        with tempfile.TemporaryDirectory(prefix='bugpilot-issue18835-') as root:
            baseline_dir = Path(root) / 'baseline'
            patched_dir = Path(root) / 'patched'
            baseline_dir.mkdir()
            patched_dir.mkdir()
            archive_head(CHECKOUT, baseline_dir)
            # Both snapshots start from identical clean HEAD. Only the known
            # v3 patched source is copied over to the second snapshot.
            archive_head(CHECKOUT, patched_dir)
            shutil.copyfile(CHECKOUT / SOURCE, patched_dir / SOURCE)
            _write_repro(baseline_dir)
            _write_repro(patched_dir)
            baseline = run_public_tests(baseline_dir, [REPRO_PATH], image=IMAGE, timeout_seconds=480)
            patched = run_public_tests(patched_dir, [REPRO_PATH], image=IMAGE, timeout_seconds=480)
    except Exception as exc:
        print('Setup failed:', type(exc).__name__, str(exc)[-700:])
        return 2

    for label, result in [('Clean HEAD baseline', baseline), ('V3 patched copy', patched)]:
        print(f'\n{label}: {result["status"]} | {result.get("reason")}')
        if result['status'] != 'passed':
            print('Test output (tail):\n', result.get('feedback', '')[-1600:])
    print('\n', classify(baseline, patched))
    print('This is development-only public issue evidence, NOT an official SWE-bench score.')
    return 2 if 'infrastructure_error' in (baseline['status'], patched['status']) else 0


if __name__ == '__main__':
    sys.exit(main())
