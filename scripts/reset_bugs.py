import ast
import textwrap

from backend.app.tools import read_file, write_file


# Deterministic intentionally-broken versions used before every benchmark run.
#
# Important:
# - Do not include comments that reveal the correct fix.
# - Every entry must produce at least one failing test.
# - Test files are never modified by this reset script.
BROKEN_VERSIONS = {
    "benchmarks/internal_bugs/bug_01_calculator": {
        "filename": "calculator.py",
        "code": """\
def add(a, b):
    return a - b
""",
    },

    "benchmarks/internal_bugs/bug_02_discount": {
        "filename": "calculator.py",
        "code": """\
def apply_discount(price, discount_percent):
    return price - (price * discount_percent)
""",
    },

    "benchmarks/internal_bugs/bug_03_grade": {
        "filename": "calculator.py",
        "code": """\
def passing_grade(score):
    if score > 60:
        return True
    return False
""",
    },

    "benchmarks/internal_bugs/bug_04_reverse": {
        "filename": "calculator.py",
        "code": """\
def reverse_words(sentence):
    return sentence[::-1]
""",
    },

    "benchmarks/internal_bugs/bug_05_sum_range": {
        "filename": "calculator.py",
        "code": """\
def sum_up_to(n):
    total = 0
    for i in range(n):
        total += i
    return total
""",
    },

    "benchmarks/internal_bugs/bug_06_mutable_default": {
        "filename": "calculator.py",
        "code": """\
def add_item(item, items=[]):
    items.append(item)
    return items
""",
    },

    "benchmarks/internal_bugs/bug_07_word_count": {
        "filename": "calculator.py",
        "code": """\
def count_words(text):
    words = text.split()
    counts = {}

    for word in words:
        counts[word] = counts.get(word, 0) + 1

    return counts
""",
    },

    "benchmarks/internal_bugs/bug_08_factorial": {
        "filename": "calculator.py",
        "code": """\
def factorial(n):
    if n == 1:
        return 1

    return n * factorial(n - 1)
""",
    },

    # bug_09 is handled separately below because ats_scorer.py is a much
    # larger real application file and we only want to reset _exact_match.
    "benchmarks/internal_bugs/bug_10_prime_checker": {
        "filename": "calculator.py",
        "code": """\
def is_prime(n):
    if n < 2:
        return False

    for i in range(2, int(n ** 0.5)):
        if n % i == 0:
            return False

    return True
""",
    },

    "benchmarks/internal_bugs/bug_11_safe_divide": {
        "filename": "calculator.py",
        "code": """\
def safe_divide(a, b):
    return a / b
""",
    },

    "benchmarks/internal_bugs/bug_12_invalid_input": {
        "filename": "calculator.py",
        "code": """\
def parse_age(value):
    return int(value)
""",
    },

    "benchmarks/internal_bugs/bug_13_list_index": {
        "filename": "list_utils.py",
        "code": """\
def get_last_element(items):
    return items[len(items)]
""",
    },

    "benchmarks/internal_bugs/bug_14_dictionary": {
        "filename": "user_utils.py",
        "code": """\
def get_user_email(user_dict):
    return user_dict["email"]
""",
    },

    "benchmarks/internal_bugs/bug_15_sets": {
        "filename": "set_utils.py",
        "code": """\
def find_common(list1, list2):
    return set(list1) | set(list2)
""",
    },

    "benchmarks/internal_bugs/bug_16_string_processing": {
        "filename": "string_utils.py",
        "code": """\
def normalize_username(name):
    return name.lower()
""",
    },

    "benchmarks/internal_bugs/bug_17_recursion": {
        "filename": "factorial.py",
        "code": """\
def factorial(n):
    if n == 1:
        return 1

    return n * factorial(n - 1)
""",
    },

    "benchmarks/internal_bugs/bug_18_algorithm": {
        "filename": "search.py",
        "code": """\
def binary_search(arr, target):
    low = 0
    high = len(arr) - 1

    while low < high:
        mid = (low + high) // 2

        if arr[mid] == target:
            return mid

        if arr[mid] < target:
            low = mid + 1
        else:
            high = mid

    return -1
""",
    },

    "benchmarks/internal_bugs/bug_19_empty_input": {
        "filename": "data_utils.py",
        "code": """\
def calculate_average(numbers):
    return sum(numbers) / len(numbers)
""",
    },

    "benchmarks/internal_bugs/bug_20_buzzword_detection": {
        "filename": "text_utils.py",
        "code": """\
BUZZWORDS = [
    "synergy",
    "passionate",
    "ninja",
    "rockstar",
    "guru",
]


def count_buzzwords(text):
    return sum(
        1
        for word in BUZZWORDS
        if word in text
    )
""",
    },
}


BUG_09_BROKEN_FUNCTION = """\
def _exact_match(keyword, resume_lower):
    kw = keyword.lower().strip()
    return kw in resume_lower
"""


class _FunctionLocator(ast.NodeVisitor):
    """Locate top-level Python functions by name."""

    def __init__(self, function_name):
        self.function_name = function_name
        self.matches = []

    def visit_FunctionDef(self, node):
        if node.name == self.function_name:
            self.matches.append(node)

        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        if node.name == self.function_name:
            self.matches.append(node)

        self.generic_visit(node)


def _replace_function(
    full_code,
    function_name,
    replacement_code,
):
    """
    Replace one function using AST source locations.

    Used only by the deterministic benchmark reset process.
    """

    try:
        tree = ast.parse(full_code)
    except SyntaxError as exc:
        raise RuntimeError(
            f"Cannot reset '{function_name}': source file has "
            f"invalid syntax: {exc}"
        ) from exc

    locator = _FunctionLocator(function_name)
    locator.visit(tree)

    if len(locator.matches) != 1:
        raise RuntimeError(
            f"Expected exactly one '{function_name}' function, "
            f"found {len(locator.matches)}."
        )

    target = locator.matches[0]

    if target.end_lineno is None:
        raise RuntimeError(
            f"Python did not provide an end line for '{function_name}'."
        )

    replacement_code = textwrap.dedent(
        replacement_code
    ).strip("\n")

    try:
        ast.parse(replacement_code)
    except SyntaxError as exc:
        raise RuntimeError(
            f"Broken benchmark replacement for '{function_name}' "
            f"is invalid Python: {exc}"
        ) from exc

    lines = full_code.splitlines(keepends=True)

    start = target.lineno - 1
    end = target.end_lineno

    replacement = replacement_code.rstrip() + "\n\n"

    updated = (
        "".join(lines[:start])
        + replacement
        + "".join(lines[end:])
    )

    try:
        ast.parse(updated)
    except SyntaxError as exc:
        raise RuntimeError(
            f"Resetting '{function_name}' produced invalid "
            f"Python: {exc}"
        ) from exc

    return updated


def reset_bug_09():
    """
    Reset the ATS regression without replacing the rest of the real
    ats_scorer.py application.
    """

    bug_dir = "benchmarks/internal_bugs/bug_09_ats_exact_match"
    filename = "ats_scorer.py"

    current_code = read_file(
        filename,
        bug_dir,
    )

    broken_code = _replace_function(
        current_code,
        "_exact_match",
        BUG_09_BROKEN_FUNCTION,
    )

    write_file(
        filename,
        broken_code,
        bug_dir,
    )

    print(
        "Reset benchmarks/internal_bugs/bug_09_ats_exact_match"
    )


def reset_standard_bugs():
    for bug_dir, info in BROKEN_VERSIONS.items():
        write_file(
            info["filename"],
            textwrap.dedent(info["code"]),
            bug_dir,
        )

        print(f"Reset {bug_dir}")


def reset_all():
    print("\nResetting BugPilot internal benchmark...\n")

    reset_standard_bugs()
    reset_bug_09()

    expected_count = 20
    actual_count = len(BROKEN_VERSIONS) + 1

    if actual_count != expected_count:
        raise RuntimeError(
            f"Benchmark reset expected {expected_count} bugs, "
            f"but reset {actual_count}."
        )

    print(
        f"\n✓ Reset complete: "
        f"{actual_count}/{expected_count} benchmark bugs prepared."
    )


if __name__ == "__main__":
    reset_all()