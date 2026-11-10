import pytest

from evaluation.swebench.current.select_subset import (
    deterministic_subset,
)


def records():
    output = []

    for number in range(
        1,
        11,
    ):
        output.append(
            {
                "instance_id": (
                    f"repo__repo-{number}"
                ),
                "repo": "repo/repo",
                "base_commit": (
                    f"commit-{number}"
                ),
                "problem_statement": (
                    f"Issue {number}"
                ),

                # Must never affect selection.
                "patch": (
                    f"SECRET_PATCH_{number}"
                ),
                "test_patch": (
                    f"SECRET_TEST_{number}"
                ),
                "FAIL_TO_PASS": (
                    f"SECRET_FAIL_{number}"
                ),
                "PASS_TO_PASS": (
                    f"SECRET_PASS_{number}"
                ),
            }
        )

    return output


def test_selection_is_deterministic():
    first = deterministic_subset(
        records(),
        4,
        seed="same-seed",
    )

    second = deterministic_subset(
        records(),
        4,
        seed="same-seed",
    )

    assert [
        item.instance_id
        for item in first
    ] == [
        item.instance_id
        for item in second
    ]


def test_selection_count():
    selected = deterministic_subset(
        records(),
        3,
    )

    assert len(
        selected
    ) == 3


def test_different_seed_can_change_selection():
    first = deterministic_subset(
        records(),
        5,
        seed="seed-a",
    )

    second = deterministic_subset(
        records(),
        5,
        seed="seed-b",
    )

    assert [
        item.instance_id
        for item in first
    ] != [
        item.instance_id
        for item in second
    ]


def test_gold_values_do_not_enter_selected_instances():
    selected = deterministic_subset(
        records(),
        3,
    )

    serialized = str(
        selected
    )

    assert (
        "SECRET_PATCH"
        not in serialized
    )

    assert (
        "SECRET_TEST"
        not in serialized
    )

    assert (
        "SECRET_FAIL"
        not in serialized
    )

    assert (
        "SECRET_PASS"
        not in serialized
    )


def test_invalid_count_rejected():
    with pytest.raises(
        ValueError
    ):
        deterministic_subset(
            records(),
            0,
        )


def test_excessive_count_rejected():
    with pytest.raises(
        ValueError
    ):
        deterministic_subset(
            records(),
            50,
        )   