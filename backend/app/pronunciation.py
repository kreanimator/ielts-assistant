"""Pronunciation check: compares the sounds you made with the sounds the words need.

1. A wav2vec2 model recognises the phonemes in the audio (what you said).
2. The CMU dictionary gives the phonemes of the transcribed words (what you meant).
3. A weighted alignment of the two finds the words that came out differently.

Both sides are reduced to one simple English phoneme set, and the comparison is
lenient where accents legitimately differ (British vs American vowels, a dropped
"r" after a vowel, unstressed vowels), so it flags learner errors, not accents.
"""
import json
import re
from pathlib import Path

import numpy as np
import torch
from g2p_en import G2p
from huggingface_hub import snapshot_download
from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC

MODEL = "facebook/wav2vec2-lv-60-espeak-cv-ft"
SAMPLE_RATE = 16000
FILLERS = {"um", "umm", "uh", "er", "erm", "ah", "hmm", "mm"}
# Short common words have natural weak forms ("and" → "an", "of" → "ə"): never flag them.
FUNCTION_WORDS = {
    "a", "an", "and", "the", "of", "to", "for", "at", "in", "on", "from", "as", "or", "but",
    "is", "are", "was", "were", "be", "been", "has", "have", "had", "do", "does", "can", "could",
    "would", "should", "will", "that", "than", "them", "some", "your", "you", "i", "it", "its",
}

# Recognised phonemes (eSpeak symbols) → our simple set. Diphthongs and r-coloured
# vowels become sequences. Anything not listed is kept as it is.
HEARD = {
    "iː": "i", "ᵻ": "ɪ", "e": "eɪ", "eː": "eɪ", "ɛː": "ɛ", "e̞": "ɛ", "a": "æ", "aː": "ɑ",
    "ɑː": "ɑ", "ɒ": "ɑ", "ɔ": "ɑ", "ɔː": "ɑ", "ʌ": "ə", "ɐ": "ə", "ɜ": "ə", "ɜː": "ə",
    "uː": "u", "o": "oʊ", "oː": "oʊ", "əʊ": "oʊ", "eʊ": "oʊ", "oɪ": "ɔɪ",
    "ɚ": "ə ɹ", "əl": "ə l", "ɪɹ": "ɪ ɹ", "ɛɹ": "ɛ ɹ", "ʊɹ": "ʊ ɹ", "ɑːɹ": "ɑ ɹ", "ɔːɹ": "ɑ ɹ",
    "oːɹ": "ɑ ɹ", "iə": "ɪ ə", "eə": "ɛ ə", "ʊə": "ʊ ə", "aɪə": "aɪ ə", "aɪɚ": "aɪ ə ɹ",
    "r": "ɹ", "ʁ": "ɹ", "ɻ": "ɹ", "ɫ": "l", "l̩": "l", "n̩": "n", "ʔ": "t", "ɾ": "t",
}
# CMU dictionary (ARPAbet) → our simple set.
EXPECTED = {
    "AA": "ɑ", "AE": "æ", "AH": "ə", "AO": "ɑ", "AW": "aʊ", "AY": "aɪ", "EH": "ɛ", "ER": "ə ɹ",
    "EY": "eɪ", "IH": "ɪ", "IY": "i", "OW": "oʊ", "OY": "ɔɪ", "UH": "ʊ", "UW": "u",
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "F": "f", "G": "ɡ", "HH": "h", "JH": "dʒ",
    "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ", "P": "p", "R": "ɹ", "S": "s",
    "SH": "ʃ", "T": "t", "TH": "θ", "V": "v", "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ",
}
VOWELS = {"i", "ɪ", "eɪ", "ɛ", "æ", "ɑ", "ə", "u", "ʊ", "oʊ", "aɪ", "aʊ", "ɔɪ"}
# Pairs that native accents mix up too: cheap to swap.
CLOSE = {frozenset(p) for p in [("t", "d"), ("ɪ", "ə"), ("ɛ", "ə"), ("ʊ", "u"), ("ɑ", "ə"), ("ɪ", "i"), ("ɑ", "oʊ")]}


class Phone:
    """One expected sound: which word it belongs to and how much a mistake on it counts."""

    def __init__(self, symbol: str, word: int, weight: float, optional: bool = False):
        self.symbol, self.word, self.weight, self.optional = symbol, word, weight, optional


class PronunciationScorer:
    def __init__(self, device: str):
        path = Path(snapshot_download(MODEL, allow_patterns=["*.json", "*.bin"]))
        vocab = json.loads((path / "vocab.json").read_text())
        self.symbols = {index: symbol for symbol, index in vocab.items()}
        self.extractor = Wav2Vec2FeatureExtractor.from_pretrained(path)
        dtype = torch.float16 if device == "cuda" else torch.float32
        self.model = Wav2Vec2ForCTC.from_pretrained(path, torch_dtype=dtype).to(device).eval()
        self.g2p = G2p()

    def heard(self, audio: np.ndarray) -> list[str]:
        """The phonemes in the audio, in our simple set."""
        inputs = self.extractor(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt").input_values
        with torch.no_grad():
            logits = self.model(inputs.to(self.model.device, self.model.dtype)).logits[0]
        ids = torch.unique_consecutive(logits.argmax(-1)).tolist()  # CTC: merge repeats, drop blanks
        symbols = [self.symbols[i] for i in ids if i > 3]  # 0-3 are <pad> <s> </s> <unk>
        return " ".join(HEARD.get(s, s) for s in symbols).split()

    def pronunciations(self, word: str) -> list[list[str]]:
        """All dictionary pronunciations of a word (ARPAbet), or a guess for unknown words."""
        return self.g2p.cmu[word] if word in self.g2p.cmu else [self.g2p.predict(word)]

    def expected(self, words: list[str], variant: int = 0) -> list[Phone]:
        phones = []
        for index, word in enumerate(words):
            options = self.pronunciations(word)
            for sound in options[min(variant, len(options) - 1)]:
                base, stress = sound.rstrip("012"), sound[-1]
                for symbol in EXPECTED.get(base, "").split():
                    # Unstressed vowels vary a lot even between native speakers.
                    weight = 0.3 if symbol in VOWELS and stress == "0" else 1.0
                    phones.append(Phone(symbol, index, weight))
        # Non-rhotic accents drop "r" when no vowel follows (British "car", "hard").
        for this, after in zip(phones, phones[1:] + [None]):
            if this.symbol == "ɹ" and (after is None or after.symbol not in VOWELS):
                this.optional = True
        return phones

    def best_variant(self, word: str, heard: list[str], alignment: "Alignment", index: int):
        """If another dictionary pronunciation fits what was heard better, use it for this word."""
        for variant in range(1, len(self.pronunciations(word))):
            phones = self.expected([word], variant)
            if not phones:
                continue
            other = align(phones, heard)
            if other.errors[0] < alignment.errors[index]:
                alignment.errors[index] = other.errors[0]
                alignment.mistakes[index] = other.mistakes[0]

    def score(self, audio: np.ndarray, text: str) -> dict:
        """Returns the overall score, the words that came out differently, and the sound
        mistakes that repeat (e.g. "θ" said as "s" three times)."""
        words = [w for w in re.findall(r"[a-z']+", text.lower()) if w not in FILLERS]
        expected = self.expected(words)
        if len(expected) < 4:
            return {"score": None, "words": [], "sounds": []}
        alignment = align(expected, self.heard(audio))

        unclear, sounds = [], {}
        for i, word in enumerate(words):
            if alignment.mistakes[i]:
                self.best_variant(word, alignment.heard[i], alignment, i)
            mistakes = alignment.mistakes[i]
            if word in FUNCTION_WORDS or not mistakes:
                continue
            unclear.append({
                "word": word,
                "expected": "".join(p.symbol for p in expected if p.word == i),
                "heard": "".join(alignment.heard[i]),
            })
            for mistake in mistakes:
                sounds[mistake] = sounds.get(mistake, 0) + 1
        total = sum(p.weight for p in expected)
        return {
            "score": round(max(0.0, 1 - sum(alignment.errors) / total), 2),
            "words": unclear[:6],
            "sounds": [
                {"expected": e, "heard": h, "count": n}  # heard "" means the sound was left out
                for (e, h), n in sorted(sounds.items(), key=lambda kv: -kv[1])
            ][:4],
        }


def cost(phone: Phone, symbol: str) -> float:
    if phone.symbol == symbol:
        return 0.0
    if frozenset((phone.symbol, symbol)) in CLOSE:
        return 0.3 * phone.weight
    return phone.weight


class Alignment:
    """Per word: the error cost, the heard phonemes, and clear mistakes as (expected, heard) pairs."""

    def __init__(self, words: int):
        self.errors = [0.0] * words
        self.heard = [[] for _ in range(words)]
        self.mistakes = [[] for _ in range(words)]


def align(expected: list[Phone], heard: list[str]) -> Alignment:
    """Weighted edit distance between the expected and heard phonemes."""
    n, m = len(expected), len(heard)
    INSERT = 0.5  # an extra sound costs less than a wrong or missing one
    table = np.zeros((n + 1, m + 1))
    table[1:, 0] = np.cumsum([0 if p.optional else p.weight for p in expected])
    table[0, 1:] = np.arange(1, m + 1) * INSERT
    for i in range(1, n + 1):
        p = expected[i - 1]
        delete = 0 if p.optional else p.weight
        for j in range(1, m + 1):
            table[i, j] = min(
                table[i - 1, j - 1] + cost(p, heard[j - 1]),
                table[i - 1, j] + delete,
                table[i, j - 1] + INSERT,
            )

    result = Alignment(max(p.word for p in expected) + 1)
    i, j = n, m
    while i > 0 or j > 0:
        p = expected[i - 1] if i > 0 else expected[0]
        if i > 0 and j > 0 and table[i, j] == table[i - 1, j - 1] + cost(p, heard[j - 1]):
            c = cost(p, heard[j - 1])
            result.errors[p.word] += c
            result.heard[p.word].insert(0, heard[j - 1])
            if c >= 1:  # a clear mistake on a stressed sound
                result.mistakes[p.word].insert(0, (p.symbol, heard[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and table[i, j] == table[i - 1, j] + (0 if p.optional else p.weight):
            if not p.optional:
                result.errors[p.word] += p.weight
                if p.weight >= 1:
                    result.mistakes[p.word].insert(0, (p.symbol, ""))
            i -= 1
        else:
            # An extra sound: count it against the word it sits in, but not as a mistake.
            word = expected[i - 1].word if i > 0 else 0
            result.errors[word] += INSERT
            result.heard[word].insert(0, heard[j - 1])
            j -= 1
    return result
