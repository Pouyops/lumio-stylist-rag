"""Environment-backed settings (INSTRUCTIONS §2)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM / embeddings (OpenAI-compatible)
    LLM_BASE_URL: str = "http://localhost:11434/v1"
    LLM_API_KEY: str = "ollama"
    LLM_MODEL: str = "qwen2.5:7b"
    EMBED_BASE_URL: str = "http://localhost:11434/v1"
    EMBED_API_KEY: str = "ollama"
    EMBED_MODEL: str = "bge-m3"
    EMBED_DIM: int = 1536

    # Vector store — empty QDRANT_URL means embedded on-disk mode.
    QDRANT_URL: str = ""
    QDRANT_LOCAL_PATH: str = "./qdrant_data"
    QDRANT_COLLECTION: str = "lumio_products"

    # Website connection
    LUMIO_BASE_URL: str = "http://localhost:3000"
    STYLIST_SYNC_SECRET: str = ""
    STYLIST_API_KEY: str = ""
    SYNC_INTERVAL_MINUTES: int = 10

    # Catalog source: "fixture" (local json) or "http" (pull from website)
    CATALOG_SOURCE: str = "fixture"

    PORT: int = 8010


@lru_cache
def get_settings() -> Settings:
    return Settings()
