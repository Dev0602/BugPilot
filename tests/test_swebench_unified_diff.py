import subprocess

import pytest

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
        "class Calculator:\n"
        "    def add(self, a, b):\n"
        "        return a - b\n",
        encoding="utf-8",
    )

    second = tmp_path / "helper.py"
    second.write_text(
        "def helper():\n"
        "    return 1\n",
        encoding="utf-8",
    )

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    test_file = tests_dir / "test_calculator.py"
    test_file.write_text(
        "def test_placeholder():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    git(tmp_path, "add", ".")
    git(
        tmp_path,
        "commit",
        "-m",
        "initial",
    )

    return source


def make_diff(
    repo,
    relative_path,
    new_text,
):
    target = repo / relative_path

    target.write_text(
        new_text,
        encoding="utf-8",
    )

    patch = git(
        repo,
        "diff",
        "HEAD",
        "--",
        relative_path,
    ).stdout

    git(
        repo,
        "checkout",
        "--",
        relative_path,
    )

    return patch


def unified_result(
    file_path,
    patch,
):
    return {
        "diagnosis": "Targeted repair",
        "file_path": file_path,
        "repair_type": "unified_diff",
        "unified_diff": patch,
    }


def test_unified_diff_can_add_new_method(
    tmp_path,
):
    source = make_repo(
        tmp_path
    )

    patch = make_diff(
        tmp_path,
        "calculator.py",
        (
            "class Calculator:\n"
            "    def add(self, a, b):\n"
            "        return a + b\n"
            "\n"
            "    def subtract(self, a, b):\n"
            "        return a - b\n"
        ),
    )

    result = adapter.apply_issue_fix(
        tmp_path,
        unified_result(
            "calculator.py",
            patch,
        ),
    )

    assert result["applied"] is True
    assert (
        result["repair_type"]
        == "unified_diff"
    )

    text = source.read_text(
        encoding="utf-8"
    )

    assert "def subtract" in text
    assert "return a + b" in text


def test_unified_diff_rejects_test_file(
    tmp_path,
):
    make_repo(
        tmp_path
    )

    patch = make_diff(
        tmp_path,
        "tests/test_calculator.py",
        (
            "def test_placeholder():\n"
            "    assert False\n"
        ),
    )

    with pytest.raises(
        ValueError
    ):
        adapter.apply_issue_fix(
            tmp_path,
            unified_result(
                "tests/test_calculator.py",
                patch,
            ),
        )


def test_unified_diff_rejects_multiple_files(
    tmp_path,
):
    make_repo(
        tmp_path
    )

    calculator = (
        tmp_path
        / "calculator.py"
    )

    helper = (
        tmp_path
        / "helper.py"
    )

    calculator.write_text(
        "class Calculator:\n"
        "    def add(self, a, b):\n"
        "        return a + b\n",
        encoding="utf-8",
    )

    helper.write_text(
        "def helper():\n"
        "    return 2\n",
        encoding="utf-8",
    )

    patch = git(
        tmp_path,
        "diff",
        "HEAD",
        "--",
    ).stdout

    git(
        tmp_path,
        "checkout",
        "--",
        "calculator.py",
        "helper.py",
    )

    with pytest.raises(
        ValueError,
        match="exactly",
    ):
        adapter.apply_issue_fix(
            tmp_path,
            unified_result(
                "calculator.py",
                patch,
            ),
        )


def test_unified_diff_rejects_new_file(
    tmp_path,
):
    make_repo(
        tmp_path
    )

    patch = """diff --git a/new_module.py b/new_module.py
new file mode 100644
--- /dev/null
+++ b/new_module.py
@@ -0,0 +1,2 @@
+def added():
+    return 1
"""

    with pytest.raises(
        ValueError
    ):
        adapter.apply_issue_fix(
            tmp_path,
            unified_result(
                "new_module.py",
                patch,
            ),
        )


def test_unified_diff_rejects_path_traversal(
    tmp_path,
):
    make_repo(
        tmp_path
    )

    with pytest.raises(
        ValueError
    ):
        adapter.apply_issue_fix(
            tmp_path,
            unified_result(
                "../outside.py",
                (
                    "diff --git a/../outside.py "
                    "b/../outside.py\n"
                ),
            ),
        )


def test_invalid_python_is_rolled_back(
    tmp_path,
):
    source = make_repo(
        tmp_path
    )

    original = source.read_text(
        encoding="utf-8"
    )

    patch = make_diff(
        tmp_path,
        "calculator.py",
        (
            "class Calculator:\n"
            "    def add(self, a, b)\n"
            "        return a + b\n"
        ),
    )

    with pytest.raises(
        ValueError,
        match="invalid Python",
    ):
        adapter.apply_issue_fix(
            tmp_path,
            unified_result(
                "calculator.py",
                patch,
            ),
        )

    assert (
        source.read_text(
            encoding="utf-8"
        )
        == original
    )
