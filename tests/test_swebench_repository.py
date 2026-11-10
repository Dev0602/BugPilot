import subprocess
from pathlib import Path

import pytest

from evaluation.swebench.current.input import (
    SwebenchInstance,
)
from evaluation.swebench.current.repository import (
    RepositoryPreparationError,
    github_repo_url,
    prepare_repository,
    safe_instance_directory_name,
    verify_repository_state,
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


def create_local_repository(
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

    source_file = (
        repo
        / "calculator.py"
    )

    source_file.write_text(
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
        "first commit",
    )

    first_commit = git(
        repo,
        "rev-parse",
        "HEAD",
    )

    source_file.write_text(
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
        "second commit",
    )

    second_commit = git(
        repo,
        "rev-parse",
        "HEAD",
    )

    return (
        repo,
        first_commit,
        second_commit,
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
            "Addition behaves incorrectly."
        ),
    )


def test_github_repo_url():
    assert (
        github_repo_url(
            "django/django"
        )
        == (
            "https://github.com/"
            "django/django.git"
        )
    )


@pytest.mark.parametrize(
    "repo",
    [
        "",
        "django",
        "owner/repo/extra",
        "../repo",
        "owner/",
    ],
)
def test_invalid_repo_name_rejected(
    repo,
):
    with pytest.raises(
        ValueError
    ):
        github_repo_url(
            repo
        )


def test_instance_directory_is_safe():
    assert (
        safe_instance_directory_name(
            "django__django-123"
        )
        == "django__django-123"
    )

    assert (
        safe_instance_directory_name(
            "owner/repo issue 123"
        )
        == "owner_repo_issue_123"
    )


def test_prepare_repository_checks_out_exact_commit(
    tmp_path,
):
    (
        source_repo,
        first_commit,
        second_commit,
    ) = create_local_repository(
        tmp_path
    )

    instance = make_instance(
        first_commit
    )

    prepared = prepare_repository(
        instance,
        tmp_path / "work",
        clone_url=source_repo,
    )

    prepared_path = Path(
        prepared["path"]
    )

    assert prepared[
        "head_commit"
    ] == first_commit

    assert prepared[
        "head_commit"
    ] != second_commit

    assert prepared[
        "clean"
    ] is True

    assert (
        (
            prepared_path
            / "calculator.py"
        ).read_text(
            encoding="utf-8"
        )
        == (
            "def add(a, b):\n"
            "    return a - b\n"
        )
    )


def test_prepare_repository_replaces_old_workspace(
    tmp_path,
):
    (
        source_repo,
        first_commit,
        _,
    ) = create_local_repository(
        tmp_path
    )

    instance = make_instance(
        first_commit
    )

    work_root = (
        tmp_path
        / "work"
    )

    prepared = prepare_repository(
        instance,
        work_root,
        clone_url=source_repo,
    )

    junk = (
        Path(prepared["path"])
        / "junk.txt"
    )

    junk.write_text(
        "stale workspace",
        encoding="utf-8",
    )

    prepared_again = (
        prepare_repository(
            instance,
            work_root,
            clone_url=source_repo,
        )
    )

    assert not (
        Path(
            prepared_again[
                "path"
            ]
        )
        / "junk.txt"
    ).exists()


def test_verify_repository_rejects_dirty_state(
    tmp_path,
):
    (
        source_repo,
        first_commit,
        _,
    ) = create_local_repository(
        tmp_path
    )

    instance = make_instance(
        first_commit
    )

    prepared = prepare_repository(
        instance,
        tmp_path / "work",
        clone_url=source_repo,
    )

    prepared_path = Path(
        prepared["path"]
    )

    (
        prepared_path
        / "calculator.py"
    ).write_text(
        "modified locally\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RepositoryPreparationError
    ):
        verify_repository_state(
            prepared_path,
            first_commit,
        )


def test_prepare_repository_rejects_wrong_commit(
    tmp_path,
):
    (
        source_repo,
        _,
        _,
    ) = create_local_repository(
        tmp_path
    )

    instance = make_instance(
        "deadbeefdeadbeef"
    )

    with pytest.raises(
        RepositoryPreparationError
    ):
        prepare_repository(
            instance,
            tmp_path / "work",
            clone_url=source_repo,
        )