import sqlite3
import json

DB_PATH = "bugpilot.db"

def init_db():
    """Creates the results table if it doesn't already exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS results (
            bug TEXT PRIMARY KEY,
            success INTEGER,
            attempts INTEGER,
            cost_usd REAL,
            latency_sec REAL,
            coverage INTEGER,
            diagnosis TEXT,
            function_name TEXT,
            run_timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_result(result, run_timestamp):
    """Inserts or updates one bug's result in the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO results (bug, success, attempts, cost_usd, latency_sec, coverage, diagnosis, function_name, run_timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(bug) DO UPDATE SET
            success=excluded.success,
            attempts=excluded.attempts,
            cost_usd=excluded.cost_usd,
            latency_sec=excluded.latency_sec,
            coverage=excluded.coverage,
            diagnosis=excluded.diagnosis,
            function_name=excluded.function_name,
            run_timestamp=excluded.run_timestamp
    """, (
        result["bug"], int(result["success"]), result["attempts"],
        result["cost_usd"], result["latency_sec"], result.get("coverage"),
        result.get("diagnosis"), result.get("function_name"), run_timestamp,
    ))
    conn.commit()
    conn.close()


def get_all_results():
    """Returns all saved results as a list of dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM results ORDER BY bug").fetchall()
    conn.close()
    return [dict(row) for row in rows]