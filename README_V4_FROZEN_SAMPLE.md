# BugPilot v4 — reproducible evaluation selection

Fixes repeat selection from old SWE-bench runs. No changes to the agent or evaluator.

## One-time dry run (no Claude API use)

From repository root:

```bash
python -m evaluation.swebench.current.generate --count 10 --seed bugpilot-v4-locked-20261018 --output-dir evaluation/swebench/current/runs/v4_locked_clean --exclude-previous-selections --dry-run
```

`--exclude-previous-selections` scans every sibling run's `selected_instances.json`, excluding all prior selected IDs, **including earlier dry runs**. It excludes the current output directory. It never searches nested third-party repositories.

The saved `selected_instances.json` is the frozen sample. Leave it unchanged.

## Subsequent paid run

**Only after separately confirming model, expected costs, Docker image coverage, evaluation environment, and sample**, reuse precisely the frozen IDs with `--reuse-selected` and the same output directory, same dataset, and count. E.g.:

```bash
python -m evaluation.swebench.current.generate --count 10 --seed bugpilot-v4-locked-20261018 --output-dir evaluation/swebench/current/runs/v4_locked_clean --reuse-selected
```

The `--reuse-selected` flag refuses to run if the file is missing, inconsistent, or contains duplicate IDs. It never resamples. The command above runs Claude and may incur API charges. For a real run with public-test verification, configure compatible Docker images separately using the existing `--public-test-images` option. Unconfigured repos remain without public-test verification.

The source records passed to the agent are still sanitized by `deterministic_subset` and `public_instance_dict`. A saved dry run is not a completed benchmark.
