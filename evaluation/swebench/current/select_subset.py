import hashlib

from evaluation.swebench.current.input import (
    prepare_instance,
)


def deterministic_subset(
    raw_instances,
    count,
    *,
    seed="bugpilot-v1",
):
    """
    Select a deterministic subset without using gold patch/test fields.

    Selection depends only on the public instance_id and the supplied seed.
    """

    if not isinstance(
        count,
        int,
    ) or count < 1:
        raise ValueError(
            "count must be a positive integer."
        )

    prepared = [
        prepare_instance(
            raw
        )
        for raw in raw_instances
    ]

    if count > len(
        prepared
    ):
        raise ValueError(
            "count exceeds the number "
            "of available instances."
        )

    def score(
        instance,
    ):
        material = (
            f"{seed}:"
            f"{instance.instance_id}"
        ).encode(
            "utf-8"
        )

        return hashlib.sha256(
            material
        ).hexdigest()

    return sorted(
        prepared,
        key=score,
    )[:count]