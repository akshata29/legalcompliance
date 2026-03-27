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

  — Knowledge Graph (new) ——————————————————————————————————
  POST /knowledge/chat             — single-turn RAG answer
  POST /knowledge/chat/stream      — SSE streaming chat
  GET  /knowledge/graph            — full graph JSON for visualisation
  GET  /knowledge/entities         — entity search
  GET  /knowledge/entity/{id}      — entity detail + findings
  GET  /knowledge/non-compliant    — all non-compliant findings
  GET  /knowledge/rules            — active rule list
  POST /knowledge/rules/{id}/evaluate — on-demand rule evaluation
  POST /knowledge/feedback         — thumbs up/down feedback
  GET  /knowledge/sme-queue        — pending SME override queue
  POST /knowledge/sme-queue/override — submit override proposal
  POST /knowledge/sme-queue/amendments/{id}/approve
  POST /knowledge/sme-queue/amendments/{id}/reject
  GET  /knowledge/telemetry        — aggregated query telemetry
  GET  /knowledge/telemetry/recent — recent query records

  — Batch (new) ————————————————————————————————————————————
  POST /batch/submit               — submit document for enrichment
  GET  /batch/status/{id}          — job status
  GET  /batch/jobs                 — list all jobs
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env into os.environ FIRST so all subsequent imports see the values
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import asyncio

from api.routes import documents, processing, sessions
from api.routes import knowledge
from api.routes import rules_designer
from batch.batch_routes import router as batch_router
from batch.batch_queue import BatchQueue
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

    # ── Knowledge Graph initialisation ────────────────────────────────────────
    try:
        from ontology.graph_store import GraphStore
        GraphStore.get()  # initialise singleton + load TTL schemas
        logger.info("Knowledge graph store initialised")
    except Exception as exc:
        logger.warning("Graph store init failed (non-fatal): %s", exc)

    # ── Synthetic demo data ─────────────────────────────────────────────────
    # Synthetic seeding disabled — graph is populated only from real document
    # enrichments submitted via the Ingest tab.

    # ── Start batch worker ────────────────────────────────────────────────────
    try:
        worker_task = asyncio.create_task(BatchQueue.get().start_worker())
        logger.info("Batch queue worker started")
    except Exception as exc:
        logger.warning("Batch worker start failed (non-fatal): %s", exc)
        worker_task = None

    # ── Start scheduler ───────────────────────────────────────────────────────
    try:
        from batch.scheduler import start_scheduler
        start_scheduler()
    except Exception as exc:
        logger.warning("Scheduler start failed (non-fatal): %s", exc)

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    try:
        from batch.scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    if worker_task:
        worker_task.cancel()
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
app.include_router(knowledge.router)
app.include_router(batch_router)
app.include_router(rules_designer.router)


@app.get("/health", tags=["health"])
async def health():
    return JSONResponse({"status": "ok", "service": "legal-compliance-api"})


# ─── Dev runner ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
