"""
FastAPI application entry point.

Endpoints:
  GET  /health                     — liveness probe
  POST /documents/upload           — upload document to Blob Storage
  GET  /documents/                 — list uploaded documents
  GET  /documents/synthetic        — synthetic demo document metadata
  POST /processing/start           — kick off Legacy or Optimized pipeline
  GET  /processing/status/{id}     — poll processing status
  GET  /processing/result/{id}     — fetch full results
  GET  /processing/compare/{docid} — side-by-side pipeline comparison
  GET  /sessions/                  — list sessions from CosmosDB
  GET  /sessions/{id}              — single session detail
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import documents, processing, sessions
from config import get_settings

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ─── Application lifecycle ────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Legal Compliance API starting up…")
    yield
    logger.info("Legal Compliance API shutting down.")


app = FastAPI(
    title="Legal Compliance Document Processing API",
    description=(
        "End-to-end EU Securities regulatory compliance document processing. "
        "Supports a Legacy pipeline (baseline) and an Optimized pipeline "
        "(prompt batching, pre-filter, async I/O, pipeline parallelism) "
        "switchable via the UI Toggle."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routes ───────────────────────────────────────────────────────────────────
app.include_router(documents.router)
app.include_router(processing.router)
app.include_router(sessions.router)


@app.get("/health", tags=["health"])
async def health():
    return JSONResponse({"status": "ok", "service": "legal-compliance-api"})


# ─── Dev runner ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
