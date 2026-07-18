"""Orchestrates the /v1/chat pipeline (INSTRUCTIONS §4)."""

from __future__ import annotations

import logging

from .generation import generate
from .indexer import indexed_count
from .models import ChatRequest, ChatResponse
from .retrieval import extract_constraints, retrieve

log = logging.getLogger("stylist.pipeline")


class IndexEmptyError(Exception):
    """Raised when there is nothing indexed to recommend from (-> HTTP 503)."""


def handle_chat(req: ChatRequest) -> ChatResponse:
    if indexed_count() == 0:
        raise IndexEmptyError("index empty")

    constraints = extract_constraints(req.message, req.history)
    candidates = retrieve(req.message, req.history, constraints)
    log.info(
        "chat: lang=%s constraints=%s candidates=%d",
        req.lang, constraints.model_dump(exclude_none=True), len(candidates),
    )
    return generate(req.message, req.lang, req.history, candidates)
