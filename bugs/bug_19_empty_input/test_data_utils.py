from data_utils import calculate_average

def test_multiple_numbers():
    assert calculate_average([1, 2, 3]) == 2

def test_single_number():
    assert calculate_average([5]) == 5

def test_empty_list_returns_zero():
    assert calculate_average([]) == 0
