"""Exercise real Docker verification against disposable public-test fixtures.

Run from the BugPilot repository root after building the trusted smoke image.
No Claude calls, SWE-bench cases, gold patches, or hidden tests are involved.
"""
from pathlib import Path
from tempfile import TemporaryDirectory

from evaluation.swebench.current.public_test_verifier import run_public_tests


IMAGE = 'bugpilot-public-tests:smoke'


def run():
    # Keep the fixture beneath the repository folder (normally shared with
    # Docker Desktop), not in MacOS's private /var/folders temp directory.
    root = Path.cwd().resolve()
    with TemporaryDirectory(prefix='.bugpilot-public-smoke-', dir=root) as temp:
        directory = Path(temp)
        target = directory / 'test_public_smoke.py'
        target.write_text('def test_example():\n    assert 2 + 2 == 4\n', encoding='utf-8')
        success = run_public_tests(directory, ['test_public_smoke.py'],
                                   image=IMAGE, timeout_seconds=120)
        print('Passing public test:', success['status'])
        if success['status'] != 'passed':
            print(success.get('feedback', '')[-1200:])
            raise SystemExit('ERROR: Docker public-test smoke run failed')

        target.write_text('def test_example():\n    assert 2 + 2 == 5\n', encoding='utf-8')
        failure = run_public_tests(directory, ['test_public_smoke.py'],
                                   image=IMAGE, timeout_seconds=120)
        print('Failing public test:', failure['status'])
        if failure['status'] != 'failed':
            print(failure.get('feedback', '')[-1200:])
            raise SystemExit('ERROR: Docker did not identify an actual assertion failure')

    print('OK: real offline Docker verification detects both passing and failing public tests.')
    print('This is a sandbox smoke test, NOT a SWE-bench correctness result.')


if __name__ == '__main__':
    run()
