import argparse
import json
from pathlib import Path

from swebench.harness.utils import (
    load_swebench_dataset,
)

from backend.app.config import MODEL
from evaluation.swebench.current.agent_adapter import (
    IssueInvestigationError,
    solve_issue,
)
from evaluation.swebench.current.input import (
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
from evaluation.swebench.current.public_test_config import (
    load_public_test_images,
    preflight_public_test_images,
)
from evaluation.swebench.current.select_subset import (
    deterministic_subset,
)
from evaluation.swebench.current.selection_lock import (
    historic_ids,
    select_excluding_history,
    reuse_frozen_selection,
)


DEFAULT_DATASET = (
    "princeton-nlp/SWE-bench_Lite"
)

DEFAULT_SPLIT = "test"
DEFAULT_SEED = "bugpilot-v1"
DEFAULT_COUNT = 5


def write_json(
    path,
    value,
):
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )



def _record_generation_failure(
    outcome,
    exc,
):
    """
    Add structured failure information to one generation outcome.

    IssueInvestigationError preserves model usage even when BugPilot
    does not produce a repair.
    """

    outcome.update(
        {
            "status": (
                "generation_failed"
            ),
            "error_type": (
                type(exc).__name__
            ),
            "error": str(
                exc
            ),
        }
    )

    if isinstance(
        exc,
        IssueInvestigationError,
    ):
        usage = dict(
            exc.usage
            or {}
        )

        outcome.update(
            {
                "stop_reason": (
                    exc.stop_reason
                ),
                "input_tokens": (
                    usage.get(
                        "input_tokens"
                    )
                ),
                "output_tokens": (
                    usage.get(
                        "output_tokens"
                    )
                ),
                "tool_turns": (
                    usage.get(
                        "tool_turns"
                    )
                ),
                "cost_usd": (
                    usage.get(
                        "cost_usd"
                    )
                ),
                "latency_sec": (
                    usage.get(
                        "latency_sec"
                    )
                ),
                "tool_trace": list(
                    exc.tool_trace
                    or []
                ),
            }
        )

        if (
            exc.details
            is not None
        ):
            outcome[
                "details"
            ] = exc.details

    else:
        outcome[
            "stop_reason"
        ] = (
            "unexpected_error"
        )

    return outcome


def generate(
    *,
    dataset_name,
    split,
    count,
    seed,
    output_dir,
    dry_run=False,
    solver=solve_issue,
    public_test_images=None,
    exclude_previous_selections=False,
    reuse_selected=False,
):
    """
    Generate BugPilot SWE-bench predictions from a deterministic
    no-oracle subset.

    Raw SWE-bench records are sanitized by deterministic_subset()
    before this function's repair loop receives them.

    Every completed instance is checkpointed immediately.
    """

    output_dir = Path(
        output_dir
    ).resolve()

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    work_root = (
        output_dir
        / "workspaces"
    )

    predictions_path = (
        output_dir
        / "predictions.jsonl"
    )

    results_path = (
        output_dir
        / "generation_results.json"
    )

    selected_path = (
        output_dir
        / "selected_instances.json"
    )

    print(
        "Loading dataset:",
        dataset_name,
    )

    raw_dataset = (
        load_swebench_dataset(
            dataset_name,
            split,
        )
    )

    if exclude_previous_selections and reuse_selected:
        raise ValueError("Choose either exclusion or reuse, not both")

    if reuse_selected:
        selected = reuse_frozen_selection(
            raw_dataset,
            selected_path=selected_path,
            count=count,
            deterministic_subset=deterministic_subset,
        )
        print("Reusing frozen issue IDs from:", selected_path)
    elif exclude_previous_selections:
        previous_ids = historic_ids(
            output_dir.parent,
            current_run=output_dir,
        )
        print("Excluding previously selected issue IDs:", len(previous_ids))
        selected = select_excluding_history(
            raw_dataset,
            count=count,
            seed=seed,
            excluded_ids=previous_ids,
            deterministic_subset=deterministic_subset,
        )
    else:
        selected = deterministic_subset(raw_dataset, count, seed=seed)

    public_selected = [
        public_instance_dict(
            instance
        )
        for instance in selected
    ]

    write_json(
        selected_path,
        public_selected,
    )

    print(
        "\nSelected instances:"
    )

    for index, instance in enumerate(
        selected,
        1,
    ):
        print(
            f"{index}. "
            f"{instance.instance_id} "
            f"| {instance.repo}"
        )

    print(
        "\nSelection saved to:",
        selected_path,
    )

    if dry_run:
        print(
            "\nDRY RUN COMPLETE — "
            "no repositories cloned "
            "and no Claude calls made."
        )

        return {
            "selected": (
                public_selected
            ),
            "predictions": [],
            "results": [],
        }

    # Optional public-only verification. Check image availability BEFORE any
    # LLM calls to avoid wasting credits on missing Docker environments.
    images = dict(public_test_images or {})
    selected_images = {
        instance.repo: images[instance.repo]
        for instance in selected if instance.repo in images
    }
    preflight_public_test_images(selected_images)

    predictions = []
    results = []

    model_name = (
        f"bugpilot/{MODEL}"
    )

    for index, instance in enumerate(
        selected,
        1,
    ):
        print(
            "\n"
            + "=" * 80
        )

        print(
            f"[{index}/{len(selected)}] "
            f"{instance.instance_id}"
        )

        print(
            "=" * 80
        )

        outcome = {
            "instance_id": (
                instance.instance_id
            ),
            "repo": (
                instance.repo
            ),
            "base_commit": (
                instance.base_commit
            ),
            "status": (
                "started"
            ),
        }

        try:
            prepared = (
                prepare_repository(
                    instance,
                    work_root,
                )
            )

            repository_path = (
                Path(
                    prepared["path"]
                )
            )

            print(
                "Repository prepared:",
                repository_path,
            )

            print(
                "Starting no-oracle "
                "BugPilot investigation..."
            )

            image = selected_images.get(instance.repo)
            options = (
                {"public_test_image": image, "auto_select_public_tests": True}
                if image else {}
            )
            repair = solver(
                repository_path,
                instance.problem_statement,
                **options,
            )

            model_patch = (
                collect_model_patch(
                    repository_path,
                    expected_commit=(
                        instance.base_commit
                    ),
                )
            )

            if not model_patch.strip():
                raise RuntimeError(
                    "BugPilot completed "
                    "without producing "
                    "a model patch."
                )

            prediction = (
                build_prediction(
                    instance,
                    model_patch,
                    model_name,
                )
            )

            predictions.append(
                prediction
            )

            usage = repair.get(
                "usage",
                {},
            )

            outcome.update(
                {
                    "status": (
                        "prediction_generated"
                    ),
                    "diagnosis": (
                        repair.get(
                            "diagnosis"
                        )
                    ),
                    "file_path": (
                        repair.get(
                            "file_path"
                        )
                    ),
                    "function_name": (
                        repair.get(
                            "function_name"
                        )
                    ),
                    "input_tokens": (
                        usage.get(
                            "input_tokens"
                        )
                    ),
                    "output_tokens": (
                        usage.get(
                            "output_tokens"
                        )
                    ),
                    "tool_turns": (
                        usage.get(
                            "tool_turns"
                        )
                    ),
                    "cost_usd": (
                        usage.get(
                            "cost_usd"
                        )
                    ),
                    "latency_sec": (
                        usage.get(
                            "latency_sec"
                        )
                    ),
                    "patch_chars": len(
                        model_patch
                    ),
                    "public_test_status": repair.get("verification", {})
                    .get("public_tests", {}).get("status", "disabled"),
                    "public_test_targets": repair.get("verification", {})
                    .get("public_tests", {}).get("test_targets", []),
                }
            )

            print(
                "Prediction generated."
            )

            print(
                "Target:",
                outcome[
                    "file_path"
                ],
                "/",
                outcome[
                    "function_name"
                ],
            )

            print(
                "Cost:",
                outcome[
                    "cost_usd"
                ],
            )

        except Exception as exc:
            _record_generation_failure(
                outcome,
                exc,
            )

            print(
                "GENERATION FAILED:"
            )

            print(
                type(
                    exc
                ).__name__,
                str(
                    exc
                ),
            )

            print(
                "Stop reason:",
                outcome.get(
                    "stop_reason"
                ),
            )

            if (
                outcome.get(
                    "cost_usd"
                )
                is not None
            ):
                print(
                    "Recorded cost:",
                    outcome[
                        "cost_usd"
                    ],
                )

        results.append(
            outcome
        )

        # Checkpoint after every instance.
        write_predictions(
            predictions,
            predictions_path,
        )

        write_json(
            results_path,
            results,
        )

        print(
            "Checkpointed:",
            len(predictions),
            "prediction(s)",
        )

    successful = sum(
        result["status"]
        == "prediction_generated"
        for result in results
    )

    failed = (
        len(results)
        - successful
    )

    print(
        "\n"
        + "=" * 80
    )

    print(
        "GENERATION SUMMARY"
    )

    print(
        "=" * 80
    )

    print(
        "Selected:",
        len(selected),
    )

    print(
        "Predictions generated:",
        successful,
    )

    print(
        "Generation failures:",
        failed,
    )

    print(
        "Predictions:",
        predictions_path,
    )

    print(
        "Results:",
        results_path,
    )

    return {
        "selected": (
            public_selected
        ),
        "predictions": (
            predictions
        ),
        "results": (
            results
        ),
    }


def main():
    parser = (
        argparse.ArgumentParser(
            description=(
                "Generate no-oracle "
                "BugPilot SWE-bench "
                "predictions."
            )
        )
    )

    parser.add_argument(
        "--dataset",
        default=(
            DEFAULT_DATASET
        ),
    )

    parser.add_argument(
        "--split",
        default=(
            DEFAULT_SPLIT
        ),
    )

    parser.add_argument(
        "--count",
        type=int,
        default=(
            DEFAULT_COUNT
        ),
    )

    parser.add_argument(
        "--seed",
        default=(
            DEFAULT_SEED
        ),
    )

    parser.add_argument(
        "--output-dir",
        default=(
            "evaluation/swebench/"
            "current/runs/"
            "bugpilot-v1"
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    parser.add_argument(
        "--public-test-images",
        default=None,
        help="Opt-in JSON manifest mapping public repositories to prebuilt offline Docker images",
    )

    selection_mode = parser.add_mutually_exclusive_group()
    selection_mode.add_argument(
        "--exclude-previous-selections",
        action="store_true",
        help="Exclude IDs from all other saved runs, including earlier dry runs",
    )
    selection_mode.add_argument(
        "--reuse-selected",
        action="store_true",
        help="Use exactly the previously saved IDs in this output directory",
    )

    args = parser.parse_args()

    generate(
        dataset_name=(
            args.dataset
        ),
        split=args.split,
        count=args.count,
        seed=args.seed,
        output_dir=(
            args.output_dir
        ),
        dry_run=(
            args.dry_run
        ),
        public_test_images=(
            load_public_test_images(args.public_test_images)
            if args.public_test_images else None
        ),
        exclude_previous_selections=args.exclude_previous_selections,
        reuse_selected=args.reuse_selected,
    )


if __name__ == "__main__":
    main()
