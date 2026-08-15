BUZZWORDS = ['synergy', 'passionate', 'ninja', 'rockstar', 'guru']

def count_buzzwords(text):
    # bug: doesn't lowercase text, so "Passionate" or "NINJA" won't match
    text_lower = text.lower()
    return sum(1 for word in BUZZWORDS if word in text_lower)

