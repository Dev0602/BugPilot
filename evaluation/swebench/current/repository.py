import re
import shutil
import subprocess
from pathlib import Path

from evaluation.swebench.current.input import (
    SwebenchInstance,
)


DEFAULT_GIT_TIMEOUT_SEC = 600


class RepositoryPreparationError(
    RuntimeError
):
    pass


def github_repo_url(
    repo,
):
    """
    Convert a SWE-bench repository name such as
    'django/django' into its canonical GitHub clone URL.
    """

    if not isinstance(
        repo,
        str,
    ):
        raise ValueError(
            "Repository name must be a string."
        )

    repo = repo.strip()

    if not re.fullmatch(
        r"[A-Za-z0-9_.-]+/"
        r"[A-Za-z0-9_.-]+",
        repo,
    ):
        raise ValueError(
            "Repository must use owner/name format."
        )

    owner, name = repo.split(
        "/",
        1,
    )

    if owner in {".", ".."} or name in {".", ".."}:
        raise ValueError(
            "Repository owner and name cannot be '.' or '..'."
        )

    return (
        f"https://github.com/{repo}.git"
    )


def safe_instance_directory_name(
    instance_id,
):
    """
    Convert a SWE-bench instance ID into a filesystem-safe name.
    """

    if not isinstance(
        instance_id,
        str,
    ):
        raise ValueError(
            "instance_id must be a string."
        )

    value = re.sub(
        r"[^A-Za-z0-9_.-]+",
        "_",
        instance_id.strip(),
    )

    value = value.strip(
        "._"
    )

    if not value:
        raise ValueError(
            "instance_id produced an empty directory name."
        )

    return value


def run_git(
    args,
    *,
    cwd=None,
    timeout=DEFAULT_GIT_TIMEOUT_SEC,
):
    """
    Execute one git command and return stdout.

    Raises RepositoryPreparationError with useful diagnostics
    instead of exposing raw CalledProcessError objects.
    """

    command = [
        "git",
        *args,
    ]

    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    except subprocess.TimeoutExpired as exc:
        raise RepositoryPreparationError(
            "Git command timed out: "
            + " ".join(command)
        ) from exc

    except OSError as exc:
        raise RepositoryPreparationError(
            "Git could not be executed."
        ) from exc

    if result.returncode != 0:
        stderr = (
            result.stderr.strip()
            or result.stdout.strip()
            or "no git error output"
        )

        raise RepositoryPreparationError(
            "Git command failed:\n"
            + " ".join(command)
            + "\n"
            + stderr
        )

    return result.stdout.strip()


def verify_repository_state(
    repository_path,
    expected_commit,
):
    """
    Ensure the prepared repository is exactly at the requested
    SWE-bench base commit and contains no local modifications.
    """

    repository_path = Path(
        repository_path
    ).resolve()

    head = run_git(
        [
            "rev-parse",
            "HEAD",
        ],
        cwd=repository_path,
    )

    expected = run_git(
        [
            "rev-parse",
            expected_commit,
        ],
        cwd=repository_path,
    )

    if head != expected:
        raise RepositoryPreparationError(
            "Repository HEAD does not match "
            "the requested SWE-bench base commit. "
            f"HEAD={head}, expected={expected}"
        )

    status = run_git(
        [
            "status",
            "--porcelain",
        ],
        cwd=repository_path,
    )

    if status:
        raise RepositoryPreparationError(
            "Prepared repository is not clean:\n"
            + status
        )

    return {
        "head_commit": head,
        "clean": True,
    }


def prepare_repository(
    instance,
    work_root,
    *,
    clone_url=None,
):
    """
    Clone a repository and check out exactly instance.base_commit.

    The function accepts only SwebenchInstance, which means gold patch
    data is not available to this layer.

    clone_url exists mainly for testing with local temporary repositories.
    Production callers normally omit it and use the GitHub URL generated
    from instance.repo.
    """

    if not isinstance(
        instance,
        SwebenchInstance,
    ):
        raise TypeError(
            "prepare_repository requires a SwebenchInstance."
        )

    work_root = Path(
        work_root
    ).resolve()

    work_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = (
        work_root
        / safe_instance_directory_name(
            instance.instance_id
        )
    )

    if destination.exists():
        shutil.rmtree(
            destination
        )

    source_url = (
        clone_url
        if clone_url is not None
        else github_repo_url(
            instance.repo
        )
    )

    run_git(
        [
            "clone",
            "--no-checkout",
            str(source_url),
            str(destination),
        ]
    )

    try:
        run_git(
            [
                "checkout",
                "--detach",
                instance.base_commit,
            ],
            cwd=destination,
        )

        verification = (
            verify_repository_state(
                destination,
                instance.base_commit,
            )
        )

    except Exception:
        shutil.rmtree(
            destination,
            ignore_errors=True,
        )

        raise

    return {
        "path": destination,
        "repo": instance.repo,
        "instance_id": (
            instance.instance_id
        ),
        "base_commit": (
            instance.base_commit
        ),
        "head_commit": (
            verification[
                "head_commit"
            ]
        ),
        "clean": True,
    }