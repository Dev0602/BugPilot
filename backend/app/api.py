
import json
import os
import sqlite3
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import DB_PATH
from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the SQLite schema before accepting API requests."""
    init_db()
    yield


app = FastAPI(
    title="BugPilot API",
    version="2.0.0",
    description=(
        "API for BugPilot run history, attempts, "
        "tool calls, patches, and test results."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# Database helpers
# ---------------------------------------------------------

def get_db():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=10,
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA foreign_keys = ON"
    )

    return conn


def row_to_dict(row):
    if row is None:
        return None

    return dict(row)


def rows_to_dicts(rows):
    return [
        dict(row)
        for row in rows
    ]


def parse_json_field(
    value,
    default=None,
):
    if value is None:
        return default

    try:
        return json.loads(value)

    except (
        TypeError,
        json.JSONDecodeError,
    ):
        return default


def serialize_run(row):
    data = row_to_dict(row)

    if data is None:
        return None

    if "metadata_json" in data:
        data["metadata"] = parse_json_field(
            data.pop(
                "metadata_json"
            ),
            {},
        )

    return data


def serialize_run_result(row):
    data = row_to_dict(row)

    if data is None:
        return None

    if "raw_json" in data:
        data["raw"] = parse_json_field(
            data.pop(
                "raw_json"
            ),
            {},
        )

    return data


def serialize_tool_call(row):
    data = row_to_dict(row)

    if data is None:
        return None

    if "input_json" in data:
        data["input"] = parse_json_field(
            data.pop(
                "input_json"
            ),
            {},
        )

    data["is_error"] = bool(
        data.get(
            "is_error",
            0,
        )
    )

    return data


def serialize_patch(row):
    data = row_to_dict(row)

    if data is None:
        return None

    data["applied"] = bool(
        data.get(
            "applied",
            0,
        )
    )

    return data


def serialize_test_result(row):
    data = row_to_dict(row)

    if data is None:
        return None

    if data.get("passed") is not None:
        data["passed"] = bool(
            data["passed"]
        )

    return data


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------

@app.get("/api/health")
def health():
    conn = get_db()

    try:
        conn.execute(
            "SELECT 1"
        ).fetchone()

    finally:
        conn.close()

    return {
        "status": "ok",
        "database": DB_PATH,
    }


# ---------------------------------------------------------
# Latest-result compatibility endpoints
# ---------------------------------------------------------

@app.get("/api/results")
def get_latest_results():
    """
    Return the latest snapshot for each benchmark bug.

    This preserves access to the older `results` table while the
    dashboard transitions to run-history based views.
    """

    conn = get_db()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM results
            ORDER BY bug
            """
        ).fetchall()

    finally:
        conn.close()

    results = rows_to_dicts(
        rows
    )

    for result in results:
        result["success"] = bool(
            result.get(
                "success",
                0,
            )
        )

    return results


@app.get("/api/results/{bug_name}")
def get_latest_result(
    bug_name: str,
):
    conn = get_db()

    try:
        row = conn.execute(
            """
            SELECT *
            FROM results
            WHERE bug LIKE ?
            LIMIT 1
            """,
            (
                f"%{bug_name}%",
            ),
        ).fetchone()

    finally:
        conn.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Bug result not found",
        )

    result = dict(row)

    result["success"] = bool(
        result.get(
            "success",
            0,
        )
    )

    return result


@app.get("/api/summary")
def get_summary():
    """
    Summary of the latest per-bug result snapshot.
    """

    conn = get_db()

    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(
                    CASE
                        WHEN success = 1
                        THEN 1
                        ELSE 0
                    END
                ) AS successes,
                COALESCE(
                    SUM(cost_usd),
                    0
                ) AS total_cost,
                COALESCE(
                    SUM(latency_sec),
                    0
                ) AS total_latency
            FROM results
            """
        ).fetchone()

    finally:
        conn.close()

    total = (
        row["total"]
        or 0
    )

    successes = (
        row["successes"]
        or 0
    )

    success_rate = (
        successes
        / total
        * 100
        if total
        else 0
    )

    return {
        "total": total,
        "successes": successes,
        "success_rate": round(
            success_rate,
            1,
        ),
        "total_cost": round(
            row["total_cost"]
            or 0,
            5,
        ),
        "total_latency": round(
            row["total_latency"]
            or 0,
            1,
        ),
    }


# ---------------------------------------------------------
# Run history
# ---------------------------------------------------------

@app.get("/api/runs")
def get_runs(
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=500,
        ),
    ] = 50,
):
    """
    Return historical BugPilot runs.

    Unlike the old endpoint, this does not overwrite prior runs.
    """

    conn = get_db()

    try:
        rows = conn.execute(
            """
            SELECT
                r.*,

                COUNT(
                    rr.id
                ) AS result_count,

                COALESCE(
                    SUM(
                        CASE
                            WHEN rr.success = 1
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS resolved_count,

                COALESCE(
                    SUM(
                        rr.cost_usd
                    ),
                    0
                ) AS calculated_cost_usd,

                COALESCE(
                    SUM(
                        rr.latency_sec
                    ),
                    0
                ) AS calculated_latency_sec

            FROM runs AS r

            LEFT JOIN run_results AS rr
                ON rr.run_id = r.run_id

            GROUP BY r.run_id

            ORDER BY
                r.started_at DESC

            LIMIT ?
            """,
            (
                limit,
            ),
        ).fetchall()

    finally:
        conn.close()

    output = []

    for row in rows:
        run = serialize_run(
            row
        )

        result_count = (
            run.get(
                "result_count",
                0,
            )
            or 0
        )

        resolved_count = (
            run.get(
                "resolved_count",
                0,
            )
            or 0
        )

        run[
            "calculated_success_rate"
        ] = (
            round(
                resolved_count
                / result_count
                * 100,
                1,
            )
            if result_count
            else 0
        )

        run[
            "calculated_cost_usd"
        ] = round(
            run.get(
                "calculated_cost_usd",
                0,
            )
            or 0,
            5,
        )

        run[
            "calculated_latency_sec"
        ] = round(
            run.get(
                "calculated_latency_sec",
                0,
            )
            or 0,
            2,
        )

        output.append(
            run
        )

    return output


@app.get("/api/runs/{run_id}")
def get_run(
    run_id: str,
):
    conn = get_db()

    try:
        run_row = conn.execute(
            """
            SELECT *
            FROM runs
            WHERE run_id = ?
            """,
            (
                run_id,
            ),
        ).fetchone()

        if run_row is None:
            raise HTTPException(
                status_code=404,
                detail="Run not found",
            )

        summary_row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(
                    SUM(
                        CASE
                            WHEN success = 1
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS successes,
                COALESCE(
                    SUM(cost_usd),
                    0
                ) AS total_cost,
                COALESCE(
                    SUM(latency_sec),
                    0
                ) AS total_latency
            FROM run_results
            WHERE run_id = ?
            """,
            (
                run_id,
            ),
        ).fetchone()

    finally:
        conn.close()

    run = serialize_run(
        run_row
    )

    total = (
        summary_row["total"]
        or 0
    )

    successes = (
        summary_row[
            "successes"
        ]
        or 0
    )

    run["summary"] = {
        "total": total,
        "successes": successes,
        "success_rate": (
            round(
                successes
                / total
                * 100,
                1,
            )
            if total
            else 0
        ),
        "total_cost": round(
            summary_row[
                "total_cost"
            ]
            or 0,
            5,
        ),
        "total_latency": round(
            summary_row[
                "total_latency"
            ]
            or 0,
            2,
        ),
    }

    return run


@app.get(
    "/api/runs/{run_id}/results"
)
def get_run_results(
    run_id: str,
):
    conn = get_db()

    try:
        run_exists = conn.execute(
            """
            SELECT 1
            FROM runs
            WHERE run_id = ?
            """,
            (
                run_id,
            ),
        ).fetchone()

        if run_exists is None:
            raise HTTPException(
                status_code=404,
                detail="Run not found",
            )

        rows = conn.execute(
            """
            SELECT *
            FROM run_results
            WHERE run_id = ?
            ORDER BY bug
            """,
            (
                run_id,
            ),
        ).fetchall()

    finally:
        conn.close()

    output = []

    for row in rows:
        result = (
            serialize_run_result(
                row
            )
        )

        result["success"] = bool(
            result.get(
                "success",
                0,
            )
        )

        output.append(
            result
        )

    return output


@app.get(
    "/api/runs/{run_id}/attempts"
)
def get_run_attempts(
    run_id: str,
):
    conn = get_db()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE run_id = ?
            ORDER BY
                bug,
                attempt_number
            """,
            (
                run_id,
            ),
        ).fetchall()

    finally:
        conn.close()

    return rows_to_dicts(
        rows
    )


# ---------------------------------------------------------
# Attempt details / replay
# ---------------------------------------------------------

@app.get(
    "/api/attempts/{attempt_id}"
)
def get_attempt(
    attempt_id: int,
):
    conn = get_db()

    try:
        attempt = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE id = ?
            """,
            (
                attempt_id,
            ),
        ).fetchone()

    finally:
        conn.close()

    if attempt is None:
        raise HTTPException(
            status_code=404,
            detail="Attempt not found",
        )

    return dict(
        attempt
    )


@app.get(
    "/api/attempts/{attempt_id}/tool-calls"
)
def get_attempt_tool_calls(
    attempt_id: int,
):
    conn = get_db()

    try:
        attempt_exists = conn.execute(
            """
            SELECT 1
            FROM attempts
            WHERE id = ?
            """,
            (
                attempt_id,
            ),
        ).fetchone()

        if attempt_exists is None:
            raise HTTPException(
                status_code=404,
                detail="Attempt not found",
            )

        rows = conn.execute(
            """
            SELECT *
            FROM tool_calls
            WHERE attempt_id = ?
            ORDER BY sequence_number
            """,
            (
                attempt_id,
            ),
        ).fetchall()

    finally:
        conn.close()

    return [
        serialize_tool_call(
            row
        )
        for row in rows
    ]


@app.get(
    "/api/attempts/{attempt_id}/patches"
)
def get_attempt_patches(
    attempt_id: int,
):
    conn = get_db()

    try:
        attempt_exists = conn.execute(
            """
            SELECT 1
            FROM attempts
            WHERE id = ?
            """,
            (
                attempt_id,
            ),
        ).fetchone()

        if attempt_exists is None:
            raise HTTPException(
                status_code=404,
                detail="Attempt not found",
            )

        rows = conn.execute(
            """
            SELECT *
            FROM patches
            WHERE attempt_id = ?
            ORDER BY id
            """,
            (
                attempt_id,
            ),
        ).fetchall()

    finally:
        conn.close()

    return [
        serialize_patch(
            row
        )
        for row in rows
    ]


@app.get(
    "/api/attempts/{attempt_id}/tests"
)
def get_attempt_tests(
    attempt_id: int,
):
    conn = get_db()

    try:
        attempt_exists = conn.execute(
            """
            SELECT 1
            FROM attempts
            WHERE id = ?
            """,
            (
                attempt_id,
            ),
        ).fetchone()

        if attempt_exists is None:
            raise HTTPException(
                status_code=404,
                detail="Attempt not found",
            )

        rows = conn.execute(
            """
            SELECT *
            FROM test_results
            WHERE attempt_id = ?
            ORDER BY id
            """,
            (
                attempt_id,
            ),
        ).fetchall()

    finally:
        conn.close()

    return [
        serialize_test_result(
            row
        )
        for row in rows
    ]


# ---------------------------------------------------------
# Complete replay payload
# ---------------------------------------------------------

@app.get(
    "/api/attempts/{attempt_id}/replay"
)
def get_attempt_replay(
    attempt_id: int,
):
    """
    Return everything needed to replay one BugPilot attempt
    in the dashboard.
    """

    conn = get_db()

    try:
        attempt = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE id = ?
            """,
            (
                attempt_id,
            ),
        ).fetchone()

        if attempt is None:
            raise HTTPException(
                status_code=404,
                detail="Attempt not found",
            )

        tool_rows = conn.execute(
            """
            SELECT *
            FROM tool_calls
            WHERE attempt_id = ?
            ORDER BY sequence_number
            """,
            (
                attempt_id,
            ),
        ).fetchall()

        patch_rows = conn.execute(
            """
            SELECT *
            FROM patches
            WHERE attempt_id = ?
            ORDER BY id
            """,
            (
                attempt_id,
            ),
        ).fetchall()

        test_rows = conn.execute(
            """
            SELECT *
            FROM test_results
            WHERE attempt_id = ?
            ORDER BY id
            """,
            (
                attempt_id,
            ),
        ).fetchall()

    finally:
        conn.close()

    return {
        "attempt": dict(
            attempt
        ),
        "tool_calls": [
            serialize_tool_call(
                row
            )
            for row in tool_rows
        ],
        "patches": [
            serialize_patch(
                row
            )
            for row in patch_rows
        ],
        "tests": [
            serialize_test_result(
                row
            )
            for row in test_rows
        ],
    }


# ---------------------------------------------------------
# Server
# ---------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(
        os.environ.get(
            "PORT",
            8000,
        )
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
    )
