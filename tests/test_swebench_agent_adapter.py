from pathlib import Path
from types import SimpleNamespace

import pytest

from evaluation.swebench.current.agent_adapter import (
    apply_issue_fix,
    diagnose_issue,
    solve_issue,
    validate_issue_target_file,
)


class FakeMessages:
    def __init__(
        self,
        responses,
    ):
        self.responses = list(
            responses
        )

        self.calls = []

    def create(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        if not self.responses:
            raise AssertionError(
                "Fake client received "
                "too many API calls."
            )

        return self.responses.pop(
            0
        )


class FakeClient:
    def __init__(
        self,
        responses,
    ):
        self.messages = (
            FakeMessages(
                responses
            )
        )


def tool_block(
    name,
    tool_input,
    tool_id,
):
    return SimpleNamespace(
        type="tool_use",
        name=name,
        input=tool_input,
        id=tool_id,
    )


def response(
    blocks,
    *,
    input_tokens=100,
    output_tokens=25,
):
    return SimpleNamespace(
        content=blocks,
        usage=SimpleNamespace(
            input_tokens=(
                input_tokens
            ),
            output_tokens=(
                output_tokens
            ),
        ),
    )


@pytest.fixture
def repository(
    tmp_path,
):
    (
        tmp_path
        / "calculator.py"
    ).write_text(
        "def add(a, b):\n"
        "    return a - b\n",
        encoding="utf-8",
    )

    (
        tmp_path
        / "test_calculator.py"
    ).write_text(
        "from calculator import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )

    return tmp_path


def valid_submit_fix():
    return {
        "diagnosis": (
            "add subtracts instead "
            "of adding."
        ),
        "file_path": (
            "calculator.py"
        ),
        "function_name": "add",
        "fixed_function_code": (
            "def add(a, b):\n"
            "    return a + b"
        ),
    }


def test_diagnose_issue_explores_repository(
    repository,
):
    client = FakeClient(
        [
            response(
                [
                    tool_block(
                        "read_file",
                        {
                            "filepath": (
                                "calculator.py"
                            ),
                        },
                        "tool-1",
                    ),
                ]
            ),
            response(
                [
                    tool_block(
                        "submit_fix",
                        valid_submit_fix(),
                        "tool-2",
                    ),
                ]
            ),
        ]
    )

    result = diagnose_issue(
        (
            "Adding two numbers "
            "returns the wrong value."
        ),
        repository,
        client=client,
    )

    assert (
        result["file_path"]
        == "calculator.py"
    )

    assert (
        result["function_name"]
        == "add"
    )

    assert (
        result["usage"][
            "input_tokens"
        ]
        == 200
    )

    first_prompt = (
        client.messages.calls[
            0
        ]["messages"][0][
            "content"
        ]
    )

    assert (
        "Adding two numbers "
        "returns the wrong value."
        in first_prompt
    )

    assert (
        "gold patch"
        in first_prompt.lower()
    )

    second_messages = (
        client.messages.calls[
            1
        ]["messages"]
    )

    assert any(
        (
            isinstance(
                message.get(
                    "content"
                ),
                list,
            )
            and any(
                (
                    isinstance(
                        block,
                        dict,
                    )
                    and block.get(
                        "type"
                    )
                    == "tool_result"
                    and (
                        "return a - b"
                        in block.get(
                            "content",
                            "",
                        )
                    )
                )
                for block
                in message[
                    "content"
                ]
            )
        )
        for message
        in second_messages
        if isinstance(
            message,
            dict,
        )
    )


def test_solve_issue_applies_patch(
    repository,
    monkeypatch,
):
    from evaluation.swebench.current import agent_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "verify_issue_patch",
        lambda *args, **kwargs: {
            "passed": True,
            "reason": "local_safety_checks_passed",
            "feedback": "Test verifier passed.",
            "changed_files": ["calculator.py"],
            "added_lines": 1,
            "deleted_lines": 1,
            "changed_lines": 2,
        },
    )

    client = FakeClient(
        [
            response(
                [
                    tool_block(
                        "submit_fix",
                        valid_submit_fix(),
                        "tool-1",
                    ),
                ]
            ),
        ]
    )

    result = solve_issue(
        repository,
        (
            "Adding two numbers "
            "returns the wrong value."
        ),
        client=client,
    )

    assert (
        result["applied"]
        is True
    )

    assert (
        (
            repository
            / "calculator.py"
        ).read_text(
            encoding="utf-8"
        )
        == (
            "def add(a, b):\n"
            "    return a + b\n"
        )
    )


def test_test_file_target_is_rejected(
    repository,
):
    with pytest.raises(
        ValueError,
        match=(
            "cannot modify "
            "test files"
        ),
    ):
        validate_issue_target_file(
            repository,
            "test_calculator.py",
        )


def test_malformed_submit_fix_can_recover(
    repository,
):
    client = FakeClient(
        [
            response(
                [
                    tool_block(
                        "submit_fix",
                        {
                            "diagnosis": (
                                "operator bug"
                            ),
                        },
                        "tool-1",
                    ),
                ]
            ),
            response(
                [
                    tool_block(
                        "submit_fix",
                        valid_submit_fix(),
                        "tool-2",
                    ),
                ]
            ),
        ]
    )

    result = diagnose_issue(
        "Addition is incorrect.",
        repository,
        client=client,
    )

    assert (
        result["file_path"]
        == "calculator.py"
    )

    assert len(
        client.messages.calls
    ) == 2

    second_messages = (
        client.messages.calls[
            1
        ]["messages"]
    )

    assert any(
        (
            isinstance(
                message.get(
                    "content"
                ),
                list,
            )
            and any(
                isinstance(
                        block,
                        dict,
                    )
                    and block.get(
                        "is_error"
                    )
                    is True
                for block
                in message[
                    "content"
                ]
            )
        )
        for message
        in second_messages
        if isinstance(
            message,
            dict,
        )
    )


def test_no_tool_call_is_rejected(
    repository,
):
    client = FakeClient(
        [
            response(
                []
            ),
        ]
    )

    with pytest.raises(
        ValueError,
        match=(
            "did not return "
            "a tool call"
        ),
    ):
        diagnose_issue(
            "Some issue.",
            repository,
            client=client,
        )

def test_patch_application_error_preserves_telemetry(
    tmp_path,
    monkeypatch,
):
    import pytest
    from evaluation.swebench.current import agent_adapter as adapter

    diagnosis = {
        "diagnosis": "Example diagnosis",
        "file_path": "example.py",
        "function_name": "MissingTarget",
        "fixed_function_code": (
            "def MissingTarget():\n"
            "    return 1\n"
        ),
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50,
            "cost_usd": 0.0123,
            "latency_sec": 2.5,
            "tool_turns": 4,
        },
        "tool_trace": [
            {
                "tool": "search_code",
                "input": {
                    "query": "MissingTarget",
                },
            }
        ],
    }

    monkeypatch.setattr(
        adapter,
        "diagnose_issue",
        lambda *args, **kwargs: diagnosis,
    )

    def fail_apply(*args, **kwargs):
        raise ValueError(
            "Could not find function 'MissingTarget'."
        )

    monkeypatch.setattr(
        adapter,
        "apply_issue_fix",
        fail_apply,
    )

    with pytest.raises(
        adapter.IssueInvestigationError
    ) as captured:
        adapter.solve_issue(
            tmp_path,
            "Public issue description",
            max_repair_attempts=1,
            client=object(),
        )

    error = captured.value

    assert (
        error.stop_reason
        == "patch_application_error"
    )

    assert (
        error.usage["cost_usd"]
        == 0.0123
    )

    assert (
        error.usage["tool_turns"]
        == 4
    )

    assert (
        error.tool_trace
        == [
            {
                "repair_attempt": 1,
                **diagnosis["tool_trace"][0],
            }
        ]
    )

    assert (
        error.details["stage"]
        == "apply_issue_fix"
    )

    assert (
        error.details["error_type"]
        == "ValueError"
    )

    assert (
        error.details["function_name"]
        == "MissingTarget"
    )


def test_solve_issue_retries_after_local_verification_failure(
    tmp_path,
    monkeypatch,
):
    from evaluation.swebench.current import agent_adapter as adapter

    diagnoses = [
        {
            "diagnosis": "First repair",
            "file_path": "example.py",
            "function_name": "target",
            "fixed_function_code": (
                "def target():\n"
                "    return 1\n"
            ),
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "tool_turns": 2,
                "cost_usd": 0.01,
                "latency_sec": 1.0,
            },
            "tool_trace": [
                {
                    "tool": "search_code",
                }
            ],
        },
        {
            "diagnosis": "Second repair",
            "file_path": "example.py",
            "function_name": "target",
            "fixed_function_code": (
                "def target():\n"
                "    return 2\n"
            ),
            "usage": {
                "input_tokens": 20,
                "output_tokens": 10,
                "tool_turns": 3,
                "cost_usd": 0.02,
                "latency_sec": 2.0,
            },
            "tool_trace": [
                {
                    "tool": "read_file",
                }
            ],
        },
    ]

    prompts = []

    def fake_diagnose(
        problem_statement,
        repository_path,
        **kwargs,
    ):
        prompts.append(
            problem_statement
        )
        return diagnoses[
            len(prompts) - 1
        ]

    monkeypatch.setattr(
        adapter,
        "diagnose_issue",
        fake_diagnose,
    )

    monkeypatch.setattr(
        adapter,
        "apply_issue_fix",
        lambda repository_path, result: {
            "applied": True,
            "diagnosis": result["diagnosis"],
            "file_path": result["file_path"],
            "function_name": result["function_name"],
            "usage": result["usage"],
            "tool_trace": result["tool_trace"],
        },
    )

    verifications = iter(
        [
            {
                "passed": False,
                "reason": "patch_too_broad",
                "feedback": (
                    "Previous repair changed too many lines."
                ),
            },
            {
                "passed": True,
                "reason": "local_safety_checks_passed",
                "feedback": (
                    "Local no-oracle safety checks passed."
                ),
            },
        ]
    )

    monkeypatch.setattr(
        adapter,
        "verify_issue_patch",
        lambda *args, **kwargs: next(
            verifications
        ),
    )

    rollbacks = []

    monkeypatch.setattr(
        adapter,
        "_rollback_issue_patch",
        lambda repository_path, relative_path: (
            rollbacks.append(
                relative_path
            )
        ),
    )

    result = adapter.solve_issue(
        tmp_path,
        "Public issue description",
        max_repair_attempts=2,
        client=object(),
    )

    assert result["repair_attempts"] == 2
    assert result["verification"]["passed"] is True

    assert result["usage"]["input_tokens"] == 30
    assert result["usage"]["output_tokens"] == 15
    assert result["usage"]["tool_turns"] == 5
    assert result["usage"]["cost_usd"] == 0.03
    assert result["usage"]["latency_sec"] == 3.0

    assert rollbacks == [
        "example.py"
    ]

    assert len(prompts) == 2

    assert (
        "Previous repair changed too many lines."
        in prompts[1]
    )

    assert (
        "Do not repeat the same rejected implementation."
        in prompts[1]
    )
