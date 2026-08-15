def calculate_average(numbers):
    # bug: crashes on empty list instead of returning 0
    if not numbers:
        return 0
    return sum(numbers) / len(numbers)

