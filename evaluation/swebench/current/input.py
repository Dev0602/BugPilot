from dataclasses import dataclass
from typing import Mapping, Any


@dataclass(frozen=True)
class SwebenchInstance:
    """
    Information BugPilot is allowed to see during repair generation.

    Deliberately excluded:
      - patch
      - test_patch
      - FAIL_TO_PASS
      - PASS_TO_PASS
      - gold file names
      - gold function names
    """

    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str


ALLOWED_INPUT_FIELDS = frozenset(
    {
        "instance_id",
        "repo",
        "base_commit",
        "problem_statement",
    }
)


FORBIDDEN_GOLD_FIELDS = frozenset(
    {
        "patch",
        "test_patch",
        "FAIL_TO_PASS",
        "PASS_TO_PASS",
        "gold_patch",
        "gold_file",
        "gold_files",
        "target_file",
        "target_files",
        "function_name",
        "target_function",
    }
)


def prepare_instance(
    raw: Mapping[str, Any],
) -> SwebenchInstance:
    """
    Build the exact benchmark view BugPilot is allowed to use.

    This function intentionally accesses only the four public issue/repository
    fields required for end-to-end repair generation.
    """

    required = (
        "instance_id",
        "repo",
        "base_commit",
        "problem_statement",
    )

    values = {}

    for field in required:
        try:
            value = raw[field]
        except KeyError as exc:
            raise ValueError(
                f"SWE-bench instance is missing required field: {field}"
            ) from exc

        if not isinstance(value, str):
            raise ValueError(
                f"SWE-bench field {field!r} must be a string."
            )

        value = value.strip()

        if not value:
            raise ValueError(
                f"SWE-bench field {field!r} cannot be empty."
            )

        values[field] = value

    return SwebenchInstance(
        **values
    )


def public_instance_dict(
    instance: SwebenchInstance,
):
    """
    Serializable representation safe to save in BugPilot logs.
    """

    return {
        "instance_id": instance.instance_id,
        "repo": instance.repo,
        "base_commit": instance.base_commit,
        "problem_statement": instance.problem_statement,
    }