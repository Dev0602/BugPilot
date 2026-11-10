from user_utils import get_user_email

def test_existing_key():
    assert get_user_email({"email": "a@b.com"}) == "a@b.com"

def test_missing_key_returns_none():
    assert get_user_email({"name": "Alice"}) is None

def test_empty_dict_returns_none():
    assert get_user_email({}) is None
