# BugPilot

**BugPilot is an autonomous AI debugging agent that diagnoses failing tests, investigates a codebase using real tools, generates targeted function-level patches, executes them inside a network-isolated Docker sandbox, and retries failed repairs — with exponential backoff and failure memory — using feedback from previous attempts.**

![BugPilot architecture](screenshots/architecture.png)

## Overview

Most demos of "AI that writes code" stop at generating a plausible-looking answer. BugPilot goes further: given a codebase with a failing test, it investigates the failure itself — reading files, searching code, and inspecting function signatures, all without being told where the bug is — proposes a fix, applies it, and **verifies the fix actually works** by re-running the real test suite inside an isolated, network-disabled sandbox. If the fix doesn't work, it retries with exponential backoff, carrying the memory of what didn't work into the next attempt.

It was evaluated against a one-shot Claude baseline (no sandbox, no tools, no retries) across a 20-bug benchmark, including one real regression injected into a production codebase I built and shipped separately.

## Why BugPilot?

Anyone can paste an error into a chatbot and get a suggested fix. What's harder — and more representative of real engineering work — is a system that:

- Investigates a failure without being told where the bug is
- Verifies its own answer is actually correct, rather than just plausible
- Recovers from a wrong first attempt using structured, backed-off retries
- Runs in a genuinely isolated environment, with no network access during execution
- Reports honest, measured results rather than a marketing claim

## Architecture

The full system: a failing test feeds into the agent, which reasons with Claude, calls real investigation tools, generates a targeted patch, and verifies it inside a network-isolated Docker sandbox — retrying with backoff on failure, and logging every attempt to both JSON and SQLite.

See `screenshots/architecture.png` for the full diagram. Key stages:

```
Failing test
    |
BugPilot Agent (Claude + tools: list_directory, search_code,
                   get_function_signature, submit_fix)
    |
Diagnose bug -> Generate function-level patch -> Apply patch
    |
Docker sandbox (bugpilot-sandbox image, network-isolated)
    |
Run tests + collect coverage
    |
   Pass? --yes--> Done, results saved (JSON + SQLite)
    |no
    |
Retry with feedback (exponential backoff: 1.5s -> 3s -> 6s, max 3 attempts,
                      stops early if the same diagnosis repeats)
    |
    +----------------> back to Agent
```

## How It Works

1. **Run tests** inside an isolated, network-disabled Docker container — a failure here is the trigger for everything downstream.
2. **Investigate** — Claude may call `list_directory`, `search_code`, or `get_function_signature` to understand the codebase before deciding on a fix. This is a genuine multi-turn tool-calling loop, not a single request/response.
3. **Diagnose and generate a patch** — Claude identifies the single function responsible and returns the corrected version of just that function, not a full-file rewrite.
4. **Apply the patch** via a regex-based function-level find/replace, leaving the rest of the file untouched.
5. **Re-run tests** (with coverage) inside the sandbox to verify the fix actually works.
6. **Retry if needed** — up to 3 attempts, each with exponential backoff (1.5s, 3s, 6s) and the full history of prior failed attempts, so the model doesn't repeat itself. If two consecutive attempts produce the same diagnosis, BugPilot stops early rather than burning a wasted third attempt.
7. **Record results** — every run writes to both a per-bug JSON file and a SQLite database, plus a timestamped log of the full run.

## Tool Calling

Early versions asked Claude to return a diagnosis and fixed code as free-text JSON. This broke on any code containing regex or backslashes — the escaping was unreliable. BugPilot instead uses the Anthropic API's structured tool-calling: a `submit_fix` tool with an explicit schema (`diagnosis`, `function_name`, `fixed_function_code`) that Claude fills in directly, guaranteeing well-formed output.

Beyond `submit_fix`, BugPilot offers three real investigation tools:
- **`list_directory`** — lists files in the bug's folder
- **`search_code`** — greps across files for a keyword or function name, returning file/line/text matches
- **`get_function_signature`** — returns just a function's signature line (not its full body), useful for quick context without pulling in a whole file

Claude genuinely chooses to use these mid-diagnosis on most bugs — confirmed by observing real tool calls in the run logs, not just wiring them up unused.

## Docker Sandbox

Every test run happens inside a custom-built image, `bugpilot-sandbox`, defined in the project's `Dockerfile`:

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir pytest pytest-cov
WORKDIR /app
```

Pre-installing `pytest`/`pytest-cov` at build time (rather than at test-run time) means the container needs **no network access to run tests** — so every test run uses `network_disabled=True`, giving genuine network isolation. An earlier attempt to enable this on the stock `python:3.12-slim` image broke, because `pip install` at runtime needs network access; building a custom image with dependencies pre-baked was the correct fix.

The workspace is mounted read-write (patches need to be written to disk), but no external network access is available once the container starts.

## Patch Generation

BugPilot patches at the **function level**, not the file level. Early versions asked Claude to rewrite the entire file on every fix — this worked for small toy files but hit the model's output token limit on a real ~330-line production file. The fix: ask for only the one broken function, then splice it into the existing file via regex. This is both more token-efficient and a safer pattern for autonomous code modification generally — the agent only touches the code it diagnosed as broken.

## Verification & Retry

A fix is only considered successful if the **real test suite passes** after it's applied — not because the patch "looks right." If tests still fail, BugPilot retries (up to `MAX_ATTEMPTS = 3`) with exponential backoff between attempts, passing the full history of prior diagnoses to the next attempt. If two consecutive attempts produce an identical diagnosis, BugPilot stops early rather than continuing to spin — a sign the agent is stuck, not making progress.

## Benchmark

20 reproducible bugs, each isolated in its own folder with a broken implementation and a test suite that exposes the defect:

| Category | Bugs |
|---|---|
| Arithmetic | 2 |
| Boundary / off-by-one | 3 |
| String logic | 2 |
| Python-specific gotcha | 1 |
| Data structures (list/dict/set) | 3 |
| Recursion | 2 |
| Exception handling | 2 |
| Algorithm (binary search) | 1 |
| Edge case (empty input) | 2 |
| Regression (real production code) | 2 |

One bug (`bug_09_ats_exact_match`) is not synthetic — it's a real function (`_exact_match`) extracted from **[Taylrd](https://github.com/Dev0602/taylrd)**, an AI resume-tailoring platform I built and shipped separately, with a realistic regression (loss of regex word-boundary matching) reintroduced. Another (`bug_20_buzzword_detection`) mirrors a similar case-sensitivity pattern from the same codebase.

## Results

**Final result: 20/20 bugs fixed (100%)**, using the complete system — real network isolation, 4-tool investigation, coverage tracking, exponential backoff, and dual storage, all working together.

| Metric | BugPilot | Baseline (one-shot Claude) |
|---|---|---|
| Bugs tested | 20 | 20 |
| Fixed | 20/20 | 20/20 |
| Success rate | 100% | 100% |
| Verification | Real sandboxed test re-execution | None |
| Retry on failure | Yes (max 3, exponential backoff, failure memory) | No |
| Investigation tools | Yes (4 tools, multi-turn) | No |
| Network isolation | Yes | N/A |

### Honest finding

BugPilot and the one-shot Claude baseline both achieved 100% repair success on this 20-bug benchmark. This indicates the benchmark was not sufficiently difficult to demonstrate a raw success-rate advantage for the agentic workflow — `claude-haiku-4-5` is simply capable enough at these single-function, clearly-scoped bugs to solve them reliably without tools or retries.

BugPilot's demonstrated contribution is therefore **automated execution-based verification, isolated patch application, real investigation tooling, and structured retry handling with failure memory** — not a claimed improvement in raw repair accuracy. A one-shot answer is never actually confirmed correct; BugPilot's is, every time, by construction.

A secondary honest finding: giving the agent investigation tools increases cost meaningfully (each investigation step is a full extra round-trip to Claude) even when the bug doesn't strictly require investigation — a real, quantified capability-vs-cost tradeoff worth accounting for in any production use of this pattern.

## Example Run

```
BUG: bugs/bug_09_ats_exact_match
==================================================
--- Attempt 1 of 3 ---
  (investigating: list_directory({}))
  (investigating: search_code({'keyword': 'def _exact_match'}))
Diagnosis: The function performs a naive substring match instead of
respecting word boundaries, causing partial matches like "js" to
match within "jsonify".
Patching function: _exact_match
SUCCESS after 1 attempt(s) | cost=$0.00674 | time=2.1s
```

## Project Structure

```
BugPilot/
├── agent.py               # Core agent: sandbox, tools, diagnosis, patching, retry loop
├── tools.py                 # read_file / write_file / list_directory / search_code / get_function_signature
├── db.py                     # SQLite storage (init_db, save_result, get_all_results)
├── baseline.py                 # One-shot comparison system (no tools/sandbox)
├── run_baseline.py               # Runs the baseline across all bugs
├── reset_bugs.py                   # Restores all bugs to their broken state
├── Dockerfile                       # Custom sandbox image (pytest/pytest-cov pre-installed)
├── requirements.txt
├── .env.example
├── .gitignore
│
├── bugs/
│   ├── bug_01_calculator/ ... bug_20_buzzword_detection/
│   └── (each: source file + test file)
│
├── results/
│   └── bug_XX.json          # Structured result per bug
│
├── logs/
│   └── run_TIMESTAMP.json     # Timestamped full-run logs
│
├── bugpilot.db                # SQLite database (all results, queryable)
│
├── frontend/
│   └── index.html                # Dashboard: bug browser + benchmark comparison view
│
└── screenshots/
    └── architecture.png            # Architecture diagram
```

## Installation

```bash
git clone https://github.com/Dev0602/BugPilot.git
cd BugPilot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your ANTHROPIC_API_KEY
docker build -t bugpilot-sandbox .
```

Requires Docker Desktop running locally.

## Running BugPilot

```bash
python3 agent.py
```

## Running the Baseline

```bash
python3 reset_bugs.py
python3 run_baseline.py
```

## Running the Benchmark

```bash
python3 reset_bugs.py
python3 agent.py        # writes results/*.json and bugpilot.db
open frontend/index.html
```

## Querying Results

Since results are stored in SQLite, they're directly queryable:

```python
import sqlite3
conn = sqlite3.connect("bugpilot.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT bug, attempts, cost_usd, coverage
    FROM results ORDER BY cost_usd DESC LIMIT 5
""").fetchall()
```

This surfaced a real finding: `bug_17_recursion` and `bug_08_factorial` are consistently BugPilot's two most expensive bugs to fix — reasoning about recursive base cases appears to require meaningfully more tokens than other bug categories.

## Limitations

- Current benchmark focuses on Python bugs.
- The benchmark uses relatively small, mostly single-file functions.
- BugPilot currently modifies a single function at a time.
- Multi-file dependency reasoning is not currently supported — no repository-wide index or file context cache.
- The sandbox workspace is mounted read-write, not read-only.
- Benchmark size is limited to 20 bugs.
- Results depend on the underlying LLM (`claude-haiku-4-5`).

## Future Work

- Repository index / file context caching (would require embeddings or vector search — a meaningfully larger subsystem, deliberately deferred)
- Read-only sandbox mounts where the patch target isn't the only file present
- S3 (or similar) storage option alongside local JSON/SQLite
- React/HTMX frontend rebuild (current static HTML dashboard is functional; this would be a polish pass, not new capability)
- Full tracing / reporting dashboard system beyond the current timestamped logs and SQL queries

---

Built by Baireddy Venkata Devendhar Reddy · [github.com/Dev0602](https://github.com/Dev0602)
