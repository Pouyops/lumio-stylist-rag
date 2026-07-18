"""Regenerate scripts/dev_catalog_fixture.json from the website's Prisma seed.

The stylist service normally pulls its catalog over HTTP from the site's
`GET /api/stylist/catalog` route (INSTRUCTIONS §3a). That route does not exist
yet (web integration is deferred), so for development we derive an equivalent
fixture from `web/prisma/seed.ts`, producing the exact §3a response shape.

The generated fixture (`dev_catalog_fixture.json`) is committed to this repo, so
you only need this script to refresh it after the seed changes. Because this is a
standalone repo, point it at the monorepo seed via the SEED_PATH env var:

    SEED_PATH=/path/to/lumio/web/prisma/seed.ts python scripts/make_fixture.py

`salePrice` is computed with the same rounding as `web/lib/types.ts::salePrice()`.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
# SEED_PATH overrides the default (the sibling monorepo layout, if present).
SEED = Path(os.environ.get("SEED_PATH", HERE.parent.parent / "web" / "prisma" / "seed.ts"))
OUT = HERE / "dev_catalog_fixture.json"


def sale_price(price: int, discount_percent: int) -> int:
    """Mirror of web/lib/types.ts salePrice(): round to clean 1000-Toman figures."""
    if not discount_percent:
        return price
    return round(price * (100 - discount_percent) / 100 / 1000) * 1000


def _block(src: str, marker: str) -> str:
    """Return the text of a `const NAME = [...]` or `= {...}` block.

    Starts scanning after the `=` so any brackets inside a TypeScript type
    annotation (e.g. `Record<string, [string, string, string]>`) are skipped.
    """
    start = src.index("=", src.index(marker)) + 1
    # find the first bracket after the `=`, then match to its close
    open_ch = None
    depth = 0
    out = []
    for ch in src[start:]:
        if open_ch is None:
            if ch in "[{":
                open_ch = ch
                close_ch = "]" if ch == "[" else "}"
                depth = 1
                out.append(ch)
            continue
        out.append(ch)
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                break
    return "".join(out)


def _num(raw: str) -> int:
    return int(raw.replace("_", ""))


def _sizes(raw: str) -> list[str]:
    return re.findall(r'"([^"]+)"', raw)


def parse_seed(src: str) -> list[dict]:
    shops_block = _block(src, "const SHOPS")
    products_block = _block(src, "const PRODUCTS")
    discounts_block = _block(src, "const DISCOUNTS")
    meta_block = _block(src, "const META")

    # shop name -> slug
    shop_slug = {
        name: slug
        for slug, name in re.findall(r'slug:\s*"([^"]+)",\s*name:\s*"([^"]+)"', shops_block)
    }

    discounts = {
        slug: int(pct)
        for slug, pct in re.findall(r'"([^"]+)":\s*(\d+)', discounts_block)
    }

    meta = {
        slug: _sizes(arr)  # [brand, season, styleTag]
        for slug, arr in re.findall(r'"([^"]+)":\s*\[([^\]]+)\]', meta_block)
    }

    # shared description constant
    desc_match = re.search(r'const DESCRIPTION\s*=\s*\n?\s*"([^"]+)"', src)
    description = desc_match.group(1) if desc_match else ""

    products = []
    for obj in re.findall(r"\{[^{}]*\}", products_block):
        def g(pattern, default=None):
            m = re.search(pattern, obj)
            return m.group(1) if m else default

        slug = g(r'slug:\s*"([^"]+)"')
        if not slug:
            continue
        price = _num(g(r"price:\s*([\d_]+)", "0"))
        discount = discounts.get(slug, 0)
        brand, season, style = (meta.get(slug) + [None, None, None])[:3] if meta.get(slug) else (None, None, None)
        shop_name = g(r'shop:\s*"([^"]+)"')

        products.append(
            {
                "id": slug,  # dev fixture: slug doubles as stable id (real sync uses Prisma cuid)
                "slug": slug,
                "name": g(r'name:\s*"([^"]+)"'),
                "description": description,
                "price": price,
                "salePrice": sale_price(price, discount),
                "discountPercent": discount,
                "category": g(r'category:\s*"([^"]+)"'),
                "color": g(r'color:\s*"([^"]+)"'),
                "sizes": _sizes(g(r"sizes:\s*\[([^\]]*)\]", "")),
                "stock": int(g(r"stock:\s*(\d+)", "0")),
                "brand": brand,
                "season": season,
                "styleTag": style,
                "rating": float(g(r"rating:\s*([\d.]+)", "0")),
                "reviewCount": int(g(r"reviewCount:\s*(\d+)", "0")),
                "shopName": shop_name,
                "shopSlug": shop_slug.get(shop_name),
                "image": g(r'image:\s*"([^"]+)"'),
                "url": f"/product/{slug}",
            }
        )
    return products


def main() -> None:
    if not SEED.exists():
        sys.exit(
            f"seed not found at {SEED}\n"
            "This standalone repo ships a pre-generated dev_catalog_fixture.json, so you\n"
            "only need this script to refresh it. Point it at the monorepo seed with:\n"
            "  SEED_PATH=/path/to/lumio/web/prisma/seed.ts python scripts/make_fixture.py"
        )
    src = SEED.read_text(encoding="utf-8")
    products = parse_seed(src)
    envelope = {
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "products": products,
    }
    OUT.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(products)} products to {OUT}")


if __name__ == "__main__":
    main()
