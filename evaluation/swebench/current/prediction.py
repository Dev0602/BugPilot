import json
from pathlib import Path

from evaluation.swebench.current.input import (
    SwebenchInstance,
)
from evaluation.swebench.current.repository import (
    RepositoryPreparationError,
    run_git,
)


PREDICTION_FIELDS = frozenset(
    {
        "instance_id",
        "model_name_or_path",
        "model_patch",
    }
)


class PredictionError(
    RuntimeError
):
    pass


def collect_model_patch(
    repository_path,
    *,
    expected_commit=None,
):
    """
    Return all tracked working-tree/index changes as a git patch.

    The patch is generated relative to HEAD.

    Untracked files are rejected instead of silently omitted. BugPilot's
    current repair mechanism edits existing source functions, so silently
    losing newly-created files would make an evaluation misleading.
    """

    repository_path = Path(
        repository_path
    ).resolve()

    if not repository_path.exists():
        raise PredictionError(
            f"Repository does not exist: {repository_path}"
        )

    try:
        head = run_git(
            [
                "rev-parse",
                "HEAD",
            ],
            cwd=repository_path,
        )

    except RepositoryPreparationError as exc:
        raise PredictionError(
            "Could not determine repository HEAD."
        ) from exc

    if expected_commit is not None:
        try:
            expected = run_git(
                [
                    "rev-parse",
                    expected_commit,
                ],
                cwd=repository_path,
            )

        except RepositoryPreparationError as exc:
            raise PredictionError(
                "Could not resolve expected base commit."
            ) from exc

        if head != expected:
            raise PredictionError(
                "Repository HEAD changed during repair generation. "
                f"HEAD={head}, expected={expected}"
            )

    status = run_git(
        [
            "status",
            "--porcelain",
            "--untracked-files=all",
        ],
        cwd=repository_path,
    )

    untracked = []

    for line in status.splitlines():
        if line.startswith(
            "?? "
        ):
            untracked.append(
                line[3:]
            )

    if untracked:
        raise PredictionError(
            "BugPilot created untracked files, but the current "
            "SWE-bench prediction exporter only supports edits "
            "to tracked files. Untracked files: "
            + ", ".join(
                untracked
            )
        )

    try:
        patch = run_git(
            [
                "diff",
                "--binary",
                "--no-ext-diff",
                "HEAD",
                "--",
            ],
            cwd=repository_path,
        )

    except RepositoryPreparationError as exc:
        raise PredictionError(
            "Could not generate model patch."
        ) from exc

    if patch:
        patch += "\n"

    return patch


def build_prediction(
    instance,
    model_patch,
    model_name_or_path,
):
    """
    Build one prediction in the format accepted by SWE-bench.
    """

    if not isinstance(
        instance,
        SwebenchInstance,
    ):
        raise TypeError(
            "build_prediction requires a SwebenchInstance."
        )

    if not isinstance(
        model_patch,
        str,
    ):
        raise ValueError(
            "model_patch must be a string."
        )

    if not isinstance(
        model_name_or_path,
        str,
    ):
        raise ValueError(
            "model_name_or_path must be a string."
        )

    model_name_or_path = (
        model_name_or_path.strip()
    )

    if not model_name_or_path:
        raise ValueError(
            "model_name_or_path cannot be empty."
        )

    return {
        "instance_id": (
            instance.instance_id
        ),
        "model_name_or_path": (
            model_name_or_path
        ),
        "model_patch": (
            model_patch
        ),
    }


def validate_prediction(
    prediction,
):
    """
    Validate the exact prediction object written to disk.
    """

    if not isinstance(
        prediction,
        dict,
    ):
        raise ValueError(
            "Prediction must be a dictionary."
        )

    if set(
        prediction
    ) != set(
        PREDICTION_FIELDS
    ):
        raise ValueError(
            "Prediction must contain exactly: "
            "instance_id, model_name_or_path, model_patch."
        )

    instance_id = prediction[
        "instance_id"
    ]

    model_name = prediction[
        "model_name_or_path"
    ]

    model_patch = prediction[
        "model_patch"
    ]

    if not isinstance(
        instance_id,
        str,
    ) or not instance_id.strip():
        raise ValueError(
            "instance_id must be a non-empty string."
        )

    if not isinstance(
        model_name,
        str,
    ) or not model_name.strip():
        raise ValueError(
            "model_name_or_path must be a non-empty string."
        )

    if not isinstance(
        model_patch,
        str,
    ):
        raise ValueError(
            "model_patch must be a string."
        )

    return prediction


def write_predictions(
    predictions,
    output_path,
):
    """
    Write SWE-bench predictions as either JSON or JSONL.

    .json:
        JSON list of prediction objects.

    .jsonl:
        One prediction object per line.
    """

    predictions = list(
        predictions
    )

    seen = set()

    for prediction in predictions:
        validate_prediction(
            prediction
        )

        instance_id = prediction[
            "instance_id"
        ]

        if instance_id in seen:
            raise ValueError(
                "Duplicate prediction for instance: "
                f"{instance_id}"
            )

        seen.add(
            instance_id
        )

    output_path = Path(
        output_path
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    suffix = (
        output_path.suffix.lower()
    )

    if suffix == ".json":
        output_path.write_text(
            json.dumps(
                predictions,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    elif suffix == ".jsonl":
        lines = [
            json.dumps(
                prediction,
                ensure_ascii=False,
            )
            for prediction in predictions
        ]

        content = (
            "\n".join(
                lines
            )
        )

        if content:
            content += "\n"

        output_path.write_text(
            content,
            encoding="utf-8",
        )

    else:
        raise ValueError(
            "Prediction output path must end in "
            ".json or .jsonl."
        )

    return output_path