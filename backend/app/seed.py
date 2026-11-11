
import json
import sqlite3
from pathlib import Path

from .config import DB_PATH
from .db import init_db, start_run, save_result, finish_run


SEED_FILE = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "internal_benchmark_seed.json"
)

RUN_ID = "internal-20260917-133203"


def seed_internal_benchmark():
    """
    Import the recorded internal benchmark results.

    The import is idempotent: an existing run is
    not imported again on application restart.
    """

    if not SEED_FILE.is_file():
        print("No internal benchmark seed file found.")
        return

    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        existing = conn.execute(
            "SELECT 1 FROM runs WHERE run_id = ?",
            (RUN_ID,),
        ).fetchone()

    if existing:
        print("Internal benchmark already imported.")
        return

    with SEED_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    results = data["results"]

    if not isinstance(results, list) or not results:
        raise ValueError("Benchmark seed has no results")

    start_run(
        run_id=RUN_ID,
        model=data.get("model"),
        benchmark=data.get("benchmark", "internal"),
        metadata={
            "source_date": data.get("source_date"),
            "source": "Recorded internal benchmark",
            "imported_from": SEED_FILE.name,
        },
    )

    for result in results:
        save_result(
            result=result,
            run_timestamp=RUN_ID,
        )

    finish_run(
        run_id=RUN_ID,
        status="completed",
    )

    resolved = sum(
        bool(result.get("success"))
        for result in results
    )

    print(
        f"Imported {len(results)} benchmark results. "
        f"Resolved: {resolved}/{len(results)}"
    )


def seed_swebench_v3():
    """Import verified SWE-bench Lite V3 results."""

    seed_file = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "swebench_v3_seed.json"
    )

    if not seed_file.is_file():
        print("SWE-bench V3 seed file not found.")
        return

    data = json.loads(seed_file.read_text(encoding="utf-8"))
    results = data["results"]

    if (
        len(results) != 10
        or len({r["bug"] for r in results}) != 10
        or sum(bool(r["submitted"]) for r in results) != 7
        or sum(bool(r["success"]) for r in results) != 2
        or any(r["success"] and not r["submitted"] for r in results)
    ):
        raise ValueError("Invalid SWE-bench V3 results")

    init_db()

    run_id = "swebench-lite-v3-final-clean"

    with sqlite3.connect(DB_PATH) as conn:
        existing = conn.execute(
            "SELECT status FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()

    if existing and existing[0] == "completed":
        print("SWE-bench V3 already imported.")
        return

    start_run(
        run_id=run_id,
        benchmark="SWE-bench Lite V3",
        metadata={
            "source": "Official SWE-bench harness",
            "selected_count": 10,
            "submitted_count": 7,
            "not_submitted_count": 3,
            "missing_metrics": [
                "attempts",
                "cost_usd",
                "latency_sec",
                "coverage",
                "agent_traces",
            ],
        },
    )

    for result in results:
        save_result(
            result=result,
            run_timestamp=run_id,
        )

    finish_run(
        run_id=run_id,
        status="completed",
    )

    print("Imported SWE-bench V3: 2/10 resolved (20%)")