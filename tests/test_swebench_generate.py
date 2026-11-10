from evaluation.swebench.current.agent_adapter import (
    IssueInvestigationError,
)
from evaluation.swebench.current.generate import (
    _record_generation_failure,
)


def test_structured_failure_preserves_usage():
    error = IssueInvestigationError(
        (
            "Claude did not submit "
            "a fix."
        ),
        stop_reason=(
            "turn_limit"
        ),
        usage={
            "input_tokens": 1200,
            "output_tokens": 300,
            "tool_turns": 12,
            "cost_usd": 0.0123,
            "latency_sec": 42.5,
        },
        tool_trace=[
            "search_code",
            "read_file",
            "search_code",
        ],
    )

    outcome = {
        "instance_id": (
            "example__repo-1"
        )
    }

    result = (
        _record_generation_failure(
            outcome,
            error,
        )
    )

    assert (
        result["status"]
        == "generation_failed"
    )

    assert (
        result["stop_reason"]
        == "turn_limit"
    )

    assert (
        result["input_tokens"]
        == 1200
    )

    assert (
        result["output_tokens"]
        == 300
    )

    assert (
        result["tool_turns"]
        == 12
    )

    assert (
        result["cost_usd"]
        == 0.0123
    )

    assert (
        result["latency_sec"]
        == 42.5
    )

    assert (
        result["tool_trace"]
        == [
            "search_code",
            "read_file",
            "search_code",
        ]
    )


def test_failure_details_are_preserved():
    error = IssueInvestigationError(
        (
            "Unsupported repair."
        ),
        stop_reason=(
            "unsupported_repair"
        ),
        usage={
            "input_tokens": 100,
            "output_tokens": 20,
            "tool_turns": 2,
            "cost_usd": 0.001,
            "latency_sec": 1.5,
        },
        details=(
            "Requires creating "
            "a new source file."
        ),
    )

    result = (
        _record_generation_failure(
            {},
            error,
        )
    )

    assert (
        result["stop_reason"]
        == "unsupported_repair"
    )

    assert (
        result["details"]
        == (
            "Requires creating "
            "a new source file."
        )
    )


def test_unexpected_failure_is_classified():
    error = RuntimeError(
        "Something unexpected."
    )

    result = (
        _record_generation_failure(
            {},
            error,
        )
    )

    assert (
        result["status"]
        == "generation_failed"
    )

    assert (
        result["stop_reason"]
        == "unexpected_error"
    )

    assert (
        result["error_type"]
        == "RuntimeError"
    )
