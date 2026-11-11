
import React, { useEffect, useMemo, useState } from "react";
import "./App.css";

const API_BASE = (
  process.env.REACT_APP_API_URL || "http://localhost:8000"
).replace(/\/$/, "");

async function apiFetch(path) {
  const response = await fetch(`${API_BASE}${path}`);

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;

    try {
      const payload = await response.json();
      message = payload.detail || payload.error || message;
    } catch (_) {
      // Keep the HTTP status when the server does not return JSON.
    }

    throw new Error(message);
  }

  return response.json();
}

function bugName(path) {
  return path ? path.split("/").pop() : "unknown";
}

function formatMoney(value) {
  if (value == null) return "N/A";
  return `$${Number(value).toFixed(5)}`;
}

function formatSeconds(value) {
  if (value == null) return "N/A";
  return `${Number(value).toFixed(1)}s`;
}

function truncate(value, limit = 420) {
  if (value == null) return "";

  const text =
    typeof value === "string"
      ? value
      : JSON.stringify(value, null, 2);

  return text.length <= limit
    ? text
    : `${text.slice(0, limit)}…`;
}

// SWE-bench V3 does not have recorded cost,
// latency, or attempt-count measurements.
function isMissingMetric(run, metric) {
  return (
    run?.metadata?.missing_metrics?.includes(metric) === true
  );
}

// The original imported result is stored in `raw`.
function isNotSubmitted(result) {
  return (
    result?.raw?.evaluation_status === "not_submitted" ||
    result?.raw?.submitted === false
  );
}

function resultStatus(result) {
  if (isNotSubmitted(result)) return "not-submitted";
  return result.success ? "pass" : "fail";
}

function buildReplaySteps(attemptReplay) {
  const steps = [];

  const attempt = attemptReplay.attempt || {};
  const attemptNumber = attempt.attempt_number ?? "?";

  const tests = attemptReplay.tests || [];
  const toolCalls = attemptReplay.tool_calls || [];
  const patches = attemptReplay.patches || [];

  tests
    .filter((test) => test.phase === "initial")
    .forEach((test) => {
      steps.push({
        kind: "test",
        status: test.passed ? "pass" : "fail",
        label: `Attempt ${attemptNumber} · Initial test`,
        detail: test.passed
          ? "Tests were already passing."
          : "Bug reproduced in the sandbox.",
        body: test.logs || "",
      });
    });

  toolCalls.forEach((tool) => {
    const input = tool.input || {};
    const detailParts = [];

    if (
      tool.tool_name === "read_file" &&
      input.filepath
    ) {
      detailParts.push(input.filepath);
    } else if (
      tool.tool_name === "search_code" &&
      input.keyword
    ) {
      detailParts.push(`keyword: ${input.keyword}`);
    } else if (
      tool.tool_name === "get_function_signature" &&
      input.function_name
    ) {
      detailParts.push(input.function_name);
    } else if (tool.tool_name === "list_directory") {
      detailParts.push(input.path || ".");
    } else if (tool.tool_name === "submit_fix") {
      if (input.file_path) {
        detailParts.push(input.file_path);
      }

      if (input.function_name) {
        detailParts.push(input.function_name);
      }
    }

    if (tool.duration_ms != null) {
      detailParts.push(
        `${Number(tool.duration_ms).toFixed(2)} ms`
      );
    }

    steps.push({
      kind: "tool",
      status: tool.is_error ? "fail" : "neutral",
      label: `Attempt ${attemptNumber} · ${tool.tool_name}`,
      detail: detailParts.join(" · ") || "Agent tool call",
      body:
        tool.tool_name === "submit_fix"
          ? truncate(
              {
                diagnosis: input.diagnosis,
                file_path: input.file_path,
                function_name: input.function_name,
              },
              900
            )
          : truncate(
              tool.output_text || tool.input || "",
              1200
            ),
    });
  });

  patches.forEach((patch) => {
    steps.push({
      kind: "patch",
      status: patch.applied ? "pass" : "fail",
      label: `Attempt ${attemptNumber} · Patch`,
      detail: `${patch.file_path || "source file"}${
        patch.function_name
          ? ` · ${patch.function_name}`
          : ""
      }`,
      body:
        patch.diff_text ||
        truncate(patch.patched_code || "", 1800),
    });
  });

  tests
    .filter((test) => test.phase !== "initial")
    .forEach((test) => {
      const coverage =
        test.coverage != null
          ? ` · coverage ${test.coverage}%`
          : "";

      steps.push({
        kind: "test",
        status: test.passed ? "pass" : "fail",
        label: `Attempt ${attemptNumber} · Verification`,
        detail: `${
          test.passed ? "PASS" : "FAIL"
        }${coverage}`,
        body: truncate(test.logs || "", 1400),
      });
    });

  return steps;
}

function App() {
  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [runResults, setRunResults] = useState([]);
  const [runAttempts, setRunAttempts] = useState([]);
  const [selected, setSelected] = useState(null);

  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingRun, setLoadingRun] = useState(false);
  const [error, setError] = useState("");

  const [replaySteps, setReplaySteps] = useState([]);
  const [
    visibleReplaySteps,
    setVisibleReplaySteps,
  ] = useState([]);
  const [isReplaying, setIsReplaying] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadRuns() {
      try {
        setLoadingRuns(true);
        setError("");

        const data = await apiFetch("/api/runs");

        if (cancelled) return;

        setRuns(data);
        setSelectedRunId(
          data.length ? data[0].run_id : ""
        );
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
        }
      } finally {
        if (!cancelled) {
          setLoadingRuns(false);
        }
      }
    }

    loadRuns();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedRunId) {
      setRunResults([]);
      setRunAttempts([]);
      setSelected(null);
      return;
    }

    let cancelled = false;

    async function loadRunData() {
      try {
        setLoadingRun(true);
        setError("");
        setReplaySteps([]);
        setVisibleReplaySteps([]);
        setIsReplaying(false);

        const [results, attempts] = await Promise.all([
          apiFetch(
            `/api/runs/${encodeURIComponent(
              selectedRunId
            )}/results`
          ),
          apiFetch(
            `/api/runs/${encodeURIComponent(
              selectedRunId
            )}/attempts`
          ),
        ]);

        if (cancelled) return;

        setRunResults(results);
        setRunAttempts(attempts);
        setSelected(results[0] || null);
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
          setRunResults([]);
          setRunAttempts([]);
          setSelected(null);
        }
      } finally {
        if (!cancelled) {
          setLoadingRun(false);
        }
      }
    }

    loadRunData();

    return () => {
      cancelled = true;
    };
  }, [selectedRunId]);

  const selectedRun = useMemo(
    () =>
      runs.find(
        (run) => run.run_id === selectedRunId
      ) || null,
    [runs, selectedRunId]
  );

  const summary = useMemo(() => {
    const total = runResults.length;

    const successes = runResults.filter(
      (result) => result.success
    ).length;

    const totalCost = runResults.reduce(
      (sum, result) =>
        sum + Number(result.cost_usd || 0),
      0
    );

    const totalLatency = runResults.reduce(
      (sum, result) =>
        sum + Number(result.latency_sec || 0),
      0
    );

    return {
      total,
      successes,
      successRate: total
        ? (successes / total) * 100
        : 0,
      totalCost,
      totalLatency,
    };
  }, [runResults]);

  const selectedAttempts = useMemo(() => {
    if (!selected) return [];

    return runAttempts
      .filter(
        (attempt) => attempt.bug === selected.bug
      )
      .sort(
        (a, b) =>
          a.attempt_number - b.attempt_number
      );
  }, [runAttempts, selected]);

  const missingAttempts = isMissingMetric(
    selectedRun,
    "attempts"
  );

  const missingCost = isMissingMetric(
    selectedRun,
    "cost_usd"
  );

  const missingLatency = isMissingMetric(
    selectedRun,
    "latency_sec"
  );

  async function runReplay() {
    if (
      !selected ||
      !selectedAttempts.length ||
      isReplaying
    ) {
      return;
    }

    try {
      setError("");
      setIsReplaying(true);
      setReplaySteps([]);
      setVisibleReplaySteps([]);

      const replayPayloads = [];

      for (const attempt of selectedAttempts) {
        const payload = await apiFetch(
          `/api/attempts/${attempt.id}/replay`
        );

        replayPayloads.push(payload);
      }

      const steps = replayPayloads.flatMap(
        buildReplaySteps
      );

      setReplaySteps(steps);

      for (
        let index = 0;
        index < steps.length;
        index += 1
      ) {
        await new Promise((resolve) =>
          setTimeout(resolve, 420)
        );

        setVisibleReplaySteps(
          steps.slice(0, index + 1)
        );
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsReplaying(false);
    }
  }

  function selectResult(result) {
    setSelected(result);
    setReplaySteps([]);
    setVisibleReplaySteps([]);
    setIsReplaying(false);
  }

  if (loadingRuns) {
    return (
      <div className="App">
        <div className="page-state">
          Loading BugPilot run history…
        </div>
      </div>
    );
  }

  return (
    <div className="App">
      <header className="hero">
        <div>
          <div className="eyebrow">
            Autonomous debugging observability
          </div>

          <h1>BugPilot</h1>

          <p className="tagline">
            Real run history, agent tool traces,
            generated patches, and sandbox verification.
          </p>
        </div>

        <div className="run-picker">
          <label htmlFor="run-select">Run</label>

          <select
            id="run-select"
            value={selectedRunId}
            onChange={(event) =>
              setSelectedRunId(event.target.value)
            }
            disabled={runs.length === 0}
          >
            {runs.length === 0 && (
              <option value="">
                No runs available
              </option>
            )}

            {runs.map((run) => (
              <option
                key={run.run_id}
                value={run.run_id}
              >
                {run.run_id} · {run.status}
              </option>
            ))}
          </select>

          {selectedRun && (
            <div className="run-meta">
              <span>
                {selectedRun.benchmark || "benchmark"}
              </span>

              <span>
                {selectedRun.model || "Not recorded"}
              </span>

              <span
                className={`status-pill ${
                  selectedRun.status || "unknown"
                }`}
              >
                {selectedRun.status || "unknown"}
              </span>
            </div>
          )}
        </div>
      </header>

      {error && (
        <div className="error-banner">
          <strong>Dashboard error:</strong>{" "}
          {error}
        </div>
      )}

      <section
        className="stats"
        aria-label="Run summary"
      >
        <div className="stat-card">
          <div className="stat-label">
            Resolved
          </div>

          <div className="stat-value success">
            {summary.successes}/{summary.total}
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">
            Success rate
          </div>

          <div className="stat-value">
            {summary.successRate.toFixed(0)}%
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">
            Model cost
          </div>

          <div className="stat-value small">
            {missingCost
              ? "N/A"
              : formatMoney(summary.totalCost)}
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">
            Model latency
          </div>

          <div className="stat-value small">
            {missingLatency
              ? "N/A"
              : formatSeconds(summary.totalLatency)}
          </div>
        </div>
      </section>

      {selectedRun?.metadata?.submitted_count != null && (
        <p className="page-state">
          Official SWE-bench:{" "}
          {selectedRun.metadata.submitted_count} submitted
          out of{" "}
          {selectedRun.metadata.selected_count} selected.
          Unsubmitted issues count toward the overall
          result but are not claimed to be failed patches.
        </p>
      )}

      <section className="section-heading">
        <div>
          <h2>Run results</h2>

          <p>
            Select a bug to inspect its diagnosis
            and any recorded agent trace.
          </p>
        </div>

        {selectedRunId && (
          <code className="run-id">
            {selectedRunId}
          </code>
        )}
      </section>

      {loadingRun ? (
        <div className="page-state">
          Loading run details…
        </div>
      ) : runResults.length === 0 ? (
        <div className="empty-state">
          No saved bug results were found for this run.
        </div>
      ) : (
        <div className="layout">
          <div className="bug-list">
            {runResults.map((result) => (
              <button
                type="button"
                key={`${result.run_id}-${result.bug}`}
                className={`bug-row ${
                  selected?.bug === result.bug
                    ? "selected"
                    : ""
                }`}
                onClick={() => selectResult(result)}
              >
                <span
                  className={`dot ${resultStatus(
                    result
                  )}`}
                  style={
                    isNotSubmitted(result)
                      ? {
                          backgroundColor: "#94a3b8",
                        }
                      : undefined
                  }
                />

                <span className="bug-name">
                  {bugName(result.bug)}
                  {isNotSubmitted(result)
                    ? " · Not submitted"
                    : ""}
                </span>

                <span className="bug-meta">
                  {missingAttempts
                    ? "N/A attempts"
                    : `${
                        result.attempts
                      } attempt${
                        result.attempts === 1
                          ? ""
                          : "s"
                      }`}
                  {" · "}
                  {missingCost
                    ? "Cost N/A"
                    : formatMoney(result.cost_usd)}
                  {" · "}
                  {missingLatency
                    ? "Time N/A"
                    : formatSeconds(result.latency_sec)}
                  {result.coverage != null
                    ? ` · cov ${result.coverage}%`
                    : ""}
                </span>
              </button>
            ))}
          </div>

          <aside className="detail-panel">
            {selected ? (
              <div className="detail">
                <div
                  className={`detail-status ${resultStatus(
                    selected
                  )}`}
                  style={
                    isNotSubmitted(selected)
                      ? {
                          backgroundColor: "#64748b",
                        }
                      : undefined
                  }
                >
                  {isNotSubmitted(selected)
                    ? "— Not submitted"
                    : selected.success
                      ? "✓ Fixed"
                      : "✗ Failed"}
                </div>

                <h3>{bugName(selected.bug)}</h3>

                <div className="attempt-strip">
                  {selectedAttempts.length > 0 ? (
                    selectedAttempts.map(
                      (attempt) => (
                        <span
                          key={attempt.id}
                          className={`attempt-chip ${
                            attempt.status || ""
                          }`}
                        >
                          Attempt{" "}
                          {attempt.attempt_number} ·{" "}
                          {attempt.status}
                        </span>
                      )
                    )
                  ) : (
                    <span className="attempt-chip">
                      No traced attempts
                    </span>
                  )}
                </div>

                <button
                  className="replay-btn"
                  onClick={runReplay}
                  disabled={
                    isReplaying ||
                    selectedAttempts.length === 0
                  }
                >
                  {isReplaying
                    ? "Replaying real trace…"
                    : selectedAttempts.length === 0
                      ? "No trace available"
                      : "▶ Replay real agent trace"}
                </button>

                <div className="detail-metrics">
                  <div>
                    <span>Attempts</span>
                    {missingAttempts
                      ? "N/A"
                      : selected.attempts}
                  </div>

                  <div>
                    <span>Cost</span>
                    {missingCost
                      ? "N/A"
                      : formatMoney(selected.cost_usd)}
                  </div>

                  <div>
                    <span>Time</span>
                    {missingLatency
                      ? "N/A"
                      : formatSeconds(
                          selected.latency_sec
                        )}
                  </div>

                  {selected.coverage != null && (
                    <div>
                      <span>Coverage</span>
                      {selected.coverage}%
                    </div>
                  )}
                </div>

                <div className="detail-block">
                  <b>Diagnosis</b>

                  <p>
                    {selected.diagnosis ||
                      (isNotSubmitted(selected)
                        ? "No prediction was submitted for this issue."
                        : "No diagnosis was recorded in the source results.")}
                  </p>
                </div>

                <div className="detail-block">
                  <b>Target</b>

                  <div className="code-stack">
                    <code>
                      {selected.file_path || "N/A"}
                    </code>

                    <code>
                      {selected.function_name
                        ? `${selected.function_name}()`
                        : "N/A"}
                    </code>
                  </div>
                </div>

                {visibleReplaySteps.length > 0 && (
                  <div className="replay-log">
                    <div className="replay-heading">
                      <b>Real agent replay</b>
                      <span>
                        {visibleReplaySteps.length}/
                        {replaySteps.length}
                      </span>
                    </div>

                    {visibleReplaySteps.map(
                      (step, index) => (
                        <div
                          key={`${step.label}-${index}`}
                          className={`replay-step ${step.kind} ${step.status}`}
                        >
                          <div className="replay-index">
                            {index + 1}
                          </div>

                          <div className="replay-content">
                            <div className="replay-label">
                              {step.label}
                            </div>

                            <div className="replay-detail">
                              {step.detail}
                            </div>

                            {step.body && (
                              <pre className="replay-body">
                                {step.body}
                              </pre>
                            )}
                          </div>
                        </div>
                      )
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="empty-state">
                Select a bug to see details.
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}

export default App;
