def count_words(text):
    words = text.split()
    counts = {}

    for word in words:
        counts[word] = counts.get(word, 0) + 1

    return counts
