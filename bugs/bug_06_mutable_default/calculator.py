def add_item(item, items=None):
    # fix: use None as default and create new list each call
    if items is None:
        items = []
    items.append(item)
    return items

