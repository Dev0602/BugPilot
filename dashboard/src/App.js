import { useState, useEffect } from "react";
import "./App.css";

const API_BASE = "https://bugpilot-8nbi.onrender.com";

const REPLAY_STAGES = (bug) => [
  { label: "Running tests...", detail: "pytest -v --cov=. --cov-report=term-missing", delay: 700 },
  { label: "Test failed ✗", detail: "Investigating with list_directory, search_code...", delay: 900 },
  { label: "Diagnosis complete", detail: bug.diagnosis || "N/A", delay: 1200 },
  { label: `Patching ${bug.function_name || "function"}()`, detail: "Applying function-level patch", delay: 800 },
  { label: "Re-running tests...", detail: "Verifying fix in isolated sandbox", delay: 900 },
  { label: "Fixed", detail: `${bug.attempts} attempt(s) · $${bug.cost_usd?.toFixed(5)} · ${bug.latency_sec}s`, delay: 0 },
];

function App() {
  const [summary, setSummary] = useState(null);
  const [runs, setRuns] = useState([]);
  const [selected, setSelected] = useState(null);
  const [replaySteps, setReplaySteps] = useState([]);
  const [isReplaying, setIsReplaying] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/summary`).then(r => r.json()).then(setSummary);
    fetch(`${API_BASE}/api/runs`).then(r => r.json()).then(data => {
      setRuns(data);
      if (data.length) setSelected(data[0]);
    });
  }, []);

  const runReplay = async (bug) => {
  setIsReplaying(true);
  setReplaySteps([]);
  const stages = REPLAY_STAGES(bug);

  for (let i = 0; i < stages.length; i++) {
    await new Promise((resolve) => setTimeout(resolve, stages[i].delay));
    setReplaySteps((prev) => [...prev, stages[i]]);
  }
  setIsReplaying(false);
};

if (!summary) return (
  <div className="App">
    <p className="loading">
      Waking up the backend... this can take up to 50 seconds on first load
      (free-tier hosting spins down when idle).
    </p>
  </div>
);


  return (
    <div className="App">
      <header>
        <h1>BugPilot Dashboard</h1>
        <p className="tagline">Autonomous AI debugging agent — live results</p>
      </header>

      <div className="stats">
        <div className="stat-card">
          <div className="stat-label">Bugs Fixed</div>
          <div className="stat-value success">{summary.successes} / {summary.total}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Success Rate</div>
          <div className="stat-value success">{summary.success_rate}%</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Cost</div>
          <div className="stat-value">${summary.total_cost}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Time</div>
          <div className="stat-value">{summary.total_latency}s</div>
        </div>
      </div>

      <h2>Bug Runs</h2>

      <div className="layout">
        <div className="bug-list">
          {runs.map((r) => (
            <div
              key={r.bug}
              className={`bug-row ${selected?.bug === r.bug ? "selected" : ""}`}
              onClick={() => { setSelected(r); setReplaySteps([]); }}
            >
              <span className={`dot ${r.success ? "pass" : "fail"}`}></span>
              <span className="bug-name">{r.bug.split("/").pop()}</span>
              <span className="bug-meta">
                {r.attempts} attempt{r.attempts !== 1 ? "s" : ""} · ${r.cost_usd?.toFixed(5)} · {r.latency_sec}s
                {r.coverage != null ? ` · cov ${r.coverage}%` : ""}
              </span>
            </div>
          ))}
        </div>

        <div className="detail-panel">
          {selected ? (
            <div className="detail">
              <div className={`detail-status ${selected.success ? "pass" : "fail"}`}>
                {selected.success ? "✓ Fixed" : "✗ Failed"}
              </div>
              <h3>{selected.bug.split("/").pop()}</h3>

              <button
                className="replay-btn"
                onClick={() => runReplay(selected)}
                disabled={isReplaying}
              >
                {isReplaying ? "Replaying..." : "▶ Replay this run"}
              </button>

              <div className="detail-metrics">
                <div><span>Attempts</span>{selected.attempts}</div>
                <div><span>Cost</span>${selected.cost_usd?.toFixed(5)}</div>
                <div><span>Time</span>{selected.latency_sec}s</div>
                {selected.coverage != null && <div><span>Coverage</span>{selected.coverage}%</div>}
              </div>

              <div className="detail-block">
                <b>Diagnosis</b>
                <p>{selected.diagnosis || "Already passing — no fix needed."}</p>
              </div>

              <div className="detail-block">
                <b>Function Patched</b>
                <code>{selected.function_name || "N/A"}()</code>
              </div>
              {replaySteps.length > 0 && (
                <div className="replay-log">
                  <b>Replay</b>
                  {replaySteps.map((step, i) => (
                    <div key={i} className="replay-step">
                      <div className="replay-label">{step.label}</div>
                      <div className="replay-detail">{step.detail}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="loading">Select a bug to see details</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;

