"""IELTS band arithmetic shared by every module."""
import math


def round_band(value: float) -> float:
    """IELTS rounding: to the nearest half band, .25 and .75 round up."""
    return math.floor(value * 2 + 0.5) / 2
