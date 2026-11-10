from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

BUGS = [
    "benchmarks/internal_bugs/bug_01_calculator",
    "benchmarks/internal_bugs/bug_02_discount",
    "benchmarks/internal_bugs/bug_03_grade",
    "benchmarks/internal_bugs/bug_04_reverse",
    "benchmarks/internal_bugs/bug_05_sum_range",
    "benchmarks/internal_bugs/bug_06_mutable_default",
    "benchmarks/internal_bugs/bug_07_word_count",
    "benchmarks/internal_bugs/bug_08_factorial",
    "benchmarks/internal_bugs/bug_09_ats_exact_match",
    "benchmarks/internal_bugs/bug_10_prime_checker",
    "benchmarks/internal_bugs/bug_11_safe_divide",
    "benchmarks/internal_bugs/bug_12_invalid_input",
    "benchmarks/internal_bugs/bug_13_list_index",
    "benchmarks/internal_bugs/bug_14_dictionary",
    "benchmarks/internal_bugs/bug_15_sets",
    "benchmarks/internal_bugs/bug_16_string_processing",
    "benchmarks/internal_bugs/bug_17_recursion",
    "benchmarks/internal_bugs/bug_18_algorithm",
    "benchmarks/internal_bugs/bug_19_empty_input",
    "benchmarks/internal_bugs/bug_20_buzzword_detection",
]

ANSWER_REVEALING_PATTERNS = [
    "# bug:",
    "#bug:",
    "should be >=",
    "should be <=",
    "wrong index",
    "off by one",
    "doesn't lowercase",
    "does not lowercase",
    "should return",
]


def check_answer_revealing_comments(bug_dir: Path) -> list[str]:
    problems = []

    for file_path in bug_dir.rglob("*.py"):
        if file_path.name.startswith("test_"):
            continue

        try:
            text = file_path.read_text(
                encoding="utf-8",
                errors="replace",
            ).lower()
        except OSError:
            continue

        for pattern in ANSWER_REVEALING_PATTERNS:
            if pattern.lower() in text:
                relative = file_path.relative_to(REPO_ROOT)
                problems.append(
                    f"{relative}: suspicious phrase '{pattern}'"
                )

    return problems


def run_bug_tests(bug_path: Path) -> tuple[int, str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--disable-warnings",
        "--maxfail=1",
    ]

    try:
        result = subprocess.run(
            command,
            cwd=bug_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return 124, "pytest timed out after 30 seconds"

    output = (
        (result.stdout or "")
        + "\n"
        + (result.stderr or "")
    ).strip()

    return result.returncode, output


def main() -> int:
    print("=" * 72)
    print("BUGPILOT INTERNAL BENCHMARK PRE-RUN VALIDATION")
    print("=" * 72)
    print()

    if len(BUGS) != 20:
        print(
            f"✗ Validator configuration error: expected 20 bugs, "
            f"found {len(BUGS)}."
        )
        return 1

    missing = []
    comment_problems = []
    failing_as_expected = []
    unexpectedly_passing = []
    infrastructure_errors = []

    for bug in BUGS:
        bug_path = REPO_ROOT / bug

        if not bug_path.exists():
            missing.append(bug)
            print(f"✗ {bug}: DIRECTORY MISSING")
            continue

        suspicious = check_answer_revealing_comments(bug_path)
        comment_problems.extend(suspicious)

        return_code, output = run_bug_tests(bug_path)

        if return_code == 1:
            failing_as_expected.append(bug)
            print(f"✓ {bug}: FAILING AS EXPECTED")

        elif return_code == 0:
            unexpectedly_passing.append(bug)
            print(f"✗ {bug}: UNEXPECTEDLY PASSING")

        else:
            infrastructure_errors.append(
                {
                    "bug": bug,
                    "return_code": return_code,
                    "output": output,
                }
            )

            print(
                f"✗ {bug}: TEST INFRASTRUCTURE ERROR "
                f"(pytest exit code {return_code})"
            )

    print()
    print("=" * 72)
    print("VALIDATION SUMMARY")
    print("=" * 72)

    print(
        f"Failing as expected: "
        f"{len(failing_as_expected)}/{len(BUGS)}"
    )

    print(
        f"Unexpectedly passing: "
        f"{len(unexpectedly_passing)}"
    )

    print(
        f"Missing benchmark folders: "
        f"{len(missing)}"
    )

    print(
        f"Test infrastructure errors: "
        f"{len(infrastructure_errors)}"
    )

    print(
        f"Answer-revealing source comments: "
        f"{len(comment_problems)}"
    )

    if unexpectedly_passing:
        print("\nUnexpectedly passing benchmarks:")

        for bug in unexpectedly_passing:
            print(f"  - {bug}")

    if missing:
        print("\nMissing benchmarks:")

        for bug in missing:
            print(f"  - {bug}")

    if comment_problems:
        print("\nPotential answer-revealing comments:")

        for problem in comment_problems:
            print(f"  - {problem}")

    if infrastructure_errors:
        print("\nTest infrastructure problems:")

        for error in infrastructure_errors:
            print(
                f"\n--- {error['bug']} "
                f"(exit {error['return_code']}) ---"
            )

            print(error["output"][-1500:])

    valid = (
        len(failing_as_expected) == 20
        and not unexpectedly_passing
        and not missing
        and not infrastructure_errors
        and not comment_problems
    )

    print()

    if valid:
        print(
            "✓ BENCHMARK VALID: all 20 cases are broken, "
            "collect correctly, and contain no obvious answer hints."
        )
        print(
            "✓ BugPilot may now run against this benchmark."
        )
        return 0

    print(
        "✗ BENCHMARK INVALID: fix the issues above before running BugPilot."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
