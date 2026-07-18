"""Pydantic v2 request/response and catalog models (INSTRUCTIONS §3a, §4)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ----- Chat contract (§4) ---------------------------------------------------
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    lang: Literal["en", "fa"] = "en"
    history: list[ChatMessage] = Field(default_factory=list, max_length=6)


class ChatResponse(BaseModel):
    reply: str
    productIds: list[str] = Field(default_factory=list)
    followUps: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    indexedProducts: int
    model: str


# ----- Catalog (§3a) --------------------------------------------------------
class CatalogProduct(BaseModel):
    id: str
    slug: str
    name: str
    description: str = ""
    price: int
    salePrice: int
    discountPercent: int = 0
    category: Optional[str] = None
    color: Optional[str] = None
    sizes: list[str] = Field(default_factory=list)
    stock: int = 0
    brand: Optional[str] = None
    season: Optional[str] = None
    styleTag: Optional[str] = None
    rating: float = 0.0
    reviewCount: int = 0
    shopName: Optional[str] = None
    shopSlug: Optional[str] = None
    image: Optional[str] = None
    url: Optional[str] = None


# ----- Retrieval constraints (§4 pipeline step 1) ---------------------------
class Constraints(BaseModel):
    budgetMax: Optional[int] = None
    category: Optional[str] = None
    season: Optional[str] = None
    sizes: list[str] = Field(default_factory=list)
