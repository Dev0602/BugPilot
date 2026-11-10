from calculator import is_prime

def test_prime_numbers():
    assert is_prime(7) == True
    assert is_prime(13) == True

def test_composite_numbers():
    assert is_prime(8) == False
    assert is_prime(9) == False

def test_edge_cases_below_two():
    assert is_prime(1) == False
    assert is_prime(0) == False
    assert is_prime(-5) == False