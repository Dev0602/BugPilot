from calculator import safe_divide

def test_normal_division():
    assert safe_divide(10, 2) == 5

def test_decimal_division():
    assert safe_divide(5, 2) == 2.5

def test_zero_division():
    assert safe_divide(10, 0) == 0