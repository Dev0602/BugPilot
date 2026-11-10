import json
import random
from dataclasses import dataclass
from pathlib import Path

import pytest

from evaluation.swebench.current.selection_lock import (
    historic_ids,
    reuse_frozen_selection,
    select_excluding_history,
)


@dataclass(frozen=True)
class Issue:
    instance_id: str
    repo: str = "sympy/sympy"
    base_commit: str = "abc123"


def subset(rows, count, *, seed):
    rows = list(rows)
    random.Random(seed).shuffle(rows)
    return rows[:count]


def test_prior_selections_include_dry_runs_and_skip_current(tmp_path):
    runs = tmp_path / "runs"
    for name, ids in (("v1", ["a", "b"]), ("v3", ["c"]), ("v4_dry", ["d"])):
        folder = runs / name
        folder.mkdir(parents=True)
        (folder / "selected_instances.json").write_text(json.dumps([{"instance_id": i} for i in ids]))
    current = runs / "next"
    current.mkdir()
    (current / "selected_instances.json").write_text('[{"instance_id":"z"}]')
    # Nested repository contents must not influence saved benchmark selection.
    nested = runs / "v3" / "workspaces" / "repo"
    nested.mkdir(parents=True)
    (nested / "selected_instances.json").write_text('[{"instance_id":"extra"}]')
    assert historic_ids(runs, current_run=current) == {"a", "b", "c", "d"}


def test_select_excluding_history_is_deterministic():
    items = [Issue(str(i)) for i in range(40)]
    params = dict(count=10, seed="frozen-seed", excluded_ids={"1", "4", "8", "23"}, deterministic_subset=subset)
    first = select_excluding_history(items, **params)
    second = select_excluding_history(items, **params)
    assert first == second
    assert len(first) == 10
    assert not {x.instance_id for x in first} & params["excluded_ids"]


def test_reuse_ignores_new_seed_and_preserves_order(tmp_path):
    path = tmp_path / "selected_instances.json"
    path.write_text('[{"instance_id":"3"},{"instance_id":"1"}]')
    selected = reuse_frozen_selection([Issue(str(i)) for i in range(10)], selected_path=path, count=2, deterministic_subset=subset)
    assert [x.instance_id for x in selected] == ["3", "1"]


def test_reuse_missing_file_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        reuse_frozen_selection([], selected_path=tmp_path / "missing.json", count=1, deterministic_subset=subset)


def test_reuse_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "selected_instances.json"
    path.write_text('[{"instance_id":"3"},{"instance_id":"3"}]')
    with pytest.raises(ValueError, match="Duplicate"):
        reuse_frozen_selection([Issue("3")], selected_path=path, count=2, deterministic_subset=subset)


def test_reuse_rejects_mismatch_count_or_missing_id(tmp_path):
    path = tmp_path / "selected_instances.json"
    path.write_text('[{"instance_id":"missing"}]')
    with pytest.raises(ValueError, match="count"):
        reuse_frozen_selection([Issue("3")], selected_path=path, count=2, deterministic_subset=subset)
    with pytest.raises(ValueError, match="absent"):
        reuse_frozen_selection([Issue("3")], selected_path=path, count=1, deterministic_subset=subset)


def test_invalid_previous_selection_fails_closed(tmp_path):
    runs = tmp_path / "runs"
    bad = runs / "v3"
    bad.mkdir(parents=True)
    (bad / "selected_instances.json").write_text('[{"nonsense":"a"}]')
    with pytest.raises(ValueError, match="Invalid"):
        historic_ids(runs, current_run=runs / "current")


def test_insufficient_eligible_issues_fails():
    with pytest.raises(ValueError, match="eligible"):
        select_excluding_history([Issue("a"), Issue("b")], count=2, seed="seed", excluded_ids={"a"}, deterministic_subset=subset)
