def get_last_element(items):
    # bug: wrong index, off by one
    if len(items) == 0:
        return None
    return items[len(items) - 1]

