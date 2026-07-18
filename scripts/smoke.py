"""Smoke tests for the running stylist service (INSTRUCTIONS §6.3).

Start the server first:  uvicorn app.main:app --port 8010
Then run:                python scripts/smoke.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402
from app.generation import _guardrail  # noqa: E402
from app.models import CatalogProduct, ChatResponse  # noqa: E402

BASE = "http://localhost:8010"
FIXTURE = Path(__file__).resolve().parent / "dev_catalog_fixture.json"

PRODUCTS = {
    p["id"]: p
    for p in json.loads(FIXTURE.read_text(encoding="utf-8"))["products"]
}

passed = 0
failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def has_persian(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in text)


def chat(message: str, lang: str, key: str | None) -> httpx.Response:
    headers = {"Content-Type": "application/json"}
    if key is not None:
        headers["Authorization"] = f"Bearer {key}"
    return httpx.post(
        f"{BASE}/v1/chat",
        headers=headers,
        json={"message": message, "lang": lang, "history": []},
        timeout=60.0,
    )


def main() -> int:
    api_key = get_settings().STYLIST_API_KEY

    print("\n[health]")
    r = httpx.get(f"{BASE}/healthz", timeout=10.0)
    body = r.json()
    check("healthz 200", r.status_code == 200, str(r.status_code))
    check("indexedProducts >= 12", body.get("indexedProducts", 0) >= 12, str(body))
    check("model reported", bool(body.get("model")), str(body))

    print("\n[auth]")
    check("no key -> 401", chat("hi", "en", None).status_code == 401)
    check("wrong key -> 401", chat("hi", "en", "nope").status_code == 401)
    bad = httpx.post(
        f"{BASE}/v1/chat",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"message": "", "lang": "en", "history": []},
        timeout=30.0,
    )
    check("empty message -> 422", bad.status_code == 422, str(bad.status_code))

    print("\n[EN: summer wedding dress under 3,000,000]")
    r = chat("a dress for a summer wedding under 3,000,000 Toman", "en", api_key)
    check("200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        data = ChatResponse(**r.json())
        check("reply in English", bool(data.reply) and not has_persian(data.reply), data.reply[:80])
        for pid in data.productIds:
            p = PRODUCTS.get(pid, {})
            check(f"{pid} is a Dress", p.get("category") == "Dresses", str(p.get("category")))
            check(f"{pid} salePrice <= 3,000,000", p.get("salePrice", 1e12) <= 3_000_000, str(p.get("salePrice")))
        check("<= 4 products", len(data.productIds) <= 4, str(len(data.productIds)))

    print("\n[FA: same request in Persian]")
    r = chat("لباسی برای عروسی تابستانی زیر ۳ میلیون تومان می‌خوام", "fa", api_key)
    check("200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        data = ChatResponse(**r.json())
        check("reply in Persian", has_persian(data.reply), data.reply[:80])
        for pid in data.productIds:
            p = PRODUCTS.get(pid, {})
            check(f"{pid} is a Dress", p.get("category") == "Dresses", str(p.get("category")))
            check(f"{pid} salePrice <= 3,000,000", p.get("salePrice", 1e12) <= 3_000_000, str(p.get("salePrice")))

    print("\n[honesty: winter coat under 500,000]")
    r = chat("a winter coat under 500,000 Toman", "en", api_key)
    check("200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        data = ChatResponse(**r.json())
        check("empty productIds (nothing fits)", data.productIds == [], str(data.productIds))
        check("reply explains", bool(data.reply), data.reply[:80])

    print("\n[guardrail unit: off-catalog id injection]")
    cands = [CatalogProduct(id="a", slug="a", name="A", price=1, salePrice=1),
             CatalogProduct(id="b", slug="b", name="B", price=1, salePrice=1)]
    resp = _guardrail(
        ChatResponse(reply="x", productIds=["a", "HACK", "b", "a", "b", "a"], followUps=[]),
        {c.id for c in cands},
    )
    check("off-catalog id stripped", "HACK" not in resp.productIds, str(resp.productIds))
    check("deduped & capped <= 4", resp.productIds == ["a", "b"], str(resp.productIds))

    print(f"\n==== {passed} passed, {failed} failed ====")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
