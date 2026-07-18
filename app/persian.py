"""Persian text helpers: digit normalization and budget parsing (§4 step 1)."""

from __future__ import annotations

import re
from typing import Optional

# Persian (۰-۹) and Arabic-Indic (٠-٩) digits -> ASCII.
_DIGIT_MAP = {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_DIGIT_MAP.update({ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")})
# Persian thousands separator and Arabic decimal marks -> plain forms.
_DIGIT_MAP.update({ord("٬"): "", ord("،"): ",", ord("٫"): "."})


def normalize_digits(text: str) -> str:
    return (text or "").translate(_DIGIT_MAP)


# "میلیون" / "million" / "m" multipliers; "هزار"/"k" for thousands.
_MILLION = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:میلیون|million|mil|m\b)", re.IGNORECASE)
_THOUSAND = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:هزار|thousand|k\b)", re.IGNORECASE)
_PLAIN = re.compile(r"(\d[\d,]{2,})")  # bare figures like 3,000,000

# Words that signal an upper bound ("under X", "زیر X", "تا X", "حداکثر X").
_UPPER_HINT = re.compile(r"(under|below|max|less than|up to|زیر|تا|حداکثر|کمتر)", re.IGNORECASE)


def _to_int(num: str, mult: int) -> int:
    # Commas are thousands separators here (e.g. "3,000,000"); drop them.
    return int(round(float(num.replace(",", "")) * mult))


def parse_budget(text: str) -> Optional[int]:
    """Best-effort max budget in Toman from free text. Regex fallback for the
    LLM constraint extractor. Returns None if no budget is expressed."""
    if not text:
        return None
    t = normalize_digits(text)

    m = _MILLION.search(t)
    if m:
        return _to_int(m.group(1), 1_000_000)
    m = _THOUSAND.search(t)
    if m:
        return _to_int(m.group(1), 1_000)
    # Bare number — only treat as a budget when an upper-bound word is present,
    # to avoid mistaking e.g. a size or year for a price.
    if _UPPER_HINT.search(t):
        m = _PLAIN.search(t)
        if m:
            val = int(m.group(1).replace(",", ""))
            if val >= 1000:
                return val
    return None
