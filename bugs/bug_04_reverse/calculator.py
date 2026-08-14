def reverse_words(sentence):
    # bug: reverses the whole string instead of the word order
    return " ".join(sentence.split()[::-1])

