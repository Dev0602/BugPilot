from backend.app.agent import TOOLS
from evaluation.swebench.current.agent_adapter import (
    _validate_submit_fix,
)


def get_submit_fix_tool():
    for tool in TOOLS:
        if tool.get("name") == "submit_fix":
            return tool

    raise AssertionError(
        "submit_fix tool not found"
    )


def test_submit_fix_schema_has_two_repair_types():
    tool = get_submit_fix_tool()

    properties = tool[
        "input_schema"
    ][
        "properties"
    ]

    assert (
        properties[
            "repair_type"
        ][
            "enum"
        ]
        == [
            "replace_function",
            "unified_diff",
        ]
    )

    assert (
        "unified_diff"
        in properties
    )


def test_replace_function_protocol_is_valid():
    valid, error = _validate_submit_fix(
        {
            "diagnosis": "Wrong operator",
            "file_path": "calculator.py",
            "repair_type": (
                "replace_function"
            ),
            "function_name": "add",
            "fixed_function_code": (
                "def add(a, b):\n"
                "    return a + b\n"
            ),
        }
    )

    assert valid is True
    assert error is None


def test_legacy_function_protocol_still_works():
    valid, error = _validate_submit_fix(
        {
            "diagnosis": "Wrong operator",
            "file_path": "calculator.py",
            "function_name": "add",
            "fixed_function_code": (
                "def add(a, b):\n"
                "    return a + b\n"
            ),
        }
    )

    assert valid is True
    assert error is None


def test_unified_diff_protocol_is_valid():
    valid, error = _validate_submit_fix(
        {
            "diagnosis": (
                "A new method is required."
            ),
            "file_path": "calculator.py",
            "repair_type": "unified_diff",
            "unified_diff": (
                "diff --git "
                "a/calculator.py "
                "b/calculator.py\n"
                "--- a/calculator.py\n"
                "+++ b/calculator.py\n"
                "@@ -1 +1 @@\n"
                "-x = 1\n"
                "+x = 2\n"
            ),
        }
    )

    assert valid is True
    assert error is None


def test_unified_diff_rejects_function_fields():
    valid, error = _validate_submit_fix(
        {
            "diagnosis": "Mixed formats",
            "file_path": "calculator.py",
            "repair_type": "unified_diff",
            "unified_diff": (
                "diff --git "
                "a/calculator.py "
                "b/calculator.py\n"
            ),
            "function_name": "add",
        }
    )

    assert valid is False

    assert (
        "Do not provide"
        in error
    )


def test_replace_function_rejects_unified_diff():
    valid, error = _validate_submit_fix(
        {
            "diagnosis": "Mixed formats",
            "file_path": "calculator.py",
            "repair_type": (
                "replace_function"
            ),
            "function_name": "add",
            "fixed_function_code": (
                "def add(a, b):\n"
                "    return a + b\n"
            ),
            "unified_diff": "not allowed",
        }
    )

    assert valid is False

    assert (
        "Do not provide"
        in error
    )
