"""Text to speech with Kokoro-82M.

Kokoro's own pipeline falls back to eSpeak-ng (GPL) for words missing from its
dictionary. To keep every dependency permissive, we use Kokoro's model directly
and fall back to the CMU dictionary through g2p_en instead (it also guesses
words it has never seen, like names).
"""
import sys
import types

import numpy as np
import torch
from huggingface_hub import hf_hub_download

# Kokoro imports misaki.espeak when it loads, even though we never use it.
# This empty module stands in for it, so the eSpeak packages are not needed.
sys.modules.setdefault("misaki.espeak", types.ModuleType("misaki.espeak"))

from g2p_en import G2p  # noqa: E402
from kokoro import KModel  # noqa: E402
from misaki import en  # noqa: E402

REPO = "hexgrad/Kokoro-82M"
SAMPLE_RATE = 24000
MAX_PHONEMES = 510  # the model's input limit; our sentences are much shorter

# CMU dictionary sounds (ARPAbet) → the phoneme symbols Kokoro was trained on.
ARPABET = {
    "AA": "ɑ", "AE": "æ", "AH": "ʌ", "AO": "ɔ", "AW": "W", "AY": "I", "EH": "ɛ", "ER": "ɜɹ",
    "EY": "A", "IH": "ɪ", "IY": "i", "OW": "O", "OY": "Y", "UH": "ʊ", "UW": "u",
    "B": "b", "CH": "ʧ", "D": "d", "DH": "ð", "F": "f", "G": "ɡ", "HH": "h", "JH": "ʤ",
    "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ", "P": "p", "R": "ɹ", "S": "s",
    "SH": "ʃ", "T": "t", "TH": "θ", "V": "v", "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ",
}
UNSTRESSED = {"AH": "ə", "ER": "əɹ"}
BRITISH = {"ɑ": "ɑː", "ɔ": "ɔː", "i": "iː", "u": "uː", "ɜɹ": "ɜː", "əɹ": "ə", "O": "Q"}
STRESS = {"1": "ˈ", "2": "ˌ"}


class CmuFallback:
    """Pronounces words that misaki's dictionary does not have."""

    def __init__(self, british: bool):
        self.british = british
        self.g2p = G2p()

    def __call__(self, token):
        word = token.text.lower()
        arpabet = self.g2p.cmu[word][0] if word in self.g2p.cmu else self.g2p.predict(word)
        phonemes = ""
        for sound in arpabet:
            base, stress = sound.rstrip("012"), sound[-1]
            symbol = UNSTRESSED.get(base) if stress == "0" and base in UNSTRESSED else ARPABET.get(base, "")
            if self.british:
                symbol = BRITISH.get(symbol, symbol)
            phonemes += STRESS.get(stress, "") + symbol
        return phonemes, 1


class Speaker:
    def __init__(self, device: str):
        self.model = KModel(repo_id=REPO).to(device).eval()
        self.g2p = {  # the first letter of a voice name is its accent
            "a": en.G2P(trf=False, british=False, fallback=CmuFallback(british=False), unk=""),
            "b": en.G2P(trf=False, british=True, fallback=CmuFallback(british=True), unk=""),
        }
        self.voices = {}

    def voice(self, name: str) -> torch.Tensor:
        if name not in self.voices:
            path = hf_hub_download(REPO, f"voices/{name}.pt")
            self.voices[name] = torch.load(path, weights_only=True).to(self.model.device)
        return self.voices[name]

    def speak(self, text: str, voice: str) -> np.ndarray:
        """Returns float32 mono audio at 24 kHz."""
        phonemes, _ = self.g2p[voice[0]](text)
        phonemes = phonemes[:MAX_PHONEMES]
        if not phonemes:
            return np.zeros(0, dtype=np.float32)
        style = self.voice(voice)[len(phonemes) - 1]
        with torch.no_grad():
            audio = self.model(phonemes, style, speed=1)
        return audio.cpu().numpy()
