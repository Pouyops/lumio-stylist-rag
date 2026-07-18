"""Shared clients: OpenAI-compatible LLM/embeddings + Qdrant factory."""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from .config import get_settings


@lru_cache
def llm_client() -> OpenAI:
    s = get_settings()
    return OpenAI(base_url=s.LLM_BASE_URL, api_key=s.LLM_API_KEY, timeout=30.0)


@lru_cache
def embed_client() -> OpenAI:
    s = get_settings()
    # Separate client so LLM and embeddings can point at different backends.
    return OpenAI(base_url=s.EMBED_BASE_URL, api_key=s.EMBED_API_KEY, timeout=30.0)


@lru_cache
def qdrant() -> QdrantClient:
    s = get_settings()
    if s.QDRANT_URL:
        return QdrantClient(url=s.QDRANT_URL)
    # Embedded on-disk mode — no server/Docker required. Still supports payload
    # filtering, which is why we use Qdrant over a flat embeddings file.
    return QdrantClient(path=s.QDRANT_LOCAL_PATH)


def ensure_collection() -> None:
    s = get_settings()
    client = qdrant()
    if not client.collection_exists(s.QDRANT_COLLECTION):
        client.create_collection(
            collection_name=s.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=s.EMBED_DIM, distance=Distance.COSINE),
        )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-embed with the configured embedding model."""
    if not texts:
        return []
    s = get_settings()
    resp = embed_client().embeddings.create(model=s.EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]
