import subprocess

from evaluation.swebench.current import agent_adapter as adapter


def git(repo, *args):
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )


def make_repo(tmp_path):
    git(tmp_path, "init")

    git(
        tmp_path,
        "config",
        "user.email",
        "bugpilot-test@example.com",
    )

    git(
        tmp_path,
        "config",
        "user.name",
        "BugPilot Test",
    )

    source = tmp_path / "calculator.py"

    source.write_text(
        "def add(a, b):\n"
        "    return a - b\n",
        encoding="utf-8",
    )

    git(
        tmp_path,
        "add",
        "calculator.py",
    )

    git(
        tmp_path,
        "commit",
        "-m",
        "initial",
    )

    return source


def test_verify_issue_patch_accepts_small_valid_patch(
    tmp_path,
):
    source = make_repo(
        tmp_path
    )

    source.write_text(
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8",
    )

    result = adapter.verify_issue_patch(
        tmp_path,
        {
            "file_path": "calculator.py",
        },
    )

    assert result["passed"] is True

    assert (
        result["reason"]
        == "local_safety_checks_passed"
    )

    assert result["changed_files"] == [
        "calculator.py"
    ]

    assert result["changed_lines"] > 0


def test_verify_issue_patch_rejects_syntax_error(
    tmp_path,
):
    source = make_repo(
        tmp_path
    )

    source.write_text(
        "def add(:\n"
        "    return 1\n",
        encoding="utf-8",
    )

    result = adapter.verify_issue_patch(
        tmp_path,
        {
            "file_path": "calculator.py",
        },
    )

    assert result["passed"] is False

    assert (
        result["reason"]
        == "syntax_error"
    )


def test_verify_issue_patch_rejects_extra_changed_file(
    tmp_path,
):
    source = make_repo(
        tmp_path
    )

    notes = tmp_path / "notes.txt"

    notes.write_text(
        "original\n",
        encoding="utf-8",
    )

    git(
        tmp_path,
        "add",
        "notes.txt",
    )

    git(
        tmp_path,
        "commit",
        "-m",
        "add notes",
    )

    source.write_text(
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8",
    )

    notes.write_text(
        "changed\n",
        encoding="utf-8",
    )

    result = adapter.verify_issue_patch(
        tmp_path,
        {
            "file_path": "calculator.py",
        },
    )

    assert result["passed"] is False

    assert (
        result["reason"]
        == "unexpected_files_changed"
    )
