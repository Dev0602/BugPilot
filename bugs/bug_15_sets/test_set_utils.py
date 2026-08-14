from set_utils import find_common

def test_common_elements():
    assert find_common([1, 2, 3], [2, 3, 4]) == {2, 3}

def test_with_duplicates():
    assert find_common([1, 1, 2], [1, 2, 2]) == {1, 2}

def test_no_overlap():
    assert find_common([1, 2], [3, 4]) == set()
