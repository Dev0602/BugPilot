from tools import write_file

# The original broken version of each bug, so we can reset before every run
BROKEN_VERSIONS = {
    "bugs/bug_01_calculator": {
        "filename": "calculator.py",
        "code": "def add(a, b):\n    return a - b  # bug: should be a + b\n",
    },
    "bugs/bug_02_discount": {
        "filename": "calculator.py",
        "code": "def apply_discount(price, discount_percent):\n    # bug: forgot to divide discount_percent by 100\n    return price - (price * discount_percent)\n",
    },
    "bugs/bug_03_grade": {
        "filename": "calculator.py",
        "code": "def passing_grade(score):\n    # bug: should be >= 60, not > 60\n    if score > 60:\n        return True\n    return False\n",
    },
    "bugs/bug_04_reverse": {
        "filename": "calculator.py",
        "code": "def reverse_words(sentence):\n    # bug: reverses the whole string instead of the word order\n    return sentence[::-1]\n",
    },
    "bugs/bug_05_sum_range": {
        "filename": "calculator.py",
        "code": "def sum_up_to(n):\n    total = 0\n    for i in range(n):\n        total += i\n    return total\n",
    },
    "bugs/bug_06_mutable_default": {
        "filename": "calculator.py",
        "code": "def add_item(item, items=[]):\n    # bug: mutable default argument persists across calls\n    items.append(item)\n    return items\n",
    },
    "bugs/bug_07_word_count": {
        "filename": "calculator.py",
        "code": "def count_words(text):\n    words = text.split()\n    counts = {}\n    for w in words:\n        counts[w] = counts.get(w, 0) + 1\n    return counts\n",
    },
    "bugs/bug_08_factorial": {
        "filename": "calculator.py",
        "code": "def factorial(n):\n    if n == 1:\n        return 1\n    return n * factorial(n - 1)\n",
    },
    "bugs/bug_11_safe_divide": {
        "filename": "calculator.py",
        "code": "def safe_divide(a, b):\n    return a / b\n",
    },
    "bugs/bug_12_invalid_input": {
        "filename": "calculator.py",
        "code": "def parse_age(value):\n    return int(value)\n",
    },
    "bugs/bug_13_list_index": {
        "filename": "list_utils.py",
        "code": "def get_last_element(items):\n    # bug: wrong index, off by one\n    return items[len(items)]\n",
    },
    "bugs/bug_14_dictionary": {
        "filename": "user_utils.py",
        "code": "def get_user_email(user_dict):\n    # bug: assumes key always exists\n    return user_dict[\"email\"]\n",
    },
    "bugs/bug_15_sets": {
        "filename": "set_utils.py",
        "code": "def find_common(list1, list2):\n    # bug: uses union instead of intersection\n    return set(list1) | set(list2)\n",
    },
    "bugs/bug_16_string_processing": {
        "filename": "string_utils.py",
        "code": "def normalize_username(name):\n    # bug: forgets to strip whitespace\n    return name.lower()\n",
    },
    "bugs/bug_17_recursion": {
        "filename": "factorial.py",
        "code": "def factorial(n):\n    # bug: wrong base case\n    if n == 1:\n        return 1\n    return n * factorial(n - 1)\n",
    },
    "bugs/bug_18_algorithm": {
        "filename": "search.py",
        "code": "def binary_search(arr, target):\n    low, high = 0, len(arr) - 1\n    while low < high:\n        mid = (low + high) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            low = mid + 1\n        else:\n            high = mid\n    return -1\n",
    },
    "bugs/bug_19_empty_input": {
        "filename": "data_utils.py",
        "code": "def calculate_average(numbers):\n    # bug: crashes on empty list instead of returning 0\n    return sum(numbers) / len(numbers)\n",
    },
    "bugs/bug_20_buzzword_detection": {
        "filename": "text_utils.py",
        "code": "BUZZWORDS = ['synergy', 'passionate', 'ninja', 'rockstar', 'guru']\n\ndef count_buzzwords(text):\n    # bug: doesn't lowercase text, so \"Passionate\" or \"NINJA\" won't match\n    return sum(1 for word in BUZZWORDS if word in text)\n",
    },
}


def reset_all():
    for bug_dir, info in BROKEN_VERSIONS.items():
        write_file(info["filename"], info["code"], bug_dir)
        print(f"Reset {bug_dir}")


if __name__ == "__main__":
    reset_all()