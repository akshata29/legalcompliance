"""
Feedback Service
----------------
Collects thumbs-up / thumbs-down feedback on agent answers and
optionally promotes strongly negative feedback into SME override proposals.
"""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

_FEEDBACK_LOG = (
    Path(__file__).resolve().parent.parent.parent / "data" / "rules" / "feedback_log.jsonl"
)


# ── Models ────────────────────────────────────────────────────────────────────

Sentiment = Literal["positive", "negative", "neutral"]


class FeedbackRecord(BaseModel):
    feedback_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    question: str
    answer_excerpt: str = ""
    sentiment: Sentiment
    rule_id: Optional[str] = None
    instrument_urn: Optional[str] = None
    persona: Optional[str] = None
    comment: Optional[str] = None
    promoted_to_sme: bool = False


# ── In-memory store ───────────────────────────────────────────────────────────

_feedback_store: list[FeedbackRecord] = []
_negative_by_rule: dict[str, list[FeedbackRecord]] = defaultdict(list)

# Threshold: auto-promote to SME queue after N consecutive negative feedbacks
_AUTO_PROMOTE_THRESHOLD = 3


# ── Public API ────────────────────────────────────────────────────────────────

def submit_feedback(record: FeedbackRecord) -> FeedbackRecord:
    """Store feedback and trigger promotion logic if threshold reached."""
    _feedback_store.append(record)
    _persist(record)

    if record.sentiment == "negative" and record.rule_id:
        _negative_by_rule[record.rule_id].append(record)
        _maybe_promote(record.rule_id)

    return record


def list_feedback(
    rule_id: Optional[str] = None,
    sentiment: Optional[Sentiment] = None,
    limit: int = 100,
) -> list[FeedbackRecord]:
    result = list(_feedback_store)
    if rule_id:
        result = [f for f in result if f.rule_id == rule_id]
    if sentiment:
        result = [f for f in result if f.sentiment == sentiment]
    return result[-limit:]


def get_summary() -> dict:
    total = len(_feedback_store)
    positive = sum(1 for f in _feedback_store if f.sentiment == "positive")
    negative = sum(1 for f in _feedback_store if f.sentiment == "negative")
    return {
        "total": total,
        "positive": positive,
        "negative": negative,
        "neutral": total - positive - negative,
        "satisfaction_rate": round(positive / max(total, 1), 4),
        "promoted_to_sme": sum(1 for f in _feedback_store if f.promoted_to_sme),
    }


# ── Private helpers ───────────────────────────────────────────────────────────

def _maybe_promote(rule_id: str) -> None:
    """
    If N+ negative feedback records exist for a rule, create an SME override proposal.
    Each batch is promoted only once per 'promotion window' (we clear the batch after).
    """
    negatives = _negative_by_rule[rule_id]
    if len(negatives) < _AUTO_PROMOTE_THRESHOLD:
        return

    # Promote to SME queue
    try:
        from rules.sme_approval import OverrideProposal, submit_override

        evidence_summary = "; ".join(
            f.comment or f.question for f in negatives[:5]
        )
        proposal = OverrideProposal(
            rule_id=rule_id,
            instrument_urn=negatives[-1].instrument_urn or "unknown",
            proposed_verdict="insufficient_evidence",
            confidence=0.4,
            evidence_summary=f"Auto-promoted after {len(negatives)} negative feedbacks: {evidence_summary}",
            source="feedback_service",
        )
        submit_override(proposal)

        # Mark records as promoted and clear batch
        for f in negatives:
            f.promoted_to_sme = True
        _negative_by_rule[rule_id] = []
    except Exception:
        # Non-critical path — never crash the feedback endpoint
        pass


def _persist(record: FeedbackRecord) -> None:
    _FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _FEEDBACK_LOG.open("a", encoding="utf-8") as fh:
        fh.write(record.model_dump_json() + "\n")

