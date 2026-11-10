"""Freeze clean SWE-bench selections without exposing evaluation oracle fields.

This module handles *only instance IDs*, not gold patches, hidden tests, or
FAIL_TO_PASS/PASS_TO_PASS information. Its caller retains the usual public
instance sanitization before invoking an agent.
"""

import json
from pathlib import Path


def _ids_from_file(path):
    values = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(values, list):
        raise ValueError(f"Expected an instance list in {path}")
    result = []
    for value in values:
        instance_id = value.get("instance_id") if isinstance(value, dict) else None
        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError(f"Invalid instance record in {path}")
        result.append(instance_id)
    if len(result) != len(set(result)):
        raise ValueError(f"Duplicate instance IDs in {path}")
    return result


def historic_ids(runs_root, *, current_run):
    """Conservatively exclude IDs selected by any other saved run, even dry runs."""
    runs_root = Path(runs_root)
    current_run = Path(current_run).resolve()
    seen = set()
    if not runs_root.is_dir():
        return seen
    # Each run is a direct child; don't recursively traverse huge git checkouts.
    for run in sorted(runs_root.iterdir()):
        if not run.is_dir() or run.resolve() == current_run:
            continue
        candidate = run / "selected_instances.json"
        if candidate.is_file():
            seen.update(_ids_from_file(candidate))
    return seen


def _all_public_instances(raw_dataset, *, seed, deterministic_subset):
    # Reuse the existing no-oracle loader's public instance model.
    return deterministic_subset(raw_dataset, len(raw_dataset), seed=seed)


def select_excluding_history(raw_dataset, *, count, seed, excluded_ids, deterministic_subset):
    if count < 1:
        raise ValueError("count must be positive")
    candidates = _all_public_instances(raw_dataset, seed=seed, deterministic_subset=deterministic_subset)
    result = [item for item in candidates if item.instance_id not in excluded_ids][:count]
    if len(result) != count:
        raise ValueError(f"Only {len(result)} eligible instances remain; need {count}")
    return result


def reuse_frozen_selection(raw_dataset, *, selected_path, count, deterministic_subset):
    selected_path = Path(selected_path)
    if not selected_path.is_file():
        raise FileNotFoundError(f"Missing frozen selection: {selected_path}. Run a dry run first.")
    wanted_ids = _ids_from_file(selected_path)
    frozen_records = json.loads(selected_path.read_text(encoding="utf-8"))
    if len(wanted_ids) != count:
        raise ValueError(f"Frozen selection has {len(wanted_ids)} IDs, but count is {count}")
    public_items = _all_public_instances(raw_dataset, seed="bugpilot-frozen-selection", deterministic_subset=deterministic_subset)
    lookup = {item.instance_id: item for item in public_items}
    missing = [item_id for item_id in wanted_ids if item_id not in lookup]
    if missing:
        raise ValueError(f"Frozen selection contains IDs absent from the dataset: {missing}")
    # Match the actual base commit as well as the ID when it is available.
    for row in frozen_records:
        actual = lookup[row["instance_id"]]
        for field in ("repo", "base_commit"):
            prior = row.get(field)
            if prior is not None and getattr(actual, field) != prior:
                raise ValueError(f"Frozen {field} mismatch for {row['instance_id']}")
    return [lookup[item_id] for item_id in wanted_ids]
