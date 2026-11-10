import argparse
import json
import time
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

from backend.app.agent import (
    apply_function_patch,
    run_tests,
)
from backend.app.config import (
    INPUT_COST_PER_M,
    MODEL,
    OUTPUT_COST_PER_M,
)
from backend.app.tools import read_file, write_file


load_dotenv()
client = Anthropic()


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


def build_repository_snapshot(bug_dir):
    """
    Build a one-shot repository snapshot for the baseline model.

    The baseline receives the repository in one prompt but is not told
    which source file contains the bug.
    """

    root = Path(bug_dir).resolve()

    if not root.exists():
        raise FileNotFoundError(
            f"Benchmark directory does not exist: {bug_dir}"
        )

    sections = []

    for path in sorted(root.rglob("*.py")):
        if not path.is_file():
            continue

        relative_path = path.relative_to(root)

        try:
            content = path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            continue

        sections.append(
            f"FILE: {relative_path}\n"
            f"--------------------\n"
            f"{content}\n"
        )

    if not sections:
        raise RuntimeError(
            f"No Python files found in {bug_dir}"
        )

    return "\n".join(sections)


def parse_baseline_response(text):
    """
    Parse the one-shot baseline's marker-based response.

    Marker-based output avoids asking the model to JSON-escape
    multiline Python code.
    """

    text = text.strip()

    file_marker = "FILE_PATH:"
    function_marker = "FUNCTION_NAME:"
    code_start = "FIXED_FUNCTION_START"
    code_end = "FIXED_FUNCTION_END"

    if file_marker not in text:
        raise ValueError(
            "Missing FILE_PATH marker."
        )

    if function_marker not in text:
        raise ValueError(
            "Missing FUNCTION_NAME marker."
        )

    if code_start not in text or code_end not in text:
        raise ValueError(
            "Missing fixed-function markers."
        )

    file_section = text.split(
        file_marker,
        1,
    )[1]

    file_path = (
        file_section
        .splitlines()[0]
        .strip()
    )

    function_section = text.split(
        function_marker,
        1,
    )[1]

    function_name = (
        function_section
        .splitlines()[0]
        .strip()
    )

    fixed_function_code = (
        text.split(
            code_start,
            1,
        )[1]
        .split(
            code_end,
            1,
        )[0]
        .strip()
    )

    if fixed_function_code.startswith("```"):
        lines = fixed_function_code.splitlines()

        if (
            lines
            and lines[0]
            .strip()
            .startswith("```")
        ):
            lines = lines[1:]

        if (
            lines
            and lines[-1]
            .strip()
            == "```"
        ):
            lines = lines[:-1]

        fixed_function_code = (
            "\n".join(lines).strip()
        )

    if not file_path:
        raise ValueError(
            "Empty FILE_PATH."
        )

    if not function_name:
        raise ValueError(
            "Empty FUNCTION_NAME."
        )

    if not fixed_function_code:
        raise ValueError(
            "Empty fixed function."
        )

    return {
        "file_path": file_path,
        "function_name": function_name,
        "fixed_function_code": (
            fixed_function_code
        ),
    }


def validate_target_file(
    bug_dir,
    file_path,
):
    """
    Reject unsafe paths and test-file modifications.
    """

    if not isinstance(
        file_path,
        str,
    ):
        raise ValueError(
            "file_path must be a string."
        )

    root = Path(
        bug_dir
    ).resolve()

    target = (
        root
        / file_path
    ).resolve()

    try:
        relative = (
            target.relative_to(root)
        )

    except ValueError as exc:
        raise ValueError(
            "Model attempted to modify "
            "a file outside the benchmark "
            "repository."
        ) from exc

    if not target.exists():
        raise ValueError(
            "Model selected a file that "
            f"does not exist: {file_path}"
        )

    if target.name.startswith(
        "test_"
    ):
        raise ValueError(
            "Baseline attempted to "
            "modify a test file."
        )

    if target.suffix != ".py":
        raise ValueError(
            "Baseline may modify only "
            "Python source files."
        )

    return str(relative)


def _failure_result(
    bug_dir,
    cost_usd,
    latency,
    coverage,
    stop_reason,
    file_path=None,
    function_name=None,
):
    """
    Build a consistent failed baseline result.
    """

    return {
        "bug": bug_dir,
        "success": False,
        "attempts": 1,
        "cost_usd": round(
            cost_usd,
            5,
        ),
        "latency_sec": round(
            latency,
            1,
        ),
        "file_path": file_path,
        "function_name": function_name,
        "coverage": coverage,
        "stop_reason": stop_reason,
    }


def baseline_fix(bug_dir):
    """
    Fair one-shot comparison baseline.

    Characteristics:

    - same Claude model as BugPilot
    - receives failing test output
    - receives repository snapshot
    - receives no oracle target filename
    - no tool calls
    - no retries
    - exactly one model response
    - uses the same AST patch engine
    - uses the same Docker verification
    - failed repairs are rolled back
    """

    print(
        f"\n{'=' * 72}"
    )

    print(
        f"BASELINE: {bug_dir}"
    )

    print("=" * 72)

    (
        passed,
        test_output,
        coverage,
    ) = run_tests(
        bug_dir
    )

    if passed:
        print(
            "Already passing — "
            "baseline skipped."
        )

        return {
            "bug": bug_dir,
            "success": True,
            "attempts": 0,
            "cost_usd": 0,
            "latency_sec": 0,
            "file_path": None,
            "function_name": None,
            "coverage": coverage,
            "stop_reason": (
                "already_passing"
            ),
        }

    repository_snapshot = (
        build_repository_snapshot(
            bug_dir
        )
    )

    prompt = f"""
You are evaluating a one-shot software repair baseline.

A repository contains a bug that causes its tests to fail.

You are NOT told which source file contains the bug.

You receive the failing test output and a snapshot of the repository.

Your task:

1. Identify the source file responsible for the failure.
2. Identify the exact function or method containing the bug.
3. Produce the smallest correct repair.
4. Do not modify test files.
5. You get only one model response and no repository tools.

Your response must use EXACTLY this format:

FILE_PATH: relative/path/to/source.py
FUNCTION_NAME: function_name
FIXED_FUNCTION_START
def function_name(...):
    ...
FIXED_FUNCTION_END

If the target is a class method and its name is ambiguous,
use a qualified name such as Calculator.add for FUNCTION_NAME.

Return only the corrected function, not the entire file.

Do not include decorators in the corrected function.
Existing decorators are preserved by the patch engine.

Do not modify test files.

FAILING TEST OUTPUT
===================

{test_output}

REPOSITORY SNAPSHOT
===================

{repository_snapshot}
"""

    start_time = time.time()

    try:
        response = (
            client.messages.create(
                model=MODEL,
                max_tokens=4000,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )
        )

    except Exception as exc:
        latency = (
            time.time()
            - start_time
        )

        print(
            "Baseline API request "
            f"failed: {exc}"
        )

        return _failure_result(
            bug_dir=bug_dir,
            cost_usd=0,
            latency=latency,
            coverage=coverage,
            stop_reason="api_error",
        )

    latency = (
        time.time()
        - start_time
    )

    input_tokens = (
        response.usage.input_tokens
    )

    output_tokens = (
        response.usage.output_tokens
    )

    cost_usd = (
        input_tokens
        / 1_000_000
        * INPUT_COST_PER_M
        + output_tokens
        / 1_000_000
        * OUTPUT_COST_PER_M
    )

    text_parts = [
        block.text
        for block
        in response.content
        if block.type == "text"
    ]

    response_text = (
        "".join(
            text_parts
        ).strip()
    )

    if not response_text:
        print(
            "Baseline returned an "
            "empty response."
        )

        return _failure_result(
            bug_dir=bug_dir,
            cost_usd=cost_usd,
            latency=latency,
            coverage=coverage,
            stop_reason=(
                "empty_model_response"
            ),
        )

    try:
        parsed = (
            parse_baseline_response(
                response_text
            )
        )

    except ValueError as exc:
        print(
            "Baseline returned an "
            f"invalid response: {exc}"
        )

        print(
            "\nRAW RESPONSE:"
        )

        print(
            response_text[-2000:]
        )

        return _failure_result(
            bug_dir=bug_dir,
            cost_usd=cost_usd,
            latency=latency,
            coverage=coverage,
            stop_reason=(
                "invalid_response"
            ),
        )

    try:
        target_file = (
            validate_target_file(
                bug_dir,
                parsed["file_path"],
            )
        )

    except ValueError as exc:
        print(
            f"Invalid target file: {exc}"
        )

        return _failure_result(
            bug_dir=bug_dir,
            cost_usd=cost_usd,
            latency=latency,
            coverage=coverage,
            stop_reason=(
                "invalid_target_file"
            ),
            file_path=(
                parsed["file_path"]
            ),
            function_name=(
                parsed[
                    "function_name"
                ]
            ),
        )

    original_code = read_file(
        target_file,
        bug_dir,
    )

    try:
        patched_code = (
            apply_function_patch(
                original_code,
                parsed[
                    "function_name"
                ],
                parsed[
                    "fixed_function_code"
                ],
            )
        )

    except ValueError as exc:
        print(
            "Baseline patch could "
            f"not be applied: {exc}"
        )

        return _failure_result(
            bug_dir=bug_dir,
            cost_usd=cost_usd,
            latency=latency,
            coverage=coverage,
            stop_reason=(
                "patch_application_failed"
            ),
            file_path=target_file,
            function_name=(
                parsed[
                    "function_name"
                ]
            ),
        )

    write_file(
        target_file,
        patched_code,
        bug_dir,
    )

    try:
        (
            passed,
            verification_output,
            coverage,
        ) = run_tests(
            bug_dir
        )

    except Exception as exc:
        # Always restore the benchmark
        # if verification itself fails.
        write_file(
            target_file,
            original_code,
            bug_dir,
        )

        print(
            "Baseline verification "
            f"error: {exc}"
        )

        return _failure_result(
            bug_dir=bug_dir,
            cost_usd=cost_usd,
            latency=latency,
            coverage=coverage,
            stop_reason=(
                "verification_error"
            ),
            file_path=target_file,
            function_name=(
                parsed[
                    "function_name"
                ]
            ),
        )

    if passed:
        print(
            "✓ BASELINE SUCCESS | "
            f"file={target_file} | "
            f"function="
            f"{parsed['function_name']} | "
            f"cost=${cost_usd:.5f} | "
            f"time={latency:.1f}s"
        )

        return {
            "bug": bug_dir,
            "success": True,
            "attempts": 1,
            "cost_usd": round(
                cost_usd,
                5,
            ),
            "latency_sec": round(
                latency,
                1,
            ),
            "file_path": (
                target_file
            ),
            "function_name": (
                parsed[
                    "function_name"
                ]
            ),
            "coverage": coverage,
            "stop_reason": (
                "tests_passed"
            ),
        }

    # A failed one-shot repair must not
    # contaminate subsequent evaluations.
    write_file(
        target_file,
        original_code,
        bug_dir,
    )

    print(
        "✗ BASELINE FAILED | "
        f"file={target_file} | "
        f"function="
        f"{parsed['function_name']}"
    )

    print(
        verification_output[
            -1200:
        ]
    )

    return _failure_result(
        bug_dir=bug_dir,
        cost_usd=cost_usd,
        latency=latency,
        coverage=coverage,
        stop_reason=(
            "tests_failed"
        ),
        file_path=target_file,
        function_name=(
            parsed[
                "function_name"
            ]
        ),
    )


def run_all():
    results = []

    for bug_dir in BUGS:
        result = baseline_fix(
            bug_dir
        )

        results.append(
            result
        )

    successes = sum(
        1
        for result in results
        if result["success"]
    )

    infrastructure_errors = sum(
        1
        for result in results
        if result["stop_reason"]
        in {
            "api_error",
            "verification_error",
        }
    )

    total_cost = sum(
        result["cost_usd"]
        for result in results
    )

    total_latency = sum(
        result["latency_sec"]
        for result in results
    )

    print(
        f"\n{'=' * 72}"
    )

    print(
        "ONE-SHOT BASELINE SUMMARY"
    )

    print("=" * 72)

    for result in results:
        status = (
            "PASSED"
            if result["success"]
            else "FAILED"
        )

        print(
            f"{result['bug']}: "
            f"{status} | "
            f"{result['stop_reason']}"
        )

    print()

    print(
        f"Resolved: "
        f"{successes}/"
        f"{len(results)} "
        f"("
        f"{successes / len(results) * 100:.1f}%"
        f")"
    )

    print(
        "Infrastructure errors: "
        f"{infrastructure_errors}"
    )

    print(
        "Total cost: "
        f"${total_cost:.5f}"
    )

    print(
        "Total model latency: "
        f"{total_latency:.1f}s"
    )

    results_dir = Path(
        "evaluation/internal/results"
    )

    results_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = (
        time.strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    output_file = (
        results_dir
        / (
            f"baseline_"
            f"{timestamp}.json"
        )
    )

    output_file.write_text(
        json.dumps(
            {
                "model": MODEL,
                "type": (
                    "one_shot_baseline"
                ),
                "resolved": (
                    successes
                ),
                "total": len(
                    results
                ),
                "resolve_rate": (
                    successes
                    / len(results)
                ),
                "infrastructure_errors": (
                    infrastructure_errors
                ),
                "total_cost_usd": round(
                    total_cost,
                    5,
                ),
                "total_latency_sec": round(
                    total_latency,
                    1,
                ),
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "\nSaved results to: "
        f"{output_file}"
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run BugPilot's one-shot "
            "comparison baseline."
        )
    )

    group = (
        parser
        .add_mutually_exclusive_group(
            required=True
        )
    )

    group.add_argument(
        "--bug",
        help=(
            "Run one benchmark folder, "
            "for example "
            "benchmarks/internal_bugs/bug_01_calculator"
        ),
    )

    group.add_argument(
        "--all",
        action="store_true",
        help=(
            "Run all 20 "
            "benchmark bugs."
        ),
    )

    args = parser.parse_args()

    if args.all:
        run_all()
        return

    result = baseline_fix(
        args.bug
    )

    print(
        "\nFINAL BASELINE RESULT:"
    )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()