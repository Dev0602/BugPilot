import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any


from .config import DB_PATH


def _utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def _json_dumps(value):
    if value is None:
        return None

    return json.dumps(
        value,
        ensure_ascii=False,
        default=str,
    )


def _connect():
    """
    Open a configured SQLite connection.

    WAL mode improves concurrent dashboard/API reads while
    BugPilot writes evaluation data.
    """

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA foreign_keys = ON"
    )

    conn.execute(
        "PRAGMA journal_mode = WAL"
    )

    conn.execute(
        "PRAGMA synchronous = NORMAL"
    )

    return conn


def _table_columns(
    conn,
    table_name,
):
    rows = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {
        row["name"]
        for row in rows
    }


def _ensure_column(
    conn,
    table_name,
    column_name,
    column_definition,
):
    """
    Add a column to an existing table when upgrading an
    older BugPilot database.
    """

    columns = _table_columns(
        conn,
        table_name,
    )

    if column_name not in columns:
        conn.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN {column_name}
            {column_definition}
            """
        )


def init_db():
    """
    Initialize BugPilot's SQLite schema.

    The original `results` table is preserved as a
    latest-result snapshot for backwards compatibility.

    Historical information is stored separately in:
      - runs
      - run_results
      - attempts
      - tool_calls
      - patches
      - test_results
    """

    conn = _connect()

    try:
        # -------------------------------------------------
        # Latest snapshot table.
        #
        # Kept for compatibility with the existing dashboard
        # and API while richer historical tables are added.
        # -------------------------------------------------
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
                bug TEXT PRIMARY KEY,
                success INTEGER NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0,
                latency_sec REAL NOT NULL DEFAULT 0,
                coverage INTEGER,
                diagnosis TEXT,
                file_path TEXT,
                function_name TEXT,
                stop_reason TEXT,
                run_timestamp TEXT
            )
            """
        )

        # Migrate an older existing results table safely.
        _ensure_column(
            conn,
            "results",
            "file_path",
            "TEXT",
        )

        _ensure_column(
            conn,
            "results",
            "stop_reason",
            "TEXT",
        )

        # -------------------------------------------------
        # One row for every BugPilot execution / benchmark.
        # -------------------------------------------------
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                model TEXT,
                benchmark TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                total_cases INTEGER NOT NULL DEFAULT 0,
                resolved INTEGER NOT NULL DEFAULT 0,
                total_cost_usd REAL NOT NULL DEFAULT 0,
                total_latency_sec REAL NOT NULL DEFAULT 0,
                metadata_json TEXT
            )
            """
        )

        # -------------------------------------------------
        # Final result for each bug inside a specific run.
        # -------------------------------------------------
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                bug TEXT NOT NULL,
                success INTEGER NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0,
                latency_sec REAL NOT NULL DEFAULT 0,
                coverage INTEGER,
                diagnosis TEXT,
                file_path TEXT,
                function_name TEXT,
                stop_reason TEXT,
                raw_json TEXT,
                created_at TEXT NOT NULL,

                UNIQUE(run_id, bug),

                FOREIGN KEY(run_id)
                    REFERENCES runs(run_id)
                    ON DELETE CASCADE
            )
            """
        )

        # -------------------------------------------------
        # Every individual repair attempt.
        # -------------------------------------------------
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                bug TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,

                status TEXT NOT NULL DEFAULT 'started',

                diagnosis TEXT,
                file_path TEXT,
                function_name TEXT,

                input_tokens INTEGER,
                output_tokens INTEGER,
                tool_turns INTEGER,

                cost_usd REAL NOT NULL DEFAULT 0,
                latency_sec REAL NOT NULL DEFAULT 0,

                verification_output TEXT,
                stop_reason TEXT,

                created_at TEXT NOT NULL,

                UNIQUE(
                    run_id,
                    bug,
                    attempt_number
                ),

                FOREIGN KEY(run_id)
                    REFERENCES runs(run_id)
                    ON DELETE CASCADE
            )
            """
        )

        # -------------------------------------------------
        # Claude repository investigation tool calls.
        # -------------------------------------------------
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id INTEGER NOT NULL,
                sequence_number INTEGER NOT NULL,

                tool_name TEXT NOT NULL,
                input_json TEXT,
                output_text TEXT,

                is_error INTEGER NOT NULL DEFAULT 0,
                duration_ms REAL,

                created_at TEXT NOT NULL,

                FOREIGN KEY(attempt_id)
                    REFERENCES attempts(id)
                    ON DELETE CASCADE
            )
            """
        )

        # -------------------------------------------------
        # Generated source patches.
        # -------------------------------------------------
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS patches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id INTEGER NOT NULL,

                file_path TEXT NOT NULL,
                function_name TEXT,

                original_code TEXT,
                patched_code TEXT,
                diff_text TEXT,

                applied INTEGER NOT NULL DEFAULT 0,

                created_at TEXT NOT NULL,

                FOREIGN KEY(attempt_id)
                    REFERENCES attempts(id)
                    ON DELETE CASCADE
            )
            """
        )

        # -------------------------------------------------
        # Test executions associated with an attempt.
        # -------------------------------------------------
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id INTEGER,

                phase TEXT NOT NULL,

                passed INTEGER NOT NULL DEFAULT 0,
                coverage INTEGER,
                status_code INTEGER,

                logs TEXT,
                duration_sec REAL,

                created_at TEXT NOT NULL,

                FOREIGN KEY(attempt_id)
                    REFERENCES attempts(id)
                    ON DELETE CASCADE
            )
            """
        )

        # Helpful indexes for API/dashboard queries.
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_run_results_run_id
            ON run_results(run_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_attempts_run_bug
            ON attempts(run_id, bug)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_tool_calls_attempt
            ON tool_calls(attempt_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_patches_attempt
            ON patches(attempt_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_test_results_attempt
            ON test_results(attempt_id)
            """
        )

        conn.commit()

    finally:
        conn.close()


def start_run(
    run_id,
    model=None,
    benchmark=None,
    metadata=None,
):
    """
    Create a new run if it does not already exist.
    """

    init_db()

    conn = _connect()

    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO runs (
                run_id,
                started_at,
                model,
                benchmark,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                run_id,
                _utc_now(),
                model,
                benchmark,
                _json_dumps(metadata),
            ),
        )

        conn.commit()

    finally:
        conn.close()


def _refresh_run_summary(
    conn,
    run_id,
):
    """
    Recompute aggregate metrics from run_results.
    """

    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_cases,
            COALESCE(
                SUM(success),
                0
            ) AS resolved,
            COALESCE(
                SUM(cost_usd),
                0
            ) AS total_cost_usd,
            COALESCE(
                SUM(latency_sec),
                0
            ) AS total_latency_sec
        FROM run_results
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()

    conn.execute(
        """
        UPDATE runs
        SET
            total_cases = ?,
            resolved = ?,
            total_cost_usd = ?,
            total_latency_sec = ?
        WHERE run_id = ?
        """,
        (
            row["total_cases"],
            row["resolved"],
            row["total_cost_usd"],
            row["total_latency_sec"],
            run_id,
        ),
    )


def finish_run(
    run_id,
    status="completed",
):
    """
    Mark a run as finished and finalize its aggregates.
    """

    conn = _connect()

    try:
        _refresh_run_summary(
            conn,
            run_id,
        )

        conn.execute(
            """
            UPDATE runs
            SET
                status = ?,
                finished_at = ?
            WHERE run_id = ?
            """,
            (
                status,
                _utc_now(),
                run_id,
            ),
        )

        conn.commit()

    finally:
        conn.close()


def save_result(
    result,
    run_timestamp,
):
    """
    Save a final bug result.

    Two copies are intentionally maintained:

    1. `results`
       Latest snapshot for compatibility with the
       current dashboard/API.

    2. `run_results`
       Permanent historical result associated with
       the specific run.
    """

    start_run(
        run_timestamp
    )

    conn = _connect()

    try:
        bug = result["bug"]

        success = int(
            bool(
                result.get(
                    "success",
                    False,
                )
            )
        )

        attempts = int(
            result.get(
                "attempts",
                0,
            )
            or 0
        )

        cost_usd = float(
            result.get(
                "cost_usd",
                0,
            )
            or 0
        )

        latency_sec = float(
            result.get(
                "latency_sec",
                0,
            )
            or 0
        )

        coverage = result.get(
            "coverage"
        )

        diagnosis = result.get(
            "diagnosis"
        )

        file_path = result.get(
            "file_path"
        )

        function_name = result.get(
            "function_name"
        )

        stop_reason = result.get(
            "stop_reason"
        )

        # Latest-result compatibility snapshot.
        conn.execute(
            """
            INSERT INTO results (
                bug,
                success,
                attempts,
                cost_usd,
                latency_sec,
                coverage,
                diagnosis,
                file_path,
                function_name,
                stop_reason,
                run_timestamp
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )

            ON CONFLICT(bug)
            DO UPDATE SET
                success = excluded.success,
                attempts = excluded.attempts,
                cost_usd = excluded.cost_usd,
                latency_sec = excluded.latency_sec,
                coverage = excluded.coverage,
                diagnosis = excluded.diagnosis,
                file_path = excluded.file_path,
                function_name = excluded.function_name,
                stop_reason = excluded.stop_reason,
                run_timestamp = excluded.run_timestamp
            """,
            (
                bug,
                success,
                attempts,
                cost_usd,
                latency_sec,
                coverage,
                diagnosis,
                file_path,
                function_name,
                stop_reason,
                run_timestamp,
            ),
        )

        # Permanent per-run history.
        conn.execute(
            """
            INSERT INTO run_results (
                run_id,
                bug,
                success,
                attempts,
                cost_usd,
                latency_sec,
                coverage,
                diagnosis,
                file_path,
                function_name,
                stop_reason,
                raw_json,
                created_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?
            )

            ON CONFLICT(run_id, bug)
            DO UPDATE SET
                success = excluded.success,
                attempts = excluded.attempts,
                cost_usd = excluded.cost_usd,
                latency_sec = excluded.latency_sec,
                coverage = excluded.coverage,
                diagnosis = excluded.diagnosis,
                file_path = excluded.file_path,
                function_name = excluded.function_name,
                stop_reason = excluded.stop_reason,
                raw_json = excluded.raw_json
            """,
            (
                run_timestamp,
                bug,
                success,
                attempts,
                cost_usd,
                latency_sec,
                coverage,
                diagnosis,
                file_path,
                function_name,
                stop_reason,
                _json_dumps(result),
                _utc_now(),
            ),
        )

        _refresh_run_summary(
            conn,
            run_timestamp,
        )

        conn.commit()

    finally:
        conn.close()


def save_attempt(
    run_id,
    bug,
    attempt_number,
    status="started",
    diagnosis=None,
    file_path=None,
    function_name=None,
    input_tokens=None,
    output_tokens=None,
    tool_turns=None,
    cost_usd=0,
    latency_sec=0,
    verification_output=None,
    stop_reason=None,
):
    """
    Insert or update one repair attempt.

    Returns the attempt database ID.
    """

    start_run(run_id)

    conn = _connect()

    try:
        conn.execute(
            """
            INSERT INTO attempts (
                run_id,
                bug,
                attempt_number,
                status,
                diagnosis,
                file_path,
                function_name,
                input_tokens,
                output_tokens,
                tool_turns,
                cost_usd,
                latency_sec,
                verification_output,
                stop_reason,
                created_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?
            )

            ON CONFLICT(
                run_id,
                bug,
                attempt_number
            )
            DO UPDATE SET
                status = excluded.status,
                diagnosis = excluded.diagnosis,
                file_path = excluded.file_path,
                function_name = excluded.function_name,
                input_tokens = excluded.input_tokens,
                output_tokens = excluded.output_tokens,
                tool_turns = excluded.tool_turns,
                cost_usd = excluded.cost_usd,
                latency_sec = excluded.latency_sec,
                verification_output =
                    excluded.verification_output,
                stop_reason = excluded.stop_reason
            """,
            (
                run_id,
                bug,
                attempt_number,
                status,
                diagnosis,
                file_path,
                function_name,
                input_tokens,
                output_tokens,
                tool_turns,
                cost_usd,
                latency_sec,
                verification_output,
                stop_reason,
                _utc_now(),
            ),
        )

        row = conn.execute(
            """
            SELECT id
            FROM attempts
            WHERE
                run_id = ?
                AND bug = ?
                AND attempt_number = ?
            """,
            (
                run_id,
                bug,
                attempt_number,
            ),
        ).fetchone()

        conn.commit()

        return row["id"]

    finally:
        conn.close()


def save_tool_call(
    attempt_id,
    sequence_number,
    tool_name,
    tool_input=None,
    output_text=None,
    is_error=False,
    duration_ms=None,
):
    """
    Persist one repository investigation tool call.
    """

    conn = _connect()

    try:
        cursor = conn.execute(
            """
            INSERT INTO tool_calls (
                attempt_id,
                sequence_number,
                tool_name,
                input_json,
                output_text,
                is_error,
                duration_ms,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt_id,
                sequence_number,
                tool_name,
                _json_dumps(
                    tool_input
                ),
                output_text,
                int(
                    bool(is_error)
                ),
                duration_ms,
                _utc_now(),
            ),
        )

        conn.commit()

        return cursor.lastrowid

    finally:
        conn.close()


def save_patch(
    attempt_id,
    file_path,
    function_name=None,
    original_code=None,
    patched_code=None,
    diff_text=None,
    applied=False,
):
    """
    Persist a generated source patch.
    """

    conn = _connect()

    try:
        cursor = conn.execute(
            """
            INSERT INTO patches (
                attempt_id,
                file_path,
                function_name,
                original_code,
                patched_code,
                diff_text,
                applied,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt_id,
                file_path,
                function_name,
                original_code,
                patched_code,
                diff_text,
                int(
                    bool(applied)
                ),
                _utc_now(),
            ),
        )

        conn.commit()

        return cursor.lastrowid

    finally:
        conn.close()


def save_test_result(
    attempt_id,
    phase,
    passed,
    coverage=None,
    status_code=None,
    logs=None,
    duration_sec=None,
):
    """
    Persist a test execution.

    Example phases:
        initial
        verification
        post_patch
    """

    conn = _connect()

    try:
        cursor = conn.execute(
            """
            INSERT INTO test_results (
                attempt_id,
                phase,
                passed,
                coverage,
                status_code,
                logs,
                duration_sec,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt_id,
                phase,
                int(
                    bool(passed)
                ),
                coverage,
                status_code,
                logs,
                duration_sec,
                _utc_now(),
            ),
        )

        conn.commit()

        return cursor.lastrowid

    finally:
        conn.close()


def get_all_results():
    """
    Return the latest result for every bug.

    Kept for compatibility with the current dashboard/API.
    """

    init_db()

    conn = _connect()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM results
            ORDER BY bug
            """
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        conn.close()


def get_runs(
    limit=50,
):
    """
    Return recent BugPilot runs.
    """

    init_db()

    conn = _connect()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM runs
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        conn.close()


def get_run(
    run_id,
):
    """
    Return one run or None.
    """

    init_db()

    conn = _connect()

    try:
        row = conn.execute(
            """
            SELECT *
            FROM runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()

        if row is None:
            return None

        return dict(row)

    finally:
        conn.close()


def get_run_results(
    run_id,
):
    """
    Return final bug results from one run.
    """

    conn = _connect()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM run_results
            WHERE run_id = ?
            ORDER BY bug
            """,
            (run_id,),
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        conn.close()


def get_attempts(
    run_id,
    bug=None,
):
    """
    Return repair attempts for a run.

    Optionally restrict to a specific bug.
    """

    conn = _connect()

    try:
        if bug is None:
            rows = conn.execute(
                """
                SELECT *
                FROM attempts
                WHERE run_id = ?
                ORDER BY
                    bug,
                    attempt_number
                """,
                (run_id,),
            ).fetchall()

        else:
            rows = conn.execute(
                """
                SELECT *
                FROM attempts
                WHERE
                    run_id = ?
                    AND bug = ?
                ORDER BY attempt_number
                """,
                (
                    run_id,
                    bug,
                ),
            ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        conn.close()


def get_tool_calls(
    attempt_id,
):
    conn = _connect()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM tool_calls
            WHERE attempt_id = ?
            ORDER BY sequence_number
            """,
            (attempt_id,),
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        conn.close()


def get_patches(
    attempt_id,
):
    conn = _connect()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM patches
            WHERE attempt_id = ?
            ORDER BY id
            """,
            (attempt_id,),
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        conn.close()


def get_test_results(
    attempt_id,
):
    conn = _connect()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM test_results
            WHERE attempt_id = ?
            ORDER BY id
            """,
            (attempt_id,),
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        conn.close()


def get_attempt_details(
    attempt_id,
):
    """
    Return one attempt together with its tool calls,
    patches, and test executions.

    This will later power the dashboard replay view.
    """

    conn = _connect()

    try:
        row = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE id = ?
            """,
            (attempt_id,),
        ).fetchone()

        if row is None:
            return None

        attempt = dict(row)

    finally:
        conn.close()

    attempt["tool_calls"] = (
        get_tool_calls(
            attempt_id
        )
    )

    attempt["patches"] = (
        get_patches(
            attempt_id
        )
    )

    attempt["test_results"] = (
        get_test_results(
            attempt_id
        )
    )

    return attempt