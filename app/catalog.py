"""Catalog acquisition (INSTRUCTIONS §3): pull from the website or a local fixture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx

from .config import get_settings
from .models import CatalogProduct

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "dev_catalog_fixture.json"


def _parse_envelope(data: dict) -> list[CatalogProduct]:
    return [CatalogProduct(**p) for p in data.get("products", [])]


def fetch_catalog() -> list[CatalogProduct]:
    """Return the current catalog per CATALOG_SOURCE.

    - "http": GET ${LUMIO_BASE_URL}/api/stylist/catalog with the sync secret (§3a).
    - "fixture": read scripts/dev_catalog_fixture.json (standalone dev).
    """
    s = get_settings()
    if s.CATALOG_SOURCE == "http":
        url = f"{s.LUMIO_BASE_URL.rstrip('/')}/api/stylist/catalog"
        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {s.STYLIST_SYNC_SECRET}"},
            timeout=20.0,
        )
        resp.raise_for_status()
        return _parse_envelope(resp.json())

    if not FIXTURE_PATH.exists():
        raise FileNotFoundError(
            f"Catalog fixture missing at {FIXTURE_PATH}. Run: python scripts/make_fixture.py"
        )
    return _parse_envelope(json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))


def embed_text(p: CatalogProduct) -> str:
    """The text sent to the embedder (INSTRUCTIONS §3b)."""
    return (
        f"{p.name}. {p.category}, {p.styleTag}, {p.season}, color {p.color}, "
        f"brand {p.brand}, by {p.shopName}. {p.description}"
    )


def content_hash(p: CatalogProduct) -> str:
    """Hash of only the fields that affect the embedding, so price/stock edits
    refresh the payload without triggering a re-embed (§3b)."""
    basis = "|".join(
        str(x)
        for x in (p.name, p.category, p.styleTag, p.season, p.color, p.brand, p.shopName, p.description)
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()
