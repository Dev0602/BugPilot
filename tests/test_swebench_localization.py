from pathlib import Path
from types import SimpleNamespace

import pytest

from evaluation.swebench.current.agent_adapter import (
    IssueInvestigationError,
    build_localization_context,
    diagnose_issue,
    extract_issue_search_terms,
)
from backend.app.tools import (
    rank_repository_files,
    search_code,
)


def make_repo(
    tmp_path,
):
    repo = (
        tmp_path
        / "repo"
    )

    repo.mkdir()

    package = (
        repo
        / "package"
    )
    package.mkdir()

    tests = (
        repo
        / "tests"
    )
    tests.mkdir()

    docs = (
        repo
        / "docs"
    )
    docs.mkdir()

    (
        package
        / "debug.py"
    ).write_text(
        "class SafeFilter:\n"
        "    def cleanse_setting"
        "(self, key, value):\n"
        "        return value\n",
        encoding="utf-8",
    )

    (
        tests
        / "test_debug.py"
    ).write_text(
        "def test_cleanse_setting():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    (
        docs
        / "debug.md"
    ).write_text(
        "The cleanse_setting "
        "function cleans settings.\n",
        encoding="utf-8",
    )

    return repo


def test_search_code_ranks_source_before_tests_and_docs(
    tmp_path,
):
    repo = make_repo(
        tmp_path
    )

    results = search_code(
        str(repo),
        "cleanse_setting",
    )

    assert results

    assert (
        results[0]["file"]
        == "package/debug.py"
    )


def test_rank_repository_files_prioritizes_source(
    tmp_path,
):
    repo = make_repo(
        tmp_path
    )

    ranked = (
        rank_repository_files(
            str(repo),
            [
                "SafeFilter",
                "cleanse_setting",
            ],
        )
    )

    assert ranked

    assert (
        ranked[0]["file"]
        == "package/debug.py"
    )


def test_extract_issue_terms_prioritizes_symbols():
    statement = """
SafeExceptionReporterFilter.get_safe_settings()
does not recursively call cleanse_setting() for
nested values.
"""

    terms = (
        extract_issue_search_terms(
            statement
        )
    )

    lowered = {
        term.lower()
        for term in terms
    }

    assert (
        "safeexceptionreporterfilter"
        in " ".join(
            lowered
        )
    )

    assert (
        "cleanse_setting"
        in lowered
    )


def test_localization_context_contains_ranked_source(
    tmp_path,
):
    repo = make_repo(
        tmp_path
    )

    context = (
        build_localization_context(
            (
                "SafeFilter."
                "cleanse_setting() "
                "does not cleanse "
                "nested values."
            ),
            repo,
        )
    )

    assert (
        "package/debug.py"
        in context
    )

    assert (
        "Ranked candidate files"
        in context
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


def tool_response(
    *,
    tool_id,
    name,
    tool_input,
    input_tokens=10,
    output_tokens=5,
):
    return SimpleNamespace(
        usage=SimpleNamespace(
            input_tokens=(
                input_tokens
            ),
            output_tokens=(
                output_tokens
            ),
        ),
        content=[
            SimpleNamespace(
                type="tool_use",
                id=tool_id,
                name=name,
                input=tool_input,
            )
        ],
    )


def text_response(
    text,
    *,
    input_tokens=10,
    output_tokens=5,
):
    return SimpleNamespace(
        usage=SimpleNamespace(
            input_tokens=(
                input_tokens
            ),
            output_tokens=(
                output_tokens
            ),
        ),
        content=[
            SimpleNamespace(
                type="text",
                text=text,
            )
        ],
    )


def test_turn_limit_preserves_usage_and_reason(
    tmp_path,
):
    repo = make_repo(
        tmp_path
    )

    client = FakeClient(
        [
            tool_response(
                tool_id="one",
                name="search_code",
                tool_input={
                    "keyword": (
                        "cleanse_setting"
                    )
                },
            ),
            tool_response(
                tool_id="two",
                name="search_code",
                tool_input={
                    "keyword": (
                        "SafeFilter"
                    )
                },
            ),
        ]
    )

    with pytest.raises(
        IssueInvestigationError
    ) as captured:
        diagnose_issue(
            (
                "SafeFilter."
                "cleanse_setting() "
                "is incorrect."
            ),
            repo,
            max_tool_turns=2,
            client=client,
        )

    error = (
        captured.value
    )

    assert (
        error.stop_reason
        == "turn_limit"
    )

    assert (
        error.usage[
            "input_tokens"
        ]
        == 20
    )

    assert (
        error.usage[
            "output_tokens"
        ]
        == 10
    )

    assert (
        error.usage[
            "tool_turns"
        ]
        == 2
    )

    assert (
        error.tool_trace
        == [
            "search_code",
            "search_code",
        ]
    )


def test_remaining_turn_budget_is_injected(
    tmp_path,
):
    repo = make_repo(
        tmp_path
    )

    client = FakeClient(
        [
            tool_response(
                tool_id="one",
                name="search_code",
                tool_input={
                    "keyword": (
                        "cleanse_setting"
                    )
                },
            ),
            text_response(
                (
                    "UNSUPPORTED_REPAIR: "
                    "requires adding "
                    "a new method"
                )
            ),
        ]
    )

    with pytest.raises(
        IssueInvestigationError
    ):
        diagnose_issue(
            (
                "SafeFilter."
                "cleanse_setting() "
                "is incorrect."
            ),
            repo,
            max_tool_turns=2,
            client=client,
        )

    second_call = (
        client.messages.calls[
            1
        ]
    )

    messages = (
        second_call[
            "messages"
        ]
    )

    budget_texts = []

    for message in messages:
        content = (
            message.get(
                "content"
            )
            if isinstance(
                message,
                dict,
            )
            else None
        )

        if not isinstance(
            content,
            list,
        ):
            continue

        for block in content:
            if (
                isinstance(
                    block,
                    dict,
                )
                and block.get(
                    "type"
                )
                == "text"
            ):
                budget_texts.append(
                    block.get(
                        "text",
                        "",
                    )
                )

    assert any(
        "1 turn remains"
        in text
        for text
        in budget_texts
    )


def test_unsupported_repair_has_specific_reason(
    tmp_path,
):
    repo = make_repo(
        tmp_path
    )

    client = FakeClient(
        [
            text_response(
                (
                    "UNSUPPORTED_REPAIR: "
                    "requires creating "
                    "a new source file"
                )
            )
        ]
    )

    with pytest.raises(
        IssueInvestigationError
    ) as captured:
        diagnose_issue(
            (
                "Feature requires "
                "a new implementation."
            ),
            repo,
            max_tool_turns=2,
            client=client,
        )

    assert (
        captured.value.stop_reason
        == "unsupported_repair"
    )

    assert (
        captured.value.usage[
            "tool_turns"
        ]
        == 1
    )
