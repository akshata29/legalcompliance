"""
Processing routes — start, poll, and compare pipeline runs.
Supports both the Legacy and Optimized pipelines.
In-memory session store (backed by CosmosDB when available).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from config import get_settings
from models.schemas import (
    ComparisonMetrics,
    PipelineMode,
    ProcessDocumentRequest,
    ProcessingSession,
    ProcessingStatus,
    ProcessingStatusResponse,
    Provision,
)
from processing.legacy_pipeline import LegacyPipeline
from processing.optimized_pipeline import OptimizedPipeline
from services.cosmos_service import CosmosService
from services.document_service import DocumentService
from services.search_service import SearchService
from services.storage_service import StorageService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/processing", tags=["processing"])

# ─── In-memory session store ─────────────────────────────────────────────────
# Used as a fast lookup during a request; CosmosDB is the durable store.
_sessions: dict[str, ProcessingSession] = {}
_SYNTHETIC_DOC_ID = "synthetic-001"


def _load_rules(doc_name: str = "") -> list[dict]:
    """Load rule categories appropriate for the document being processed."""
    data_dir = Path(__file__).parent.parent.parent.parent / "data" / "synthetic"
    name = doc_name.lower()
    if "erisa" in name:
        fname = "erisa_rules.json"
    elif name.startswith("om_") or "_om_" in name:
        fname = "om_rules.json"
    elif "issuance" in name:
        fname = "issuance_rules.json"
    else:
        fname = "eu_sec_rules.json"
    rules_path = data_dir / fname
    if rules_path.exists():
        with open(rules_path, encoding="utf-8") as f:
            return json.load(f)
    # Fall back to eu_sec_rules.json if selected file is missing
    rules_path = data_dir / "eu_sec_rules.json"
    if rules_path.exists():
        with open(rules_path, encoding="utf-8") as f:
            return json.load(f)
    # Fallback minimal rule set
    return [
        {"id": "DATA_RETENTION", "name": "Data Retention", "description": "Obligations to retain personal and financial data for specified periods."},
        {"id": "DATA_TRANSFER", "name": "Cross-Border Transfer", "description": "Requirements for transfering personal data to third countries or international organisations."},
        {"id": "CONSENT", "name": "Consent Management", "description": "Rules governing freely given, specific, informed and unambiguous consent."},
        {"id": "REPORTING", "name": "Regulatory Reporting", "description": "Obligations to report transactions and positions to competent authorities."},
        {"id": "RISK_DISCLOSURE", "name": "Risk Disclosure", "description": "Requirements to clearly disclose material investment and operational risks."},
        {"id": "RECORD_KEEPING", "name": "Record Keeping", "description": "Obligations to maintain accurate and retrievable business records."},
        {"id": "PRIVACY_NOTICE", "name": "Privacy Notice", "description": "Requirements to provide fair processing information to data subjects."},
        {"id": "THIRD_PARTY", "name": "Third-Party Management", "description": "Due diligence and contractual requirements for processors and sub-processors."},
        {"id": "LAWFUL_BASIS", "name": "Lawful Processing Basis", "description": "Requirement to identify and document a valid legal basis for each processing activity."},
        {"id": "SUBJECT_RIGHTS", "name": "Data Subject Rights", "description": "Obligations to honour access, erasure, portability and objection requests."},
    ]


def _load_synthetic_provisions() -> list[Provision]:
    """Load the synthetic 150-page document and segment it into provisions."""
    doc_path = (
        Path(__file__).parent.parent.parent.parent / "data" / "synthetic" / "eu_sec_150page.txt"
    )
    if not doc_path.exists():
        raise FileNotFoundError(f"Synthetic document not found: {doc_path}")

    text = doc_path.read_text(encoding="utf-8")
    svc = DocumentService.__new__(DocumentService)   # skip __init__ (no Azure needed)
    return svc.segment_into_provisions(text, "eu_sec_150page.txt")


async def _run_pipeline(
    session: ProcessingSession,
    provisions: list[Provision],
    rules: list[dict],
    enable_indexing: bool = False,
) -> None:
    """Background task that executes the appropriate pipeline and persists results."""
    cosmos = CosmosService()

    async def _persist(sess: ProcessingSession) -> None:
        """Write to Cosmos in a thread (SDK is sync) without blocking the event loop."""
        await asyncio.to_thread(cosmos.upsert_item_sync, sess)

    async def _status_cb(sess: ProcessingSession, pct: int) -> None:
        _sessions[sess.session_id] = sess
        try:
            await _persist(sess)
        except Exception as exc:
            logger.warning("Cosmos write failed at pct=%d status=%s: %s", pct, sess.status, exc)

    try:
        if session.pipeline_mode == PipelineMode.LEGACY:
            pipeline = LegacyPipeline()
        else:
            pipeline = OptimizedPipeline()

        session = await pipeline.run(session, provisions, rules, _status_cb)
        _sessions[session.session_id] = session

        # Knowledge Graph enrichment — runs automatically for every Optimized
        # pipeline run regardless of enable_indexing. Non-blocking: fires as a
        # background task so the pipeline response is not delayed.
        if session.pipeline_mode == PipelineMode.OPTIMIZED and session.status == ProcessingStatus.COMPLETE:
            try:
                from ontology.enrichment import enrich_from_session
                asyncio.create_task(
                    enrich_from_session(session.model_dump(mode="json")),
                )
                logger.info(
                    "Knowledge graph enrichment scheduled for session %s",
                    session.session_id,
                )
            except Exception as _enc_exc:
                logger.warning("Could not schedule graph enrichment: %s", _enc_exc)

        # Bulk AI Search indexing — only for the Optimized pipeline (P6) and
        # only when the caller explicitly opted in via enable_indexing.
        # Runs synchronous SDK calls in a thread so the event loop is never blocked.
        if enable_indexing and session.pipeline_mode == PipelineMode.OPTIMIZED:
            session.status = ProcessingStatus.INDEXING
            _sessions[session.session_id] = session
            try:
                search = SearchService()
                prov_dicts = [p.model_dump() for p in provisions]
                await asyncio.to_thread(
                    search.index_provisions,
                    session.document_id, session.session_id, prov_dicts,
                )
                logger.info("AI Search bulk indexing complete")
            except Exception as exc:
                logger.warning("AI Search indexing failed (non-critical): %s", exc)

    except Exception as exc:
        logger.exception("Pipeline execution failed: %s", exc)
        session.status = ProcessingStatus.FAILED
        session.error_message = str(exc)
        _sessions[session.session_id] = session
    finally:
        # Final write — full document including all provisions, clauses, findings
        if session.status == ProcessingStatus.INDEXING:
            session.status = ProcessingStatus.COMPLETE
        _sessions[session.session_id] = session
        await asyncio.to_thread(cosmos.upsert_item_sync, session)
        logger.info(
            "Session %s final write: %d provisions, %d clauses, %d findings",
            session.session_id,
            len(session.provisions), len(session.clauses), len(session.findings),
        )


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.post("/start", response_model=ProcessingStatusResponse)
async def start_processing(body: ProcessDocumentRequest, background: BackgroundTasks):
    """
    Start processing a document using the chosen pipeline mode.
    Returns session_id immediately; poll /status/{session_id} for updates.
    """
    # Resolve provisions
    if body.document_id == _SYNTHETIC_DOC_ID:
        try:
            provisions = _load_synthetic_provisions()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        doc_name = body.document_name or "eu_sec_prospectus_sample.txt"
    else:
        # Real uploaded document — download and process via Document Intelligence
        try:
            storage = StorageService()
            blobs = storage.list_documents()
            blob_entry = next(
                (b for b in blobs if b["name"].startswith(body.document_id + "/")), None
            )
            if not blob_entry:
                raise HTTPException(status_code=404, detail=f"Document {body.document_id} not found.")

            data = await storage.download_document(blob_entry["name"])
            doc_svc = DocumentService()
            blob_filename = blob_entry["name"].split("/", 1)[-1].lower()
            if blob_filename.endswith(".txt") or blob_filename.endswith(".md"):
                # Plain text — skip Document Intelligence, decode directly
                markdown = data.decode("utf-8", errors="replace")
            else:
                markdown, _ = await doc_svc.analyse_document_bytes(data)
            provisions = doc_svc.segment_into_provisions(markdown)
            doc_name = body.document_name or blob_entry["name"].split("/", 1)[-1]
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Document analysis failed: {exc}")

    rules = _load_rules(doc_name)

    session = ProcessingSession(
        document_id=body.document_id,
        document_name=doc_name,
        pipeline_mode=body.pipeline_mode,
        status=ProcessingStatus.PENDING,
    )
    _sessions[session.session_id] = session

    background.add_task(_run_pipeline, session, provisions, rules, body.enable_indexing)

    return ProcessingStatusResponse(
        session_id=session.session_id,
        status=session.status,
        pipeline_mode=session.pipeline_mode,
        progress_pct=0,
        metrics=session.metrics,
    )


@router.get("/status/{session_id}", response_model=ProcessingStatusResponse)
async def get_processing_status(session_id: str):
    """Poll processing status for a running or completed session."""
    session = _sessions.get(session_id)
    if not session:
        # Try CosmosDB
        cosmos = CosmosService()
        session = await cosmos.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")
        _sessions[session_id] = session

    _STATUS_PCT = {
        ProcessingStatus.PENDING: 0,
        ProcessingStatus.UPLOADING: 5,
        ProcessingStatus.EXTRACTING: 10,
        ProcessingStatus.CHUNKING: 15,
        ProcessingStatus.INDEXING: 20,
        ProcessingStatus.CATEGORIZING: 40,
        ProcessingStatus.EXTRACTING_CLAUSES: 65,
        ProcessingStatus.ANALYZING: 85,
        ProcessingStatus.COMPLETE: 100,
        ProcessingStatus.FAILED: 0,
    }
    return ProcessingStatusResponse(
        session_id=session_id,
        status=session.status,
        pipeline_mode=session.pipeline_mode,
        current_phase=session.status.value,
        progress_pct=_STATUS_PCT.get(session.status, 0),
        metrics=session.metrics,
        error_message=session.error_message,
    )


@router.get("/result/{session_id}", response_model=ProcessingSession)
async def get_processing_result(session_id: str):
    """Retrieve the complete result of a finished processing session."""
    session = _sessions.get(session_id)
    if not session:
        cosmos = CosmosService()
        session = await cosmos.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")
    if session.status not in {ProcessingStatus.COMPLETE, ProcessingStatus.FAILED}:
        raise HTTPException(status_code=202, detail="Processing not yet complete.")
    return session


@router.get("/compare/{document_id}", response_model=ComparisonMetrics)
async def compare_pipelines(document_id: str):
    """
    Return side-by-side metrics for the most recent Legacy and Optimized
    runs on a given document, computing speedup and call-reduction stats.
    """
    legacy_s = next(
        (
            s for s in reversed(list(_sessions.values()))
            if s.document_id == document_id and s.pipeline_mode == PipelineMode.LEGACY
               and s.status == ProcessingStatus.COMPLETE
        ),
        None,
    )
    opt_s = next(
        (
            s for s in reversed(list(_sessions.values()))
            if s.document_id == document_id and s.pipeline_mode == PipelineMode.OPTIMIZED
               and s.status == ProcessingStatus.COMPLETE
        ),
        None,
    )

    speedup = None
    call_reduction = None
    token_reduction = None
    if legacy_s and opt_s:
        lt = legacy_s.metrics.total_duration_seconds or 1
        ot = opt_s.metrics.total_duration_seconds or 1
        speedup = round(lt / ot, 2) if ot > 0 else None

        lc = legacy_s.metrics.total_llm_calls or 1
        oc = opt_s.metrics.total_llm_calls or 1
        call_reduction = round(100 * (lc - oc) / lc, 1) if lc > 0 else None

        ltok = legacy_s.metrics.total_tokens_used or 1
        otok = opt_s.metrics.total_tokens_used or 1
        token_reduction = round(100 * (ltok - otok) / ltok, 1) if ltok > 0 else None

    return ComparisonMetrics(
        document_id=document_id,
        legacy_session_id=legacy_s.session_id if legacy_s else None,
        optimized_session_id=opt_s.session_id if opt_s else None,
        legacy_metrics=legacy_s.metrics if legacy_s else None,
        optimized_metrics=opt_s.metrics if opt_s else None,
        speedup_factor=speedup,
        llm_call_reduction_pct=call_reduction,
        token_reduction_pct=token_reduction,
    )
