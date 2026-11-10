import sqlite3

import pytest
from fastapi import HTTPException

from backend.app import api
from backend.app import db


@pytest.fixture
def temp_database(
    tmp_path,
    monkeypatch,
):
    """
    Give every test its own temporary SQLite database.

    Nothing here touches the real bugpilot.db file.
    """

    database_path = str(
        tmp_path / "test_bugpilot.db"
    )

    monkeypatch.setattr(
        db,
        "DB_PATH",
        database_path,
    )

    monkeypatch.setattr(
        api,
        "DB_PATH",
        database_path,
    )

    db.init_db()

    return database_path


def create_test_run(
    run_id="test_run",
):
    db.start_run(
        run_id=run_id,
        model="claude-haiku-4-5",
        benchmark="pytest",
        metadata={
            "purpose": (
                "database api test"
            ),
        },
    )


def create_test_result(
    run_id,
    success=True,
):
    result = {
        "bug": (
            "bugs/"
            "bug_01_calculator"
        ),
        "success": success,
        "attempts": 1,
        "cost_usd": 0.00841,
        "latency_sec": 4.7,
        "diagnosis": (
            "The add function "
            "used subtraction."
        ),
        "file_path": (
            "calculator.py"
        ),
        "function_name": "add",
        "coverage": 100,
        "stop_reason": (
            "tests_passed"
            if success
            else
            "max_attempts_reached"
        ),
    }

    db.save_result(
        result,
        run_id,
    )

    return result


def test_database_schema_created(
    temp_database,
):
    conn = sqlite3.connect(
        temp_database
    )

    try:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()

    finally:
        conn.close()

    tables = {
        row[0]
        for row in rows
    }

    expected = {
        "runs",
        "run_results",
        "results",
        "attempts",
        "tool_calls",
        "patches",
        "test_results",
    }

    assert expected.issubset(
        tables
    )


def test_run_history_does_not_overwrite(
    temp_database,
):
    """
    The old results table keeps the latest snapshot,
    while run_results preserves history.
    """

    create_test_run(
        "run_one"
    )

    create_test_result(
        "run_one",
        success=True,
    )

    db.finish_run(
        "run_one",
        status="completed",
    )

    create_test_run(
        "run_two"
    )

    create_test_result(
        "run_two",
        success=False,
    )

    db.finish_run(
        "run_two",
        status="completed",
    )

    conn = sqlite3.connect(
        temp_database
    )

    try:
        historical_count = (
            conn.execute(
                """
                SELECT COUNT(*)
                FROM run_results
                WHERE bug = ?
                """,
                (
                    "bugs/"
                    "bug_01_calculator",
                ),
            )
            .fetchone()[0]
        )

        latest_count = (
            conn.execute(
                """
                SELECT COUNT(*)
                FROM results
                WHERE bug = ?
                """,
                (
                    "bugs/"
                    "bug_01_calculator",
                ),
            )
            .fetchone()[0]
        )

        latest_success = (
            conn.execute(
                """
                SELECT success
                FROM results
                WHERE bug = ?
                """,
                (
                    "bugs/"
                    "bug_01_calculator",
                ),
            )
            .fetchone()[0]
        )

    finally:
        conn.close()

    assert historical_count == 2
    assert latest_count == 1
    assert latest_success == 0


def test_attempt_trace_is_persisted(
    temp_database,
):
    run_id = "trace_run"

    create_test_run(
        run_id
    )

    attempt_id = db.save_attempt(
        run_id,
        "bugs/bug_01_calculator",
        1,
        status="started",
    )

    assert attempt_id is not None

    db.save_tool_call(
        attempt_id=attempt_id,
        sequence_number=1,
        tool_name=(
            "list_directory"
        ),
        tool_input={
            "path": ".",
        },
        output_text=(
            "calculator.py\n"
            "test_calculator.py"
        ),
        is_error=False,
        duration_ms=1.25,
    )

    db.save_tool_call(
        attempt_id=attempt_id,
        sequence_number=2,
        tool_name="read_file",
        tool_input={
            "filepath": (
                "calculator.py"
            ),
        },
        output_text=(
            "def add(a, b):\n"
            "    return a - b"
        ),
        is_error=False,
        duration_ms=0.75,
    )

    db.save_patch(
        attempt_id,
        file_path=(
            "calculator.py"
        ),
        function_name="add",
        original_code=(
            "def add(a, b):\n"
            "    return a - b\n"
        ),
        patched_code=(
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        applied=True,
    )

    db.save_test_result(
        attempt_id,
        phase="initial",
        passed=False,
        coverage=100,
        logs="1 failed",
        duration_sec=0.1,
    )

    db.save_test_result(
        attempt_id,
        phase="verification",
        passed=True,
        coverage=100,
        logs="1 passed",
        duration_sec=0.1,
    )

    conn = sqlite3.connect(
        temp_database
    )

    try:
        tool_calls = (
            conn.execute(
                """
                SELECT
                    sequence_number,
                    tool_name
                FROM tool_calls
                WHERE attempt_id = ?
                ORDER BY
                    sequence_number
                """,
                (
                    attempt_id,
                ),
            )
            .fetchall()
        )

        patch_count = (
            conn.execute(
                """
                SELECT COUNT(*)
                FROM patches
                WHERE attempt_id = ?
                """,
                (
                    attempt_id,
                ),
            )
            .fetchone()[0]
        )

        test_count = (
            conn.execute(
                """
                SELECT COUNT(*)
                FROM test_results
                WHERE attempt_id = ?
                """,
                (
                    attempt_id,
                ),
            )
            .fetchone()[0]
        )

    finally:
        conn.close()

    assert tool_calls == [
        (
            1,
            "list_directory",
        ),
        (
            2,
            "read_file",
        ),
    ]

    assert patch_count == 1
    assert test_count == 2


def test_replay_api_returns_real_trace(
    temp_database,
):
    run_id = "replay_run"

    create_test_run(
        run_id
    )

    attempt_id = db.save_attempt(
        run_id,
        "bugs/bug_01_calculator",
        1,
        status="passed",
        diagnosis=(
            "Addition used subtraction."
        ),
        file_path=(
            "calculator.py"
        ),
        function_name="add",
        input_tokens=100,
        output_tokens=25,
        tool_turns=2,
        cost_usd=0.001,
        latency_sec=1.5,
        stop_reason=(
            "tests_passed"
        ),
    )

    db.save_tool_call(
        attempt_id=attempt_id,
        sequence_number=1,
        tool_name=(
            "list_directory"
        ),
        tool_input={
            "path": ".",
        },
        output_text=(
            "calculator.py"
        ),
        is_error=False,
        duration_ms=1.0,
    )

    db.save_tool_call(
        attempt_id=attempt_id,
        sequence_number=2,
        tool_name=(
            "submit_fix"
        ),
        tool_input={
            "diagnosis": (
                "Wrong operator"
            ),
            "file_path": (
                "calculator.py"
            ),
            "function_name": "add",
            "fixed_function_code": (
                "def add(a, b):\n"
                "    return a + b"
            ),
        },
        output_text=(
            "Fix accepted for "
            "patch application."
        ),
        is_error=False,
    )

    db.save_patch(
        attempt_id,
        file_path=(
            "calculator.py"
        ),
        function_name="add",
        original_code=(
            "def add(a, b):\n"
            "    return a - b\n"
        ),
        patched_code=(
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        applied=True,
    )

    db.save_test_result(
        attempt_id,
        phase="verification",
        passed=True,
        coverage=100,
        logs="1 passed",
        duration_sec=0.2,
    )

    replay = (
        api.get_attempt_replay(
            attempt_id
        )
    )

    assert (
        replay["attempt"]["id"]
        == attempt_id
    )

    assert len(
        replay["tool_calls"]
    ) == 2

    assert (
        replay[
            "tool_calls"
        ][0][
            "sequence_number"
        ]
        == 1
    )

    assert (
        replay[
            "tool_calls"
        ][0]["tool_name"]
        == "list_directory"
    )

    assert (
        replay[
            "tool_calls"
        ][1]["tool_name"]
        == "submit_fix"
    )

    assert len(
        replay["patches"]
    ) == 1

    assert len(
        replay["tests"]
    ) == 1

    assert (
        replay[
            "tests"
        ][0]["passed"]
        is True
    )


def test_run_api_and_missing_attempt(
    temp_database,
):
    run_id = "api_run"

    create_test_run(
        run_id
    )

    create_test_result(
        run_id,
        success=True,
    )

    db.finish_run(
        run_id,
        status="completed",
    )

    runs = api.get_runs(
        limit=50
    )

    assert len(runs) == 1

    assert (
        runs[0]["run_id"]
        == run_id
    )

    assert (
        runs[0]["status"]
        == "completed"
    )

    assert (
        runs[0][
            "result_count"
        ]
        == 1
    )

    assert (
        runs[0][
            "resolved_count"
        ]
        == 1
    )

    results = (
        api.get_run_results(
            run_id
        )
    )

    assert len(results) == 1

    assert (
        results[0]["success"]
        is True
    )

    with pytest.raises(
        HTTPException
    ) as exc_info:
        api.get_attempt_replay(
            999999
        )

    assert (
        exc_info.value.status_code
        == 404
    )