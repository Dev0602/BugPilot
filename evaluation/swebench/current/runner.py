from pathlib import Path

from evaluation.swebench.current.agent_adapter import (
    solve_issue,
)
from evaluation.swebench.current.input import (
    SwebenchInstance,
    prepare_instance,
    public_instance_dict,
)
from evaluation.swebench.current.prediction import (
    build_prediction,
    collect_model_patch,
    write_predictions,
)
from evaluation.swebench.current.repository import (
    prepare_repository,
)


class EvaluationRunnerError(
    RuntimeError
):
    pass


def _process_prepared_instance(
    instance,
    work_root,
    *,
    model_name_or_path,
    solver,
    clone_url=None,
):
    """
    Process one already-sanitized SWE-bench instance.

    The solver receives only:
      - repository path
      - public problem statement

    It never receives the original raw SWE-bench record.
    """

    if not isinstance(
        instance,
        SwebenchInstance,
    ):
        raise TypeError(
            "instance must be "
            "a SwebenchInstance."
        )

    prepared = prepare_repository(
        instance,
        work_root,
        clone_url=clone_url,
    )

    repository_path = Path(
        prepared["path"]
    ).resolve()

    repair_result = solver(
        repository_path,
        instance.problem_statement,
    )

    model_patch = collect_model_patch(
        repository_path,
        expected_commit=(
            instance.base_commit
        ),
    )

    if not model_patch.strip():
        raise EvaluationRunnerError(
            "Solver completed without "
            "producing a repository patch."
        )

    prediction = build_prediction(
        instance,
        model_patch,
        model_name_or_path,
    )

    return {
        "instance": (
            public_instance_dict(
                instance
            )
        ),
        "repository": {
            "path": str(
                repository_path
            ),
            "head_commit": (
                prepared[
                    "head_commit"
                ]
            ),
            "clean_before_repair": (
                prepared[
                    "clean"
                ]
            ),
        },
        "repair": repair_result,
        "prediction": prediction,
    }


def process_instance(
    raw_instance,
    work_root,
    *,
    model_name_or_path,
    solver=solve_issue,
    clone_url=None,
):
    """
    Sanitize and process one raw SWE-bench record.

    prepare_instance() is the only component that sees the raw
    benchmark dictionary. Gold fields are discarded before repository
    preparation or agent execution.
    """

    instance = prepare_instance(
        raw_instance
    )

    return _process_prepared_instance(
        instance,
        work_root,
        model_name_or_path=(
            model_name_or_path
        ),
        solver=solver,
        clone_url=clone_url,
    )


def run_batch(
    raw_instances,
    work_root,
    output_path,
    *,
    model_name_or_path,
    solver=solve_issue,
    clone_url_resolver=None,
):
    """
    Process multiple SWE-bench records and write predictions.

    clone_url_resolver is intended for controlled tests or offline
    evaluation. It receives only the sanitized SwebenchInstance.

    Production runs normally leave it as None so the canonical GitHub
    repository URL is used.
    """

    instances = []
    seen_instance_ids = set()

    for raw_instance in raw_instances:
        instance = prepare_instance(
            raw_instance
        )

        if (
            instance.instance_id
            in seen_instance_ids
        ):
            raise EvaluationRunnerError(
                "Duplicate SWE-bench "
                "instance ID: "
                f"{instance.instance_id}"
            )

        seen_instance_ids.add(
            instance.instance_id
        )

        instances.append(
            instance
        )

    predictions = []
    results = []

    for instance in instances:
        clone_url = None

        if (
            clone_url_resolver
            is not None
        ):
            clone_url = (
                clone_url_resolver(
                    instance
                )
            )

        result = (
            _process_prepared_instance(
                instance,
                work_root,
                model_name_or_path=(
                    model_name_or_path
                ),
                solver=solver,
                clone_url=clone_url,
            )
        )

        predictions.append(
            result[
                "prediction"
            ]
        )

        results.append(
            result
        )

    output = write_predictions(
        predictions,
        output_path,
    )

    return {
        "output_path": str(
            output
        ),
        "count": len(
            predictions
        ),
        "predictions": (
            predictions
        ),
        "results": results,
    }
