
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
