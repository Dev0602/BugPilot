from types import SimpleNamespace

from backend.app import agent


class FakeToolBlock:
    def __init__(
        self,
        name,
        tool_input,
        block_id="tool-1",
    ):
        self.type = "tool_use"
        self.name = name
        self.input = tool_input
        self.id = block_id


class FakeResponse:
    def __init__(
        self,
        blocks,
        input_tokens=100,
        output_tokens=50,
    ):
        self.content = blocks
        self.usage = SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def create(self, **kwargs):
        response = self.responses[self.calls]
        self.calls += 1
        return response


class FakeAnthropicClient:
    def __init__(self, responses):
        self.messages = FakeMessages(
            responses
        )


def make_fix(
    diagnosis="wrong operator",
    file_path="calculator.py",
    function_name="add",
    fixed_code=None,
):
    if fixed_code is None:
        fixed_code = (
            "def add(a, b):\n"
            "    return a + b\n"
        )

    return {
        "diagnosis": diagnosis,
        "file_path": file_path,
        "function_name": function_name,
        "fixed_function_code": fixed_code,
        "usage": {
            "input_tokens": 10,
            "output_tokens": 10,
            "cost_usd": 0.001,
            "latency_sec": 0.1,
            "tool_turns": 1,
        },
    }


def test_diagnose_and_fix_recovers_from_incomplete_submit(
    monkeypatch,
):
    """
    An incomplete submit_fix call should be returned to
    the model as a tool error rather than crashing BugPilot.
    """

    incomplete = FakeResponse(
        [
            FakeToolBlock(
                "submit_fix",
                {
                    "diagnosis": (
                        "Addition uses subtraction."
                    ),
                    # file_path intentionally missing
                    "function_name": "add",
                    "fixed_function_code": (
                        "def add(a, b):\n"
                        "    return a + b\n"
                    ),
                },
                block_id="bad-submit",
            )
        ]
    )

    corrected = FakeResponse(
        [
            FakeToolBlock(
                "submit_fix",
                {
                    "diagnosis": (
                        "Addition uses subtraction."
                    ),
                    "file_path": "calculator.py",
                    "function_name": "add",
                    "fixed_function_code": (
                        "def add(a, b):\n"
                        "    return a + b\n"
                    ),
                },
                block_id="good-submit",
            )
        ]
    )

    fake_client = FakeAnthropicClient(
        [
            incomplete,
            corrected,
        ]
    )

    monkeypatch.setattr(
        agent,
        "get_anthropic_client",
        lambda: fake_client,
    )

    result = agent.diagnose_and_fix(
        test_output="assert -1 == 5",
        bug_dir="bugs/fake_bug",
        max_tool_turns=3,
    )

    assert result["file_path"] == (
        "calculator.py"
    )

    assert result["function_name"] == "add"

    assert (
        "return a + b"
        in result["fixed_function_code"]
    )

    assert result["usage"]["tool_turns"] == 2

    assert fake_client.messages.calls == 2


def test_failed_patch_is_rolled_back_before_retry(
    monkeypatch,
):
    """
    After a repair fails verification, the next attempt
    must start from the original broken source.
    """

    original_code = (
        "def add(a, b):\n"
        "    return a - b\n"
    )

    state = {
        "code": original_code,
    }

    test_runs = {
        "count": 0,
    }

    diagnosis_calls = {
        "count": 0,
    }

    def fake_run_tests(bug_dir):
        test_runs["count"] += 1

        if test_runs["count"] == 1:
            return (
                False,
                "initial failure",
                100,
            )

        if test_runs["count"] == 2:
            return (
                False,
                "first repair still fails",
                100,
            )

        return (
            True,
            "all tests passed",
            100,
        )

    def fake_diagnose_and_fix(
        test_output,
        bug_dir,
        attempt_history=None,
        max_tool_turns=10,
    ):
        diagnosis_calls["count"] += 1

        if diagnosis_calls["count"] == 2:
            assert state["code"] == (
                original_code
            )

        if diagnosis_calls["count"] == 1:
            return make_fix(
                diagnosis="first repair",
                fixed_code=(
                    "def add(a, b):\n"
                    "    return a * b\n"
                ),
            )

        return make_fix(
            diagnosis="second repair",
            fixed_code=(
                "def add(a, b):\n"
                "    return a + b\n"
            ),
        )

    def fake_read_file(
        filepath,
        bug_dir,
    ):
        return state["code"]

    def fake_write_file(
        filepath,
        contents,
        bug_dir,
    ):
        state["code"] = contents

    def fake_apply_patch(
        full_code,
        function_name,
        new_function_code,
    ):
        return new_function_code

    monkeypatch.setattr(
        agent,
        "run_tests",
        fake_run_tests,
    )

    monkeypatch.setattr(
        agent,
        "diagnose_and_fix",
        fake_diagnose_and_fix,
    )

    monkeypatch.setattr(
        agent,
        "read_file",
        fake_read_file,
    )

    monkeypatch.setattr(
        agent,
        "write_file",
        fake_write_file,
    )

    monkeypatch.setattr(
        agent,
        "apply_function_patch",
        fake_apply_patch,
    )

    monkeypatch.setattr(
        agent.time,
        "sleep",
        lambda *_: None,
    )

    result = agent.solve_bug(
        "bugs/fake_bug",
        max_attempts=3,
    )

    assert result["success"] is True
    assert result["attempts"] == 2
    assert result["stop_reason"] == (
        "tests_passed"
    )

    assert (
        "return a + b"
        in state["code"]
    )

    assert test_runs["count"] == 3


def test_repeated_failed_repair_stops_early(
    monkeypatch,
):
    """
    If Claude proposes the exact same repair again after
    it already failed, BugPilot should stop early.
    """

    original_code = (
        "def add(a, b):\n"
        "    return a - b\n"
    )

    state = {
        "code": original_code,
    }

    test_runs = {
        "count": 0,
    }

    diagnosis_calls = {
        "count": 0,
    }

    repeated_fix = make_fix(
        diagnosis=(
            "replace subtraction with multiplication"
        ),
        fixed_code=(
            "def add(a, b):\n"
            "    return a * b\n"
        ),
    )

    def fake_run_tests(bug_dir):
        test_runs["count"] += 1

        return (
            False,
            "tests still failing",
            100,
        )

    def fake_diagnose_and_fix(
        test_output,
        bug_dir,
        attempt_history=None,
        max_tool_turns=10,
    ):
        diagnosis_calls["count"] += 1

        return {
            **repeated_fix,
            "usage": {
                **repeated_fix["usage"],
            },
        }

    def fake_read_file(
        filepath,
        bug_dir,
    ):
        return state["code"]

    def fake_write_file(
        filepath,
        contents,
        bug_dir,
    ):
        state["code"] = contents

    monkeypatch.setattr(
        agent,
        "run_tests",
        fake_run_tests,
    )

    monkeypatch.setattr(
        agent,
        "diagnose_and_fix",
        fake_diagnose_and_fix,
    )

    monkeypatch.setattr(
        agent,
        "read_file",
        fake_read_file,
    )

    monkeypatch.setattr(
        agent,
        "write_file",
        fake_write_file,
    )

    monkeypatch.setattr(
        agent,
        "apply_function_patch",
        lambda full_code,
        function_name,
        new_function_code: (
            new_function_code
        ),
    )

    monkeypatch.setattr(
        agent.time,
        "sleep",
        lambda *_: None,
    )

    result = agent.solve_bug(
        "bugs/fake_bug",
        max_attempts=3,
    )

    assert result["success"] is False

    assert result["attempts"] == 2

    assert result["stop_reason"] == (
        "repeated_failed_repair"
    )

    # Initial test + first repair verification.
    # The repeated second repair must NOT be applied/tested.
    assert test_runs["count"] == 2

    assert diagnosis_calls["count"] == 2

    # First failed repair should have been rolled back.
    assert state["code"] == original_code