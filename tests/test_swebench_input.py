import pytest

from evaluation.swebench.current.input import (
    ALLOWED_INPUT_FIELDS,
    FORBIDDEN_GOLD_FIELDS,
    SwebenchInstance,
    prepare_instance,
    public_instance_dict,
)


class AccessTrackingMapping:
    """
    Mapping that records every field the code attempts to access.

    If prepare_instance ever starts reading gold fields, this test exposes it.
    """

    def __init__(
        self,
        data,
    ):
        self.data = data
        self.accessed = []

    def __getitem__(
        self,
        key,
    ):
        self.accessed.append(
            key
        )

        return self.data[key]


def valid_raw_instance():
    return {
        "instance_id": (
            "django__django-12345"
        ),
        "repo": (
            "django/django"
        ),
        "base_commit": (
            "abc123def456"
        ),
        "problem_statement": (
            "A user-visible bug occurs "
            "when processing a request."
        ),

        # These values intentionally contain obvious secrets.
        # The production input function must never read them.
        "patch": (
            "SECRET_GOLD_PATCH"
        ),
        "test_patch": (
            "SECRET_TEST_PATCH"
        ),
        "FAIL_TO_PASS": (
            '["secret_test"]'
        ),
        "PASS_TO_PASS": (
            '["secret_regression_test"]'
        ),
        "target_file": (
            "secret_gold_file.py"
        ),
        "function_name": (
            "secret_gold_function"
        ),
    }


def test_prepare_instance_uses_only_public_fields():
    raw = AccessTrackingMapping(
        valid_raw_instance()
    )

    instance = prepare_instance(
        raw
    )

    assert isinstance(
        instance,
        SwebenchInstance,
    )

    assert set(
        raw.accessed
    ) == set(
        ALLOWED_INPUT_FIELDS
    )

    assert not (
        set(raw.accessed)
        & FORBIDDEN_GOLD_FIELDS
    )


def test_gold_values_do_not_enter_instance():
    raw = valid_raw_instance()

    instance = prepare_instance(
        raw
    )

    serialized = str(
        public_instance_dict(
            instance
        )
    )

    assert (
        "SECRET_GOLD_PATCH"
        not in serialized
    )

    assert (
        "SECRET_TEST_PATCH"
        not in serialized
    )

    assert (
        "secret_gold_file.py"
        not in serialized
    )

    assert (
        "secret_gold_function"
        not in serialized
    )


def test_public_instance_contains_exactly_allowed_fields():
    instance = prepare_instance(
        valid_raw_instance()
    )

    output = public_instance_dict(
        instance
    )

    assert set(
        output
    ) == set(
        ALLOWED_INPUT_FIELDS
    )


@pytest.mark.parametrize(
    "missing_field",
    [
        "instance_id",
        "repo",
        "base_commit",
        "problem_statement",
    ],
)
def test_required_fields_are_enforced(
    missing_field,
):
    raw = valid_raw_instance()

    del raw[
        missing_field
    ]

    with pytest.raises(
        ValueError
    ):
        prepare_instance(
            raw
        )


def test_empty_required_field_is_rejected():
    raw = valid_raw_instance()

    raw[
        "problem_statement"
    ] = "   "

    with pytest.raises(
        ValueError
    ):
        prepare_instance(
            raw
        )