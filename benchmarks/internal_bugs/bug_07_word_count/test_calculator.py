from calculator import count_words

def test_case_insensitive_count():
    result = count_words("The the THE")
    assert result == {"the": 3}
