def factorial(n):
    # bug: wrong base case
    if n <= 1:
        return 1
    return n * factorial(n - 1)

