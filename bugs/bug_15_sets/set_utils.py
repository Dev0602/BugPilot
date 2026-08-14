def find_common(list1, list2):
    # bug: uses union instead of intersection
    return set(list1) & set(list2)

