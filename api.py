from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    conn = sqlite3.connect("bugpilot.db")
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/api/runs")
def get_runs():
    conn = get_db()
    rows = conn.execute("SELECT * FROM results ORDER BY bug").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/summary")
def get_summary():
    conn = get_db()
    rows = conn.execute("SELECT * FROM results").fetchall()
    conn.close()
    total = len(rows)
    successes = sum(1 for r in rows if r["success"])
    total_cost = sum(r["cost_usd"] or 0 for r in rows)
    total_latency = sum(r["latency_sec"] or 0 for r in rows)
    return {
        "total": total,
        "successes": successes,
        "success_rate": round(successes / total * 100, 1) if total else 0,
        "total_cost": round(total_cost, 5),
        "total_latency": round(total_latency, 1),
    }
    
@app.get("/api/runs/{bug_name}")
def get_run(bug_name: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM results WHERE bug LIKE ?", (f"%{bug_name}%",)).fetchone()
    conn.close()
    return dict(row) if row else {"error": "not found"}

if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)