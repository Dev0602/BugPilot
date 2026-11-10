from calculator import apply_discount

def test_discount():
    assert apply_discount(100, 20) == 80
