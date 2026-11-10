import json
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPO_ROOT),
    )


from backend.app.agent import solve_bug
from backend.app.config import MAX_ATTEMPTS, MODEL
from backend.app.db import (
    finish_run,
    init_db,
    save_result,
    start_run,
)


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

BENCHMARK_NAME = "internal-20-bug"


def classify_exception(exc):
    """
    Convert an exception into a benchmark failure category.

    agent_error:
        Model/protocol/repair-agent failures.

    infrastructure_error:
        Docker, sandbox, dependency installation, or
        environment execution failures.

    unexpected_error:
        Anything not recognized above.
    """

    message = str(exc).lower()

    infrastructure_markers = (
        "docker is not available",
        "sandbox test execution",
        "dependency installation",
        "container",
        "docker",
        "timed out",
        "timeout",
    )

    agent_markers = (
        "claude did not return",
        "claude did not submit",
        "anthropic client",
        "submit_fix",
        "tool call",
        "generated replacement",
        "replacement function",
        "could not find function",
        "function name",
    )

    if isinstance(
        exc,
        ValueError,
    ):
        return "agent_error"

    if any(
        marker in message
        for marker in infrastructure_markers
    ):
        return "infrastructure_error"

    if any(
        marker in message
        for marker in agent_markers
    ):
        return "agent_error"

    return "unexpected_error"


def error_result(
    bug_dir,
    exc,
):
    category = classify_exception(
        exc
    )

    return {
        "bug": bug_dir,
        "success": False,
        "attempts": 0,
        "cost_usd": 0,
        "latency_sec": 0,
        "diagnosis": None,
        "file_path": None,
        "function_name": None,
        "coverage": None,
        "stop_reason": category,
        "outcome": category,
        "error_type": (
            type(exc).__name__
        ),
        "error": str(exc),
    }


def normalized_outcome(
    result,
):
    if result.get(
        "success"
    ):
        return "success"

    stop_reason = result.get(
        "stop_reason"
    )

    if stop_reason in {
        "agent_error",
        "infrastructure_error",
        "unexpected_error",
    }:
        return stop_reason

    return "repair_failed"


def main():
    print(
        "=" * 72
    )

    print(
        "BUGPILOT INTERNAL BENCHMARK"
    )

    print(
        "=" * 72
    )

    init_db()

    timestamp = time.strftime(
        "%Y%m%d_%H%M%S"
    )

    run_id = (
        f"internal_{timestamp}"
    )

    print(
        f"Run ID: {run_id}"
    )

    start_run(
        run_id=run_id,
        model=MODEL,
        benchmark=BENCHMARK_NAME,
        metadata={
            "bug_count": len(
                BUGS
            ),
            "max_attempts": (
                MAX_ATTEMPTS
            ),
            "runner": (
                "evaluation/internal/"
                "run_bugpilot.py"
            ),
        },
    )

    results = []

    try:
        for index, bug_dir in enumerate(
            BUGS,
            1,
        ):
            print(
                f"\n[{index}/{len(BUGS)}] "
                f"Running {bug_dir}"
            )

            try:
                result = solve_bug(
                    bug_dir,
                    max_attempts=(
                        MAX_ATTEMPTS
                    ),
                    run_id=run_id,
                )

                result[
                    "outcome"
                ] = normalized_outcome(
                    result
                )

            except Exception as exc:
                category = (
                    classify_exception(
                        exc
                    )
                )

                print(
                    f"✗ {category}: "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

                result = error_result(
                    bug_dir,
                    exc,
                )

            results.append(
                result
            )

            # Persist each result immediately.
            # If the benchmark is interrupted later,
            # completed cases are still available.
            save_result(
                result,
                run_id,
            )

    except BaseException:
        finish_run(
            run_id,
            status="failed",
        )

        raise

    else:
        finish_run(
            run_id,
            status="completed",
        )

    resolved = sum(
        1
        for result in results
        if (
            result.get(
                "outcome"
            )
            == "success"
        )
    )

    repair_failures = sum(
        1
        for result in results
        if (
            result.get(
                "outcome"
            )
            == "repair_failed"
        )
    )

    agent_errors = sum(
        1
        for result in results
        if (
            result.get(
                "outcome"
            )
            == "agent_error"
        )
    )

    infrastructure_errors = sum(
        1
        for result in results
        if (
            result.get(
                "outcome"
            )
            == "infrastructure_error"
        )
    )

    unexpected_errors = sum(
        1
        for result in results
        if (
            result.get(
                "outcome"
            )
            == "unexpected_error"
        )
    )

    total_attempts = sum(
        result.get(
            "attempts",
            0,
        )
        or 0
        for result in results
    )

    total_cost = sum(
        result.get(
            "cost_usd",
            0,
        )
        or 0
        for result in results
    )

    total_latency = sum(
        result.get(
            "latency_sec",
            0,
        )
        or 0
        for result in results
    )

    retries_used = sum(
        1
        for result in results
        if (
            result.get(
                "attempts",
                0,
            )
            > 1
        )
    )

    repeated_repair_stops = sum(
        1
        for result in results
        if (
            result.get(
                "stop_reason"
            )
            == "repeated_failed_repair"
        )
    )

    print()

    print(
        "=" * 72
    )

    print(
        "BUGPILOT SUMMARY"
    )

    print(
        "=" * 72
    )

    for result in results:
        outcome = result.get(
            "outcome",
            "unknown",
        )

        if outcome == "success":
            status = "PASSED"

        elif outcome == "repair_failed":
            status = (
                "REPAIR FAILED"
            )

        elif outcome == "agent_error":
            status = (
                "AGENT ERROR"
            )

        elif outcome == (
            "infrastructure_error"
        ):
            status = (
                "INFRA ERROR"
            )

        else:
            status = (
                "UNEXPECTED ERROR"
            )

        print(
            f"{result['bug']}: "
            f"{status} | "
            f"attempts="
            f"{result.get('attempts', 0)} | "
            f"reason="
            f"{result.get('stop_reason')}"
        )

    total = len(
        results
    )

    resolve_rate = (
        resolved / total
        if total
        else 0
    )

    print()

    print(
        f"Resolved: "
        f"{resolved}/{total} "
        f"({resolve_rate * 100:.1f}%)"
    )

    print(
        f"Repair failures: "
        f"{repair_failures}"
    )

    print(
        f"Agent errors: "
        f"{agent_errors}"
    )

    print(
        f"Infrastructure errors: "
        f"{infrastructure_errors}"
    )

    print(
        f"Unexpected errors: "
        f"{unexpected_errors}"
    )

    print(
        f"Total repair attempts: "
        f"{total_attempts}"
    )

    print(
        f"Cases requiring retries: "
        f"{retries_used}"
    )

    print(
        f"Repeated-repair early stops: "
        f"{repeated_repair_stops}"
    )

    print(
        f"Total recorded cost: "
        f"${total_cost:.5f}"
    )

    print(
        f"Total recorded model latency: "
        f"{total_latency:.1f}s"
    )

    results_dir = Path(
        "evaluation/internal/results"
    )

    results_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        results_dir
        / f"bugpilot_{timestamp}.json"
    )

    payload = {
        "run_id": run_id,
        "model": MODEL,
        "benchmark": (
            BENCHMARK_NAME
        ),
        "type": (
            "bugpilot_agent"
        ),
        "max_attempts": (
            MAX_ATTEMPTS
        ),
        "resolved": resolved,
        "total": total,
        "resolve_rate": (
            resolve_rate
        ),
        "repair_failures": (
            repair_failures
        ),
        "agent_errors": (
            agent_errors
        ),
        "infrastructure_errors": (
            infrastructure_errors
        ),
        "unexpected_errors": (
            unexpected_errors
        ),
        "total_attempts": (
            total_attempts
        ),
        "cases_requiring_retries": (
            retries_used
        ),
        "repeated_repair_stops": (
            repeated_repair_stops
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
    }

    output_file.write_text(
        json.dumps(
            payload,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"\nRun ID: {run_id}"
    )

    print(
        "Saved results to: "
        f"{output_file}"
    )


if __name__ == "__main__":
    main()