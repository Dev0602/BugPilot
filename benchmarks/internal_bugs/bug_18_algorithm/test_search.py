from search import binary_search

def test_target_at_beginning():
    assert binary_search([1, 2, 3, 4, 5], 1) == 0

def test_target_at_middle():
    assert binary_search([1, 2, 3, 4, 5], 3) == 2

def test_target_at_end():
    assert binary_search([1, 2, 3, 4, 5], 5) == 4

def test_target_missing():
    assert binary_search([1, 2, 3, 4, 5], 10) == -1

def test_single_element_found():
    assert binary_search([7], 7) == 0
