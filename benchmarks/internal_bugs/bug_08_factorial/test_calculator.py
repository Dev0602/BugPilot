from calculator import factorial

def test_factorial_zero():
    assert factorial(0) == 1

def test_factorial_five():
    assert factorial(5) == 120
