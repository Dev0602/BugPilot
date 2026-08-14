from calculator import add_item

def test_add_item_does_not_leak_across_calls():
    result1 = add_item("apple")
    result2 = add_item("banana")
    # if the bug exists, result2 will incorrectly contain "apple" too
    assert result2 == ["banana"]