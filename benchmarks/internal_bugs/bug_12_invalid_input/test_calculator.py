from calculator import parse_age

def test_valid_numeric_string():
    assert parse_age("25") == 25

def test_zero_string():
    assert parse_age("0") == 0

def test_invalid_string_returns_zero():
    assert parse_age("abc") == 0

def test_none_returns_zero():
    assert parse_age(None) == 0