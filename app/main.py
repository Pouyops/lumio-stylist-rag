"""FastAPI app: routes, auth, startup sync + scheduler (INSTRUCTIONS §3b, §4)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .clients import ensure_collection
from .config import get_settings
from .indexer import indexed_count, reindex, sync
from .models import ChatRequest, ChatResponse, HealthResponse
from .pipeline import IndexEmptyError, handle_chat

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("stylist.main")

scheduler: BackgroundScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler
    s = get_settings()
    ensure_collection()
    try:
        sync()
    except Exception as e:  # don't crash on a transient sync/embed failure at boot
        log.error("startup sync failed: %s", e)

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        _safe_sync,
        "interval",
        minutes=s.SYNC_INTERVAL_MINUTES,
        id="catalog-sync",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("scheduler started: sync every %d min", s.SYNC_INTERVAL_MINUTES)
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)


def _safe_sync() -> None:
    try:
        sync()
    except Exception as e:
        log.error("scheduled sync failed: %s", e)


app = FastAPI(title="LUMIO Stylist RAG", lifespan=lifespan)


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    s = get_settings()
    expected = f"Bearer {s.STYLIST_API_KEY}"
    if not s.STYLIST_API_KEY or authorization != expected:
        raise HTTPException(status_code=401, detail="invalid api key")


# Ensure error bodies use the contract's {"error": "..."} shape (§4).
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": "invalid request body"})


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    s = get_settings()
    return HealthResponse(status="ok", indexedProducts=indexed_count(), model=s.LLM_MODEL)


@app.post("/v1/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
def chat(req: ChatRequest) -> ChatResponse:
    try:
        return handle_chat(req)
    except IndexEmptyError:
        raise HTTPException(status_code=503, detail="index empty")
    except Exception as e:
        log.error("chat failed: %s", e)
        raise HTTPException(status_code=503, detail="stylist temporarily unavailable")


@app.post("/admin/reindex", dependencies=[Depends(require_api_key)])
def admin_reindex() -> dict:
    try:
        count = reindex()
    except Exception as e:
        log.error("reindex failed: %s", e)
        raise HTTPException(status_code=503, detail="reindex failed")
    return {"status": "ok", "indexedProducts": count}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=get_settings().PORT)
