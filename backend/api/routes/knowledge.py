"""
Knowledge Graph API Routes — /knowledge/...
All endpoints that power the rich Knowledge Graph UI page.
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents.knowledge_agent import AgentResponse, KnowledgeAgent
from ontology.graph_query import (
    find_entity_by_hint,
    get_full_graph_json,
    get_ingested_document_names,
    get_instrument_detail,
    get_instrument_findings,
    get_non_compliant_findings,
)
from ontology.nx_export import export_for_visualization
from rules.rule_evaluator import RuleEvaluator
from rules.rule_registry import get_registry
from rules.sme_approval import (
    OverrideProposal,
    approve_amendment,
    list_amendments,
    list_proposals,
    reject_amendment,
    submit_override,
)
from services.feedback_service import FeedbackRecord, submit_feedback
from services.telemetry_service import (
    LatencyTimer,
    get_recent,
    get_summary,
    record_query,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# Agent is instantiated lazily on first request (requires env vars at runtime)
_agent: KnowledgeAgent | None = None


def _get_agent() -> KnowledgeAgent:
    global _agent
    if _agent is None:
        _agent = KnowledgeAgent()
    return _agent


# ── Request / Response models ──────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str
    persona: Optional[str] = None
    session_history: Optional[list[dict]] = None
    instrument_urn: Optional[str] = None  # when set, scope context to this instrument


class FeedbackRequest(BaseModel):
    question: str
    answer_excerpt: str = ""
    sentiment: str                    # positive | negative | neutral
    rule_id: Optional[str] = None
    instrument_urn: Optional[str] = None
    persona: Optional[str] = None
    comment: Optional[str] = None


class OverrideRequest(BaseModel):
    rule_id: str
    instrument_urn: str
    proposed_verdict: str
    confidence: float
    evidence_summary: str


class AmendmentDecision(BaseModel):
    sme_name: str
    comment: str = ""
    reason: str = ""


# ── Chat endpoints ─────────────────────────────────────────────────────────────

@router.post("/chat", response_model=AgentResponse)
async def chat(req: ChatRequest):
    """
    Non-streaming chat. Returns full answer + citations in one response.
    Use for API consumers that cannot handle SSE.
    """
    with LatencyTimer() as t:
        try:
            response = await _get_agent().ask(
                question=req.question,
                persona=req.persona,
                session_history=req.session_history,
                instrument_urn=req.instrument_urn,
            )
        except Exception as exc:
            record_query(req.question, "error", latency_ms=t.elapsed_ms, error=str(exc))
            raise HTTPException(status_code=500, detail=str(exc))

    record_query(
        req.question,
        response.intent,
        persona=req.persona,
        latency_ms=t.elapsed_ms,
    )
    return response


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    SSE streaming chat. Each event: data: {"token": "..."}\n\n
    Final event: data: {"citations": [...], "done": true}\n\n
    """
    start = time.perf_counter()

    async def _generator():
        intent = "generic"
        try:
            async for chunk in _get_agent().stream_ask(
                question=req.question,
                persona=req.persona,
                session_history=req.session_history,
                instrument_urn=req.instrument_urn,
            ):
                yield chunk
        except Exception as exc:
            import json
            from openai import APIConnectionError, APITimeoutError
            if isinstance(exc, (APIConnectionError, APITimeoutError)):
                err_msg = "The AI service is temporarily unavailable — please try again."
            else:
                err_msg = str(exc)
            yield f"data: {json.dumps({'error': err_msg})}\n\n"
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            record_query(req.question, intent, persona=req.persona, latency_ms=elapsed_ms)

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Graph / entity endpoints ───────────────────────────────────────────────────

@router.get("/graph")
async def get_graph(
    persona: Optional[str] = Query(default=None),
    hint: Optional[str] = Query(default=None),
):
    """Return the full visualisation graph JSON (nodes + edges)."""
    return export_for_visualization(persona=persona)


@router.get("/ingested-documents")
async def get_ingested_documents():
    """Return filenames of documents already enriched into the knowledge graph."""
    return {"names": get_ingested_document_names()}


@router.get("/entities")
async def search_entities(q: str = Query(..., min_length=1)):
    """Search for entities by name, ISIN, or type hint."""
    rows = find_entity_by_hint(q)
    return {"entities": rows}


@router.get("/entity/{entity_id:path}")
async def get_entity(entity_id: str):
    """Retrieve full detail + findings for one entity (by URN or ISIN)."""
    detail = get_instrument_detail(entity_id)
    findings = get_instrument_findings(entity_id)
    if not detail and not findings:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
    return {"detail": detail, "findings": findings}


@router.get("/non-compliant")
async def get_non_compliant():
    """List all non-compliant findings across all instruments."""
    return {"findings": get_non_compliant_findings()}


# ── Rule endpoints ─────────────────────────────────────────────────────────────

@router.get("/rules")
async def list_rules(use_case: Optional[str] = Query(default=None)):
    """List all active rules, optionally filtered by use case."""
    registry = get_registry()
    rules = registry.get_by_use_case(use_case) if use_case else registry.get_all()
    return {
        "rules": [
            {
                "rule_id": r.rule_id,
                "name": r.name,
                "use_case": r.use_case,
                "regulation": r.regulation,
                "description": r.description,
                "version": r.version,
                "confidence_threshold": r.confidence_threshold,
            }
            for r in rules
        ]
    }


@router.post("/rules/{rule_id}/evaluate")
async def evaluate_rule(rule_id: str, instrument_urn: str = Query(...)):
    """Run a specific rule against an instrument and return the evaluation result."""
    rule = get_registry().get_active(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    evaluator = RuleEvaluator()
    result = evaluator._eval_one(instrument_urn, rule)
    if result is None:
        raise HTTPException(status_code=422, detail="Evaluation returned no result")
    return result.model_dump()


# ── Feedback endpoints ─────────────────────────────────────────────────────────

@router.post("/feedback", status_code=201)
async def post_feedback(req: FeedbackRequest):
    """Submit thumbs-up/down feedback on an agent answer."""
    record = FeedbackRecord(
        question=req.question,
        answer_excerpt=req.answer_excerpt,
        sentiment=req.sentiment,  # type: ignore[arg-type]
        rule_id=req.rule_id,
        instrument_urn=req.instrument_urn,
        persona=req.persona,
        comment=req.comment,
    )
    saved = submit_feedback(record)
    return {"feedback_id": saved.feedback_id, "status": "recorded"}


# ── SME Queue endpoints ────────────────────────────────────────────────────────

@router.get("/sme-queue")
async def get_sme_queue():
    """Return pending SME override proposals and amendments."""
    return {
        "proposals": [p.model_dump() for p in list_proposals(status="pending")],
        "amendments": [a.model_dump() for a in list_amendments(status="awaiting_sme")],
    }


@router.post("/sme-queue/override")
async def submit_override_proposal(req: OverrideRequest):
    """Submit a new override proposal (from AI agent or user)."""
    proposal = OverrideProposal(
        rule_id=req.rule_id,
        instrument_urn=req.instrument_urn,
        proposed_verdict=req.proposed_verdict,
        confidence=req.confidence,
        evidence_summary=req.evidence_summary,
        source="user",
    )
    saved = submit_override(proposal)
    return {"proposal_id": saved.proposal_id, "status": saved.status}


@router.post("/sme-queue/amendments/{amendment_id}/approve")
async def approve_amendment_endpoint(amendment_id: str, body: AmendmentDecision):
    """SME approves a BDD-gated amendment (writes to YAML + reloads registry)."""
    try:
        amendment = approve_amendment(amendment_id, body.sme_name, body.comment)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"amendment_id": amendment.amendment_id, "status": amendment.status}


@router.post("/sme-queue/amendments/{amendment_id}/reject")
async def reject_amendment_endpoint(amendment_id: str, body: AmendmentDecision):
    """SME rejects an amendment."""
    try:
        amendment = reject_amendment(amendment_id, body.sme_name, body.reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"amendment_id": amendment.amendment_id, "status": amendment.status}


# ── Telemetry ──────────────────────────────────────────────────────────────────

@router.get("/telemetry")
async def get_telemetry():
    """Return aggregated telemetry summary."""
    return get_summary()


@router.get("/telemetry/recent")
async def get_recent_telemetry(n: int = Query(default=50, le=200)):
    """Return the N most recent query records."""
    return {"records": get_recent(n)}

