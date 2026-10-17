"""Dates on a timeline read as years, so a timeline can place its events in proportion (v2's own): "1526", "500 BC",
"320 BCE", "AD 78", "c. 1500", "1920s", "1500s", "16th century", "early 18th century", "3rd millennium BC",
"15 August 1947", "1947-48", "10,000 years ago". A year is a float, negative before Christ (500 BC is -500).

Used by the compiler (compile_lecture.py: a timeline's range and spans checked) and by the engine
(pocket_lecture.big_timeline: where each event sits, the scale of years under the track).

    python timeline_dates.py "16th century" "500 BC" "1920s"
"""

from __future__ import annotations

import math
import re
import sys

NOW = 2025
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                      "dec"])}
_BC = re.compile(r"\b(b\.?\s?c\.?\s?e?\.?|bce)(?![a-z])", re.I)
_AD = re.compile(r"\b(a\.?\s?d\.?|c\.?\s?e\.?)(?![a-z])", re.I)
_ORDINAL = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+(century|centuries|millennium|millennia)\b", re.I)
_WORD_ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
                 "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
                 "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
                 "twentieth": 20, "twenty-first": 21}


def year(value) -> float | None:
    """A date as a year (negative before Christ), or None when it names no year ("the Stone Age", "Step 2")."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().lower().replace("–", "-").replace("—", "-").replace("’", "'")
    if not text:
        return None
    bc = bool(_BC.search(text))
    sign = -1.0 if bc else 1.0
    # "early / mid / late" within a century or a decade.
    part = 0.5
    if re.search(r"\bearly\b", text):
        part = 0.2
    elif re.search(r"\blate\b", text):
        part = 0.8
    words = text
    for word, k in _WORD_ORDINAL.items():
        words = re.sub(rf"\b{word}\b", f"{k}th", words)
    m = _ORDINAL.search(words)
    if m:
        k = int(m.group(1))
        if m.group(2).startswith("millenni"):
            span, start = 1000, (k - 1) * 1000
        else:
            span, start = 100, (k - 1) * 100
        # Before Christ the centuries count down: the 3rd century BC runs from 300 to 201 BC.
        return -(start + span * (1 - part)) if bc else start + span * part
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(million|thousand)?\s*years?\s+ago", text)
    if m:
        n = float(m.group(1).replace(",", ""))
        n *= {"million": 1e6, "thousand": 1e3}.get(m.group(2) or "", 1)
        return NOW - n
    # A decade or a century as "1920s", "1500s", "'60s".
    m = re.search(r"\b(\d{2,4})0'?s\b", text)
    if m and not re.search(r"\d\s*(?:bc|bce|ad|ce)", text[:m.start()]):
        base = int(m.group(1)) * 10
        width = 100 if base % 100 == 0 and len(m.group(1)) >= 3 and m.group(1).endswith("0") else 10
        return sign * (base + width * part) if not bc else -(base + width * (1 - part))
    if "'" in text and re.search(r"'\d", text):
        return None                                   # "'60s": which century is not said
    m = re.search(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", text)
    if not m:
        return None
    n = float(m.group(0).replace(",", ""))
    # A small number among other words is not a year ("Step 2", "Phase 3"), unless the date says BC or AD.
    marked = bc or bool(_AD.search(text)) or bool(re.search(r"\b(c\.|ca\.|circa|year)\b", text))
    if n < 100 and not marked and re.search(r"[a-z]{2,}", re.sub(r"\b(?:" + "|".join(MONTHS) + r")[a-z]*", "", text)):
        return None
    if n == 0 or n > 10_000_000:
        return None
    # A day and month before the year ("15 August 1947"): the year is the last four-digit number.
    years = re.findall(r"\b\d{3,4}\b", text)
    if years and n < 32 and any(mo in text for mo in MONTHS):
        n = float(years[-1])
    out = sign * n
    for mo, k in MONTHS.items():
        if re.search(rf"\b{mo}", text) and not bc:
            out += k / 12
            break
    return out


def label(y: float, any_bc: bool = False) -> str:
    """A year written for a scale: "500 BC", "AD 78" (when the scale crosses into BC), "1600", "8000 BC"."""
    n = int(round(abs(y)))
    if n == 0 and any_bc:
        return "AD 1"                     # there is no year 0: the scale's mark between 1 BC and AD 1
    if y < 0:
        return f"{n:,} BC" if n >= 10000 else f"{n} BC"
    if any_bc and n < 1000:
        return f"AD {n}"
    return f"{n:,}" if n >= 10000 else str(n)


def ticks(lo: float, hi: float, most: int = 7) -> list[float]:
    """Round years between lo and hi for a scale, at most `most` (1, 2 or 5 times a power of ten apart)."""
    span = max(hi - lo, 1e-6)
    raw = span / max(most - 1, 1)
    power = 10 ** math.floor(math.log10(raw))
    step = next(m * power for m in (1, 2, 5, 10) if m * power >= raw)
    step = max(step, 1.0)
    first = math.ceil(lo / step) * step
    out = []
    t = first
    while t <= hi + 1e-9 and len(out) < most + 2:
        out.append(round(t, 6))
        t += step
    return out


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(f"{arg!r}: {year(arg)}")
