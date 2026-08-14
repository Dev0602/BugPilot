from list_utils import get_last_element

def test_multiple_elements():
    assert get_last_element([1, 2, 3]) == 3

def test_single_element():
    assert get_last_element([10]) == 10

def test_empty_list_returns_none():
    assert get_last_element([]) is None
