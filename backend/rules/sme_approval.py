"""
SME Approval Workflow
---------------------
Collect rule-override proposals from the AI feedback loop, batch them by rule,
route through a BDD gate, and (on SME sign-off) write back to the YAML rule file.

Architecture decision (ADR-004):
  Overrides are NEVER auto-applied.
  append-only audit log → SME queue → BDD gate → YAML write → reload registry
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

_AUDIT_LOG = Path(__file__).resolve().parent.parent.parent / "data" / "rules" / "sme_audit_log.jsonl"
_RULES_DIR  = Path(__file__).resolve().parent.parent.parent / "data" / "rules"


# ── Data models ───────────────────────────────────────────────────────────────

class OverrideProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    rule_id: str
    instrument_urn: str
    proposed_verdict: str          # compliant | non_compliant | insufficient_evidence
    confidence: float
    evidence_summary: str
    source: str = "ai_agent"       # ai_agent | user_feedback | batch_job
    status: str = "pending"        # pending | approved | rejected | bdd_failed
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    reviewer_comment: Optional[str] = None


class SMEAmendment(BaseModel):
    """
    A consolidated amendment for one rule, derived from multiple proposals.
    Sent to the SME queue for final sign-off.
    """
    amendment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rule_id: str
    current_version: str
    proposed_version: str          # bumped semver, e.g.  "2024-09-01"
    changes: dict                  # field → {old, new}
    supporting_proposals: list[str]  # proposal_ids
    bdd_passed: bool = False
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: str = "awaiting_sme"   # awaiting_sme | approved | rejected


# ── In-memory queue (reset on restart; persist via audit log) ─────────────────

_proposals: list[OverrideProposal] = []
_amendments: list[SMEAmendment]    = []


# ── Public API ────────────────────────────────────────────────────────────────

def submit_override(proposal: OverrideProposal) -> OverrideProposal:
    """
    Accept an override proposal, append to audit log, add to in-memory queue.
    Returns the stored proposal (with proposal_id assigned).
    """
    _proposals.append(proposal)
    _append_audit(proposal.model_dump())
    return proposal


def list_proposals(rule_id: str | None = None, status: str | None = None) -> list[OverrideProposal]:
    result = list(_proposals)
    if rule_id:
        result = [p for p in result if p.rule_id == rule_id]
    if status:
        result = [p for p in result if p.status == status]
    return result


def list_amendments(status: str | None = None) -> list[SMEAmendment]:
    if status:
        return [a for a in _amendments if a.status == status]
    return list(_amendments)


def propose_amendment(
    rule_id: str,
    changes: dict,
    proposal_ids: list[str],
    new_effective_date: str | None = None,
) -> SMEAmendment:
    """
    Derive an SMEAmendment from accumulated override proposals for one rule.
    Does NOT update the YAML yet — needs `approve_amendment()` after BDD gate.
    """
    from rules.rule_registry import get_registry  # local import avoids circular

    registry = get_registry()
    active = registry.get_active(rule_id)
    if active is None:
        raise ValueError(f"Rule {rule_id} not found in registry")

    new_version = new_effective_date or datetime.now(timezone.utc).date().isoformat()
    amendment = SMEAmendment(
        rule_id=rule_id,
        current_version=active.version,
        proposed_version=new_version,
        changes=changes,
        supporting_proposals=proposal_ids,
    )
    _amendments.append(amendment)
    _append_audit({"type": "amendment_proposed", **amendment.model_dump()})
    return amendment


def record_bdd_result(amendment_id: str, passed: bool) -> None:
    """Mark the BDD gate result on an amendment."""
    for a in _amendments:
        if a.amendment_id == amendment_id:
            a.bdd_passed = passed
            a.status = "awaiting_sme" if passed else "bdd_failed"
            _append_audit({"type": "bdd_result", "amendment_id": amendment_id, "passed": passed})
            return
    raise KeyError(f"Amendment {amendment_id} not found")


def approve_amendment(amendment_id: str, sme_name: str, comment: str = "") -> SMEAmendment:
    """
    SME approves an amendment that has already passed BDD.
    Writes new version to the YAML rule file and triggers registry reload.
    """
    amendment = _get_amendment(amendment_id)
    if not amendment.bdd_passed:
        raise ValueError("Cannot approve: BDD gate has not passed for this amendment")

    _apply_to_yaml(amendment)
    amendment.status = "approved"

    _append_audit({
        "type": "amendment_approved",
        "amendment_id": amendment_id,
        "sme": sme_name,
        "comment": comment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # Mark related proposals as approved
    for p in _proposals:
        if p.proposal_id in amendment.supporting_proposals:
            p.status = "approved"
            p.reviewed_by = sme_name
            p.reviewed_at = datetime.now(timezone.utc).isoformat()
            p.reviewer_comment = comment

    # Hot-reload the registry so new version takes effect immediately
    from rules.rule_registry import get_registry
    get_registry().reload()

    return amendment


def reject_amendment(amendment_id: str, sme_name: str, reason: str) -> SMEAmendment:
    """SME rejects an amendment — proposals remain in log for audit but are not applied."""
    amendment = _get_amendment(amendment_id)
    amendment.status = "rejected"

    _append_audit({
        "type": "amendment_rejected",
        "amendment_id": amendment_id,
        "sme": sme_name,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    for p in _proposals:
        if p.proposal_id in amendment.supporting_proposals:
            p.status = "rejected"
            p.reviewed_by = sme_name
            p.reviewer_comment = reason

    return amendment


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_amendment(amendment_id: str) -> SMEAmendment:
    for a in _amendments:
        if a.amendment_id == amendment_id:
            return a
    raise KeyError(f"Amendment {amendment_id} not found")


def _apply_to_yaml(amendment: SMEAmendment) -> None:
    """Locate the rule in its YAML file and inject the new version entry."""
    for yaml_path in _RULES_DIR.glob("*.yaml"):
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        rules: list[dict] = data.get("rules", [])
        for rule in rules:
            if rule.get("id") == amendment.rule_id:
                new_entry = dict(rule)
                new_entry["version"] = amendment.proposed_version
                for field, change in amendment.changes.items():
                    new_entry[field] = change["new"]
                rules.append(new_entry)
                data["rules"] = rules
                yaml_path.write_text(
                    yaml.dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8",
                )
                return
    raise KeyError(f"Rule {amendment.rule_id} not found in any YAML under data/rules/")


def _append_audit(record: dict) -> None:
    """Append one JSON line to the append-only audit log."""
    _AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    record.setdefault("logged_at", datetime.now(timezone.utc).isoformat())
    with _AUDIT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")

