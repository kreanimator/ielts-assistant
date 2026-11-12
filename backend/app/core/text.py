"""Text measures shared by the modules: word counts, vocabulary variety, dictionary words."""
import re

import numpy as np

# A word as IELTS counts it: anything between spaces that has a letter or a digit
# ("well-known", "don't" and "2024" are one word each; a lone "-" is none).
WORD = re.compile(r"\S*[A-Za-z0-9]\S*")


def word_count(text: str) -> int:
    """The same count as the word counter in the app (frontend/lib/modules/writing/words.dart)."""
    return len(WORD.findall(text))


def moving_type_token_ratio(tokens: list[str], window: int = 40) -> float:
    """Share of different words, averaged over 40-word windows (fair across answer lengths)."""
    if len(tokens) < window:
        return len(set(tokens)) / max(1, len(tokens))
    return float(np.mean([len(set(tokens[i:i + window])) / window for i in range(len(tokens) - window + 1)]))


_dictionary = None


def dictionary() -> set[str]:
    """The words of the CMU dictionary, lower case (about 120,000, with many names)."""
    global _dictionary
    if _dictionary is None:
        from nltk.corpus import cmudict  # installed with the pronunciation model (g2p_en)
        _dictionary = set(cmudict.words())
    return _dictionary


def unknown_words(text: str) -> list[str]:
    """Words that are not in the dictionary, in order and without repeats: possible
    misspellings (or rare words and names, which the dictionary may lack)."""
    words = dictionary()
    seen, unknown = set(), []
    for w in re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text):
        low = w.lower()
        # Capitalised words are skipped: names, and (sadly) misspellings at a sentence start.
        if low not in seen and low not in words and low.split("'")[0] not in words and not w[0].isupper():
            unknown.append(w)
        seen.add(low)
    return unknown


def readability(text: str) -> float:
    """The share of the words that are English words (the CMU dictionary)."""
    words = re.findall(r"[A-Za-z']+", text)
    if not words:
        return 0.0
    return sum(w.lower().strip("'") in dictionary() for w in words) / len(words)
