"""Constraint extraction + filtered vector retrieval (INSTRUCTIONS §4 steps 1-2)."""

from __future__ import annotations

import json
import logging
import re

from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue, Range

from .clients import embed_texts, llm_client, qdrant
from .config import get_settings
from .models import CatalogProduct, ChatMessage, Constraints
from .persian import normalize_digits, parse_budget

log = logging.getLogger("stylist.retrieval")

TOP_K = 12

CATEGORIES = ["Dresses", "Tops", "Bottoms", "Outerwear", "Shoes", "Accessories"]
SEASONS = ["Spring", "Summer", "Autumn", "Winter", "All Seasons"]

# Keyword hints for the regex fallback (en + fa).
_CATEGORY_HINTS = {
    "Dresses": ["dress", "gown", "لباس", "پیراهن", "دِرس"],
    "Tops": ["top", "blouse", "shirt", "knit", "sweater", "بلوز", "تاپ", "پیراهن مردانه"],
    "Bottoms": ["trouser", "pant", "skirt", "jeans", "shorts", "شلوار", "دامن"],
    "Outerwear": ["coat", "jacket", "blazer", "کت", "پالتو", "ژاکت"],
    "Shoes": ["shoe", "sandal", "heel", "boot", "کفش", "صندل", "بوت"],
    "Accessories": ["bag", "tote", "earring", "jewel", "accessor", "کیف", "گوشواره", "زیورآلات"],
}
_SEASON_HINTS = {
    "Spring": ["spring", "بهار"],
    "Summer": ["summer", "تابستان"],
    "Autumn": ["autumn", "fall", "پاییز"],
    "Winter": ["winter", "زمستان"],
}
_SIZE_RE = re.compile(r"\b(XS|S|M|L|XL|XXL|3[6-9]|4[0-5])\b")

_EXTRACT_PROMPT = (
    "Extract shopping constraints from the user's fashion request. "
    "Return ONLY a JSON object with keys: budgetMax (integer Toman or null), "
    f"category (one of {CATEGORIES} or null), season (one of {SEASONS} or null), "
    "sizes (array of size strings like ['M'] or []). "
    "Interpret 'میلیون'/'million' as ×1,000,000 and normalize Persian digits. "
    "Only set a field if the user clearly implies it; otherwise use null/empty."
)


def _fallback_constraints(message: str) -> Constraints:
    t = normalize_digits(message).lower()
    category = next((c for c, kws in _CATEGORY_HINTS.items() if any(k in t for k in kws)), None)
    season = next((s for s, kws in _SEASON_HINTS.items() if any(k in t for k in kws)), None)
    sizes = list(dict.fromkeys(_SIZE_RE.findall(message.upper())))
    return Constraints(
        budgetMax=parse_budget(message),
        category=category,
        season=season,
        sizes=sizes,
    )


def extract_constraints(message: str, history: list[ChatMessage] | None = None) -> Constraints:
    """One small LLM call, with a regex fallback (§4 step 1)."""
    s = get_settings()
    try:
        resp = llm_client().chat.completions.create(
            model=s.LLM_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _EXTRACT_PROMPT},
                {"role": "user", "content": normalize_digits(message)},
            ],
        )
        data = json.loads(resp.choices[0].message.content)
        c = Constraints(
            budgetMax=data.get("budgetMax") or None,
            category=data.get("category") if data.get("category") in CATEGORIES else None,
            season=data.get("season") if data.get("season") in SEASONS else None,
            sizes=[str(x) for x in (data.get("sizes") or [])],
        )
        fb = _fallback_constraints(message)
        # Budget regex is high-precision (needs a million/thousand/upper-bound cue),
        # so trust it whenever the model omitted or under-scaled the figure.
        if c.budgetMax is None or c.budgetMax < 10_000:
            c.budgetMax = fb.budgetMax or c.budgetMax
        # Guard against a rare all-null LLM response: if it extracted nothing at
        # all, fall back to the deterministic keyword pass rather than dropping
        # every filter. (Kept narrow to avoid keyword false-positives normally.)
        if c.category is None and c.season is None and not c.sizes:
            c.category, c.season, c.sizes = fb.category, fb.season, fb.sizes
        return c
    except Exception as e:  # network / parse / API errors -> deterministic fallback
        log.warning("constraint extraction fell back to regex: %s", e)
        return _fallback_constraints(message)


def _build_filter(c: Constraints) -> Filter:
    must: list[FieldCondition] = [FieldCondition(key="stock", range=Range(gt=0))]
    if c.budgetMax:
        must.append(FieldCondition(key="salePrice", range=Range(lte=c.budgetMax)))
    if c.category:
        must.append(FieldCondition(key="category", match=MatchValue(value=c.category)))
    if c.season:
        # Season match includes season-agnostic pieces.
        must.append(FieldCondition(key="season", match=MatchAny(any=[c.season, "All Seasons"])))
    if c.sizes:
        must.append(FieldCondition(key="sizes", match=MatchAny(any=c.sizes)))
    return Filter(must=must)


def _query_text(message: str, history: list[ChatMessage] | None) -> str:
    summary = ""
    if history:
        prior = " ".join(m.content for m in history if m.role == "user")
        summary = f" {prior}"[:200]
    return normalize_digits(message) + summary


def retrieve(
    message: str, history: list[ChatMessage] | None, constraints: Constraints
) -> list[CatalogProduct]:
    """Embed the query and search Qdrant with payload filters (§4 step 2)."""
    s = get_settings()
    vector = embed_texts([_query_text(message, history)])[0]
    result = qdrant().query_points(
        collection_name=s.QDRANT_COLLECTION,
        query=vector,
        query_filter=_build_filter(constraints),
        limit=TOP_K,
        with_payload=True,
    )
    products: list[CatalogProduct] = []
    for h in result.points:
        try:
            products.append(CatalogProduct(**h.payload))
        except Exception:
            continue
    return products
