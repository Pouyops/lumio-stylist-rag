"""Indexing: embed catalog products into Qdrant and keep the index in sync (§3b)."""

from __future__ import annotations

import logging
import threading
import uuid

from qdrant_client.models import PointStruct

from .catalog import content_hash, embed_text, fetch_catalog
from .clients import embed_texts, ensure_collection, qdrant
from .config import get_settings
from .models import CatalogProduct

log = logging.getLogger("stylist.indexer")

# UUID5 namespace so a product id always maps to the same Qdrant point id (§3b).
_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")

# Serialize writes; embedded Qdrant is single-process and the scheduler runs
# sync() on a background thread alongside request handling.
_sync_lock = threading.Lock()


def point_id(product_id: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, product_id))


def _existing_hashes() -> dict[str, str]:
    """Map of point id -> stored contentHash for everything currently indexed."""
    s = get_settings()
    client = qdrant()
    out: dict[str, str] = {}
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=s.QDRANT_COLLECTION,
            with_payload=["contentHash"],
            with_vectors=False,
            limit=256,
            offset=offset,
        )
        for p in points:
            out[str(p.id)] = (p.payload or {}).get("contentHash", "")
        if offset is None:
            break
    return out


def _payload(p: CatalogProduct, chash: str) -> dict:
    data = p.model_dump()
    data["contentHash"] = chash
    return data


def sync(force: bool = False) -> int:
    """Fetch the catalog and reconcile the index. Returns the indexed count.

    force=True re-embeds every product (use after changing EMBED_MODEL)."""
    with _sync_lock:
        ensure_collection()
        s = get_settings()
        client = qdrant()

        products = fetch_catalog()
        existing = _existing_hashes()
        current_ids: set[str] = set()

        to_embed: list[CatalogProduct] = []
        hashes: dict[str, str] = {}
        for p in products:
            pid = point_id(p.id)
            current_ids.add(pid)
            chash = content_hash(p)
            hashes[p.id] = chash
            if force or existing.get(pid) != chash:
                to_embed.append(p)
            else:
                # Unchanged embedding text — refresh mutable fields (price/stock/...).
                client.set_payload(
                    collection_name=s.QDRANT_COLLECTION,
                    payload=_payload(p, chash),
                    points=[pid],
                )

        if to_embed:
            vectors = embed_texts([embed_text(p) for p in to_embed])
            points = [
                PointStruct(
                    id=point_id(p.id),
                    vector=vec,
                    payload=_payload(p, hashes[p.id]),
                )
                for p, vec in zip(to_embed, vectors)
            ]
            client.upsert(collection_name=s.QDRANT_COLLECTION, points=points)

        # Delete points for products no longer in the catalog.
        stale = [pid for pid in existing if pid not in current_ids]
        if stale:
            client.delete(collection_name=s.QDRANT_COLLECTION, points_selector=stale)

        count = indexed_count()
        log.info(
            "sync: %d products, %d embedded, %d refreshed, %d deleted, %d indexed",
            len(products), len(to_embed), len(products) - len(to_embed), len(stale), count,
        )
        return count


def reindex() -> int:
    """Force a full re-embed (manual refresh endpoint)."""
    return sync(force=True)


def indexed_count() -> int:
    s = get_settings()
    try:
        return qdrant().count(collection_name=s.QDRANT_COLLECTION, exact=True).count
    except Exception:  # collection may not exist yet
        return 0
