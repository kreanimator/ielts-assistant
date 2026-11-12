"""IELTS band arithmetic shared by every module."""
import math


def round_band(value: float) -> float:
    """IELTS rounding: to the nearest half band, .25 and .75 round up."""
    return math.floor(value * 2 + 0.5) / 2


# The official tables from a raw score (correct answers out of 40) to a band, as IELTS publishes
# them (ielts.org, "How IELTS is scored"): (lowest raw score, band), highest first. The tables
# stop at band 2.5; below that, 1-3 correct answers give band 2 (an estimate) and none band 0.
RAW_TO_BAND = {
    "listening": [(39, 9), (37, 8.5), (35, 8), (32, 7.5), (30, 7), (26, 6.5), (23, 6), (18, 5.5),
                  (16, 5), (13, 4.5), (10, 4), (8, 3.5), (6, 3), (4, 2.5)],
    "reading-academic": [(39, 9), (37, 8.5), (35, 8), (33, 7.5), (30, 7), (27, 6.5), (23, 6), (19, 5.5),
                         (15, 5), (13, 4.5), (10, 4), (8, 3.5), (6, 3), (4, 2.5)],
    "reading-general": [(40, 9), (39, 8.5), (37, 8), (36, 7.5), (34, 7), (32, 6.5), (30, 6), (27, 5.5),
                        (23, 5), (19, 4.5), (15, 4), (12, 3.5), (9, 3), (6, 2.5)],
}


def raw_band(table: str, raw: int) -> float:
    """The band for `raw` correct answers out of 40 (table: listening, reading-academic or
    reading-general)."""
    for lowest, band in RAW_TO_BAND[table]:
        if raw >= lowest:
            return float(band)
    return 2.0 if raw > 0 else 0.0
