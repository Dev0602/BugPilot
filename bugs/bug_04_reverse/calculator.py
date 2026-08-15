def reverse_words(sentence):
    # Fixed: reverse the order of words, not characters
    return " ".join(sentence.split()[::-1])

