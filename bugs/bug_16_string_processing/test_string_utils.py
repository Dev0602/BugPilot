from string_utils import normalize_username

def test_normal_string():
    assert normalize_username("JohnDoe") == "johndoe"

def test_leading_trailing_spaces():
    assert normalize_username("  JohnDoe  ") == "johndoe"

def test_uppercase():
    assert normalize_username("ALICE") == "alice"

def test_empty_string():
    assert normalize_username("") == ""
