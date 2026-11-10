import json
import subprocess
from pathlib import Path

import pytest

from evaluation.swebench.current.input import (
    SwebenchInstance,
)
from evaluation.swebench.current.runner import (
    EvaluationRunnerError,
    process_instance,
    run_batch,
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


def create_source_repository(
    tmp_path,
):
    repo = (
        tmp_path
        / "source"
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


def raw_instance(
    commit,
    *,
    instance_id=(
        "example__repo-1"
    ),
):
    return {
        "instance_id": (
            instance_id
        ),
        "repo": (
            "example/repo"
        ),
        "base_commit": (
            commit
        ),
        "problem_statement": (
            "Addition returns "
            "the wrong result."
        ),

        # Gold information deliberately present
        # in the raw record.
        "patch": (
            "SECRET_GOLD_PATCH"
        ),
        "test_patch": (
            "SECRET_TEST_PATCH"
        ),
        "FAIL_TO_PASS": (
            '["secret_failure"]'
        ),
        "PASS_TO_PASS": (
            '["secret_regression"]'
        ),
        "target_file": (
            "secret_file.py"
        ),
        "function_name": (
            "secret_function"
        ),
    }


def repair_solver(
    repository_path,
    problem_statement,
):
    assert (
        problem_statement
        == (
            "Addition returns "
            "the wrong result."
        )
    )

    source = (
        Path(
            repository_path
        )
        / "calculator.py"
    )

    source.write_text(
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8",
    )

    return {
        "diagnosis": (
            "Incorrect arithmetic operator."
        ),
        "file_path": (
            "calculator.py"
        ),
        "function_name": (
            "add"
        ),
    }


def test_process_instance_builds_prediction_without_gold(
    tmp_path,
):
    source_repo, commit = (
        create_source_repository(
            tmp_path
        )
    )

    result = process_instance(
        raw_instance(
            commit
        ),
        tmp_path / "work",
        model_name_or_path=(
            "bugpilot/"
            "claude-haiku-4-5"
        ),
        solver=repair_solver,
        clone_url=source_repo,
    )

    prediction = result[
        "prediction"
    ]

    assert (
        prediction[
            "instance_id"
        ]
        == "example__repo-1"
    )

    assert (
        "return a + b"
        in prediction[
            "model_patch"
        ]
    )

    serialized = str(
        result
    )

    assert (
        "SECRET_GOLD_PATCH"
        not in serialized
    )

    assert (
        "SECRET_TEST_PATCH"
        not in serialized
    )

    assert (
        "secret_file.py"
        not in serialized
    )

    assert (
        "secret_function"
        not in serialized
    )


def test_solver_receives_exact_base_commit(
    tmp_path,
):
    source_repo, commit = (
        create_source_repository(
            tmp_path
        )
    )

    observed = {}

    def solver(
        repository_path,
        problem_statement,
    ):
        observed[
            "head"
        ] = git(
            repository_path,
            "rev-parse",
            "HEAD",
        )

        return repair_solver(
            repository_path,
            problem_statement,
        )

    process_instance(
        raw_instance(
            commit
        ),
        tmp_path / "work",
        model_name_or_path=(
            "bugpilot"
        ),
        solver=solver,
        clone_url=source_repo,
    )

    assert (
        observed["head"]
        == commit
    )


def test_solver_with_no_change_is_rejected(
    tmp_path,
):
    source_repo, commit = (
        create_source_repository(
            tmp_path
        )
    )

    def no_change_solver(
        repository_path,
        problem_statement,
    ):
        return {
            "diagnosis": (
                "No change."
            ),
        }

    with pytest.raises(
        EvaluationRunnerError,
        match=(
            "without producing "
            "a repository patch"
        ),
    ):
        process_instance(
            raw_instance(
                commit
            ),
            tmp_path / "work",
            model_name_or_path=(
                "bugpilot"
            ),
            solver=(
                no_change_solver
            ),
            clone_url=source_repo,
        )


def test_run_batch_writes_jsonl(
    tmp_path,
):
    source_repo, commit = (
        create_source_repository(
            tmp_path
        )
    )

    records = [
        raw_instance(
            commit,
            instance_id=(
                "example__repo-1"
            ),
        ),
        raw_instance(
            commit,
            instance_id=(
                "example__repo-2"
            ),
        ),
    ]

    def clone_resolver(
        instance,
    ):
        assert isinstance(
            instance,
            SwebenchInstance,
        )

        return source_repo

    output = (
        tmp_path
        / "predictions.jsonl"
    )

    result = run_batch(
        records,
        tmp_path / "work",
        output,
        model_name_or_path=(
            "bugpilot/"
            "claude-haiku-4-5"
        ),
        solver=repair_solver,
        clone_url_resolver=(
            clone_resolver
        ),
    )

    assert (
        result["count"]
        == 2
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

    first = json.loads(
        lines[0]
    )

    second = json.loads(
        lines[1]
    )

    assert (
        first[
            "instance_id"
        ]
        == "example__repo-1"
    )

    assert (
        second[
            "instance_id"
        ]
        == "example__repo-2"
    )


def test_run_batch_rejects_duplicate_ids(
    tmp_path,
):
    source_repo, commit = (
        create_source_repository(
            tmp_path
        )
    )

    records = [
        raw_instance(
            commit,
            instance_id=(
                "example__repo-1"
            ),
        ),
        raw_instance(
            commit,
            instance_id=(
                "example__repo-1"
            ),
        ),
    ]

    with pytest.raises(
        EvaluationRunnerError,
        match=(
            "Duplicate SWE-bench "
            "instance ID"
        ),
    ):
        run_batch(
            records,
            tmp_path / "work",
            (
                tmp_path
                / "predictions.jsonl"
            ),
            model_name_or_path=(
                "bugpilot"
            ),
            solver=repair_solver,
            clone_url_resolver=(
                lambda instance: (
                    source_repo
                )
            ),
        )


def test_clone_resolver_sees_only_sanitized_instance(
    tmp_path,
):
    source_repo, commit = (
        create_source_repository(
            tmp_path
        )
    )

    observed = {}

    def clone_resolver(
        instance,
    ):
        observed[
            "instance"
        ] = instance

        return source_repo

    run_batch(
        [
            raw_instance(
                commit
            ),
        ],
        tmp_path / "work",
        (
            tmp_path
            / "predictions.jsonl"
        ),
        model_name_or_path=(
            "bugpilot"
        ),
        solver=repair_solver,
        clone_url_resolver=(
            clone_resolver
        ),
    )

    instance = observed[
        "instance"
    ]

    assert isinstance(
        instance,
        SwebenchInstance,
    )

    assert not hasattr(
        instance,
        "patch",
    )

    assert not hasattr(
        instance,
        "test_patch",
    )

    assert not hasattr(
        instance,
        "FAIL_TO_PASS",
    )

    assert not hasattr(
        instance,
        "PASS_TO_PASS",
    )
