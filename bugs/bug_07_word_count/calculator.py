def count_words(text):
    words = text.split()
    counts = {}
    for w in words:
        w_lower = w.lower()
        counts[w_lower] = counts.get(w_lower, 0) + 1
    return counts

