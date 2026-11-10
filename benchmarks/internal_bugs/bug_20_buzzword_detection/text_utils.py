BUZZWORDS = [
    "synergy",
    "passionate",
    "ninja",
    "rockstar",
    "guru",
]


def count_buzzwords(text):
    return sum(
        1
        for word in BUZZWORDS
        if word in text
    )
