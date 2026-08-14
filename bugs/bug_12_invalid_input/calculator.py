def parse_age(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0

