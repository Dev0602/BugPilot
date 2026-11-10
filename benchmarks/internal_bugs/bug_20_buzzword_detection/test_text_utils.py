from text_utils import count_buzzwords

def test_lowercase_match():
    assert count_buzzwords("I am a passionate ninja") == 2

def test_uppercase_not_missed():
    assert count_buzzwords("I am a Passionate NINJA") == 2

def test_no_buzzwords():
    assert count_buzzwords("I write clean code") == 0
