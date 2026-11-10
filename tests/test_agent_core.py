import pytest

from backend.app.agent import (
    _repair_fingerprint,
    apply_function_patch,
    parse_coverage,
)


def test_parse_coverage_extracts_total():
    logs = """
Name                 Stmts   Miss  Cover
----------------------------------------
calculator.py            2      0   100%
test_calculator.py       3      0   100%
----------------------------------------
TOTAL                    5      0   100%
"""

    assert parse_coverage(logs) == 100


def test_parse_coverage_returns_none_when_missing():
    assert parse_coverage("no coverage data here") is None


def test_patch_top_level_function():
    source = """
def add(a, b):
    return a - b
"""

    replacement = """
def add(a, b):
    return a + b
"""

    patched = apply_function_patch(
        source,
        "add",
        replacement,
    )

    assert "return a + b" in patched

    compile(
        patched,
        "<patched>",
        "exec",
    )


def test_patch_class_method():
    source = """
class Calculator:
    def add(self, a, b):
        return a - b
"""

    replacement = """
def add(self, a, b):
    return a + b
"""

    patched = apply_function_patch(
        source,
        "Calculator.add",
        replacement,
    )

    assert "return a + b" in patched

    compile(
        patched,
        "<patched>",
        "exec",
    )


def test_patch_async_function():
    source = """
async def fetch_value():
    return "wrong"
"""

    replacement = """
async def fetch_value():
    return "correct"
"""

    patched = apply_function_patch(
        source,
        "fetch_value",
        replacement,
    )

    assert 'return "correct"' in patched

    compile(
        patched,
        "<patched>",
        "exec",
    )


def test_existing_decorator_is_preserved():
    source = """
class Calculator:
    @staticmethod
    def multiply(a, b):
        return a + b
"""

    replacement = """
def multiply(a, b):
    return a * b
"""

    patched = apply_function_patch(
        source,
        "Calculator.multiply",
        replacement,
    )

    assert "@staticmethod" in patched
    assert "return a * b" in patched

    compile(
        patched,
        "<patched>",
        "exec",
    )


def test_replacement_decorator_is_rejected():
    source = """
class Calculator:
    @staticmethod
    def multiply(a, b):
        return a + b
"""

    replacement = """
@staticmethod
def multiply(a, b):
    return a * b
"""

    with pytest.raises(
        ValueError,
        match="Do not include decorators",
    ):
        apply_function_patch(
            source,
            "Calculator.multiply",
            replacement,
        )


def test_ambiguous_function_name_is_rejected():
    source = """
class First:
    def run(self):
        return 1


class Second:
    def run(self):
        return 2
"""

    replacement = """
def run(self):
    return 3
"""

    with pytest.raises(
        ValueError,
        match="ambiguous",
    ):
        apply_function_patch(
            source,
            "run",
            replacement,
        )


def test_missing_function_is_rejected():
    source = """
def add(a, b):
    return a + b
"""

    replacement = """
def subtract(a, b):
    return a - b
"""

    with pytest.raises(
        ValueError,
        match="Could not find function",
    ):
        apply_function_patch(
            source,
            "subtract",
            replacement,
        )


def test_wrong_replacement_function_name_is_rejected():
    source = """
def add(a, b):
    return a - b
"""

    replacement = """
def subtract(a, b):
    return a - b
"""

    with pytest.raises(
        ValueError,
        match="Replacement function is named",
    ):
        apply_function_patch(
            source,
            "add",
            replacement,
        )


def test_repair_fingerprint_normalizes_diagnosis_whitespace():
    first = {
        "diagnosis": "Wrong   operator in ADD function",
        "file_path": "calculator.py",
        "function_name": "add",
        "fixed_function_code": """
def add(a, b):
    return a + b
""",
    }

    second = {
        "diagnosis": "wrong operator in add function",
        "file_path": "calculator.py",
        "function_name": "add",
        "fixed_function_code": """
def add(a, b):
    return a + b
""",
    }

    assert (
        _repair_fingerprint(first)
        == _repair_fingerprint(second)
    )


def test_different_patch_has_different_fingerprint():
    first = {
        "diagnosis": "wrong operator",
        "file_path": "calculator.py",
        "function_name": "add",
        "fixed_function_code": """
def add(a, b):
    return a + b
""",
    }

    second = {
        "diagnosis": "wrong operator",
        "file_path": "calculator.py",
        "function_name": "add",
        "fixed_function_code": """
def add(a, b):
    return a * b
""",
    }

    assert (
        _repair_fingerprint(first)
        != _repair_fingerprint(second)
    )