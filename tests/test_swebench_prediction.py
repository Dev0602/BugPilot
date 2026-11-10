import json
import subprocess
from pathlib import Path

import pytest

from evaluation.swebench.current.input import (
    SwebenchInstance,
)
from evaluation.swebench.current.prediction import (
    PREDICTION_FIELDS,
    PredictionError,
    build_prediction,
    collect_model_patch,
    write_predictions,
)


def git(
    repo,
    *args,
):
    result = subprocess.run(
        [
            "git",
            *args,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout.strip()


def create_repo(
    tmp_path,
):
    repo = (
        tmp_path
        / "repo"
    )

    repo.mkdir()

    git(
        repo,
        "init",
    )

    git(
        repo,
        "config",
        "user.email",
        "bugpilot@example.com",
    )

    git(
        repo,
        "config",
        "user.name",
        "BugPilot Test",
    )

    (
        repo
        / "calculator.py"
    ).write_text(
        "def add(a, b):\n"
        "    return a - b\n",
        encoding="utf-8",
    )

    git(
        repo,
        "add",
        "calculator.py",
    )

    git(
        repo,
        "commit",
        "-m",
        "base",
    )

    commit = git(
        repo,
        "rev-parse",
        "HEAD",
    )

    return (
        repo,
        commit,
    )


def make_instance(
    base_commit,
):
    return SwebenchInstance(
        instance_id=(
            "example__repo-123"
        ),
        repo="example/repo",
        base_commit=base_commit,
        problem_statement=(
            "Addition returns the wrong result."
        ),
    )


def test_clean_repository_has_empty_patch(
    tmp_path,
):
    repo, commit = create_repo(
        tmp_path
    )

    patch = collect_model_patch(
        repo,
        expected_commit=commit,
    )

    assert patch == ""


def test_modified_file_produces_git_patch(
    tmp_path,
):
    repo, commit = create_repo(
        tmp_path
    )

    (
        repo
        / "calculator.py"
    ).write_text(
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8",
    )

    patch = collect_model_patch(
        repo,
        expected_commit=commit,
    )

    assert (
        "diff --git "
        "a/calculator.py "
        "b/calculator.py"
        in patch
    )

    assert (
        "-    return a - b"
        in patch
    )

    assert (
        "+    return a + b"
        in patch
    )


def test_staged_change_is_included(
    tmp_path,
):
    repo, commit = create_repo(
        tmp_path
    )

    (
        repo
        / "calculator.py"
    ).write_text(
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8",
    )

    git(
        repo,
        "add",
        "calculator.py",
    )

    patch = collect_model_patch(
        repo,
        expected_commit=commit,
    )

    assert (
        "+    return a + b"
        in patch
    )


def test_untracked_file_is_rejected(
    tmp_path,
):
    repo, commit = create_repo(
        tmp_path
    )

    (
        repo
        / "new_file.py"
    ).write_text(
        "print('new')\n",
        encoding="utf-8",
    )

    with pytest.raises(
        PredictionError
    ):
        collect_model_patch(
            repo,
            expected_commit=commit,
        )


def test_changed_head_is_rejected(
    tmp_path,
):
    repo, first_commit = create_repo(
        tmp_path
    )

    (
        repo
        / "calculator.py"
    ).write_text(
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8",
    )

    git(
        repo,
        "add",
        "calculator.py",
    )

    git(
        repo,
        "commit",
        "-m",
        "unexpected commit",
    )

    with pytest.raises(
        PredictionError
    ):
        collect_model_patch(
            repo,
            expected_commit=first_commit,
        )


def test_build_prediction_has_exact_format(
    tmp_path,
):
    _, commit = create_repo(
        tmp_path
    )

    instance = make_instance(
        commit
    )

    prediction = build_prediction(
        instance,
        "diff --git a/a.py b/a.py\n",
        "bugpilot/claude-haiku-4-5",
    )

    assert set(
        prediction
    ) == set(
        PREDICTION_FIELDS
    )

    assert (
        prediction[
            "instance_id"
        ]
        == instance.instance_id
    )

    assert (
        prediction[
            "model_name_or_path"
        ]
        == "bugpilot/claude-haiku-4-5"
    )


def test_write_predictions_json(
    tmp_path,
):
    prediction = {
        "instance_id": "repo__repo-1",
        "model_name_or_path": "bugpilot",
        "model_patch": "diff content\n",
    }

    output = write_predictions(
        [
            prediction,
        ],
        tmp_path / "predictions.json",
    )

    loaded = json.loads(
        output.read_text(
            encoding="utf-8"
        )
    )

    assert loaded == [
        prediction,
    ]


def test_write_predictions_jsonl(
    tmp_path,
):
    predictions = [
        {
            "instance_id": "repo__repo-1",
            "model_name_or_path": "bugpilot",
            "model_patch": "patch one\n",
        },
        {
            "instance_id": "repo__repo-2",
            "model_name_or_path": "bugpilot",
            "model_patch": "patch two\n",
        },
    ]

    output = write_predictions(
        predictions,
        tmp_path / "predictions.jsonl",
    )

    lines = (
        output.read_text(
            encoding="utf-8"
        )
        .splitlines()
    )

    assert len(
        lines
    ) == 2

    assert json.loads(
        lines[0]
    ) == predictions[0]

    assert json.loads(
        lines[1]
    ) == predictions[1]