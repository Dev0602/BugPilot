BUZZWORDS = ['synergy', 'passionate', 'ninja', 'rockstar', 'guru']

def count_buzzwords(text):
    # bug fix: lowercase text before checking for buzzwords
    text = text.lower()
    return sum(1 for word in BUZZWORDS if word in text)

