"""Run one real pre-existing SymPy public test file through BugPilot v4 Docker.

Development diagnostic only. This does not measure SWE-bench resolution, and
neither hidden benchmark tests nor gold patches are used or supplied.
"""
from pathlib import Path
import sys

from evaluation.swebench.current.public_test_verifier import run_public_tests

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "evaluation/swebench/current/runs/v3_final_clean/workspaces/sympy__sympy-18835"
TEST = "sympy/utilities/tests/test_iterables.py"
IMAGE = "bugpilot-public-tests:sympy-local"


def main():
    if not REPO.is_dir() or not (REPO / TEST).is_file():
        print("Cannot find the prior v3 development checkout/test at:")
        print(REPO / TEST)
        print("This script does not clone repositories or call the Claude API.")
        return 2
    print("Development repository:", REPO)
    print("Existing public test:", TEST)
    print("Docker image:", IMAGE)
    print("Running with no network and a read-only source mount...")
    outcome = run_public_tests(REPO, [TEST], image=IMAGE, timeout_seconds=480)
    print("\nPublic test status:", outcome["status"])
    print("Reason:", outcome["reason"])
    print("Exit code:", outcome.get("exit_code"))
    print("\nLast test output:\n", (outcome.get("feedback") or "")[-3500:])
    if outcome["status"] == "passed":
        print("\nSUCCESS: A real public SymPy test file ran successfully in offline Docker.")
        print("This is not an official SWE-bench resolved result.")
        return 0
    if outcome["status"] == "failed":
        print("\nPUBLIC TESTS FAILED: tests ran and reported failures.")
        print("They may already fail on this development checkout; investigate baseline before retrying repairs.")
        return 1
    print("\nINFRASTRUCTURE ERROR: do not use this image for evaluation until fixed.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
