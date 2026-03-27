"""
Rules Designer API — CRUD for versioned rule definitions.
YAML source files live in data/rules/ and are hot-reloaded after every write.
No server restart required to pick up changes.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from rules.rule_registry import get_registry
from rules.rule_schema import RuleDefinition

router = APIRouter(prefix="/rules-designer", tags=["rules-designer"])

USE_CASES = ("eu_sec", "erisa", "om", "new_issuance")


# ── Request / response models ──────────────────────────────────────────────────

class RulePayload(BaseModel):
    """Fields accepted when creating or updating a rule."""
    id: str
    version: str = "1.0"
    name: str
    regulation: str = ""
    use_case: str = "eu_sec"
    condition: str = ""
    obligation: str = ""
    evidence_fields: list[str] = Field(default_factory=list)
    confidence_threshold: float = 0.85
    human_review_trigger: str = ""
    effective_from: str = Field(default_factory=lambda: date.today().isoformat())
    effective_until: Optional[str] = None
    supersedes: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    description: str = ""

    def to_rule_definition(self) -> RuleDefinition:
        return RuleDefinition(
            id=self.id,
            version=self.version,
            name=self.name,
            regulation=self.regulation,
            use_case=self.use_case,
            condition=self.condition,
            obligation=self.obligation,
            evidence_fields=self.evidence_fields,
            confidence_threshold=self.confidence_threshold,
            human_review_trigger=self.human_review_trigger,
            effective_from=date.fromisoformat(self.effective_from),
            effective_until=(
                date.fromisoformat(self.effective_until) if self.effective_until else None
            ),
            supersedes=self.supersedes,
            keywords=self.keywords,
            description=self.description,
        )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/")
def list_rules():
    """Return all active rules grouped by use_case."""
    rules = get_registry().get_all()
    grouped: dict[str, list] = {}
    for r in rules:
        grouped.setdefault(r.use_case, []).append(r.model_dump(mode="json"))
    return {
        "rules": [r.model_dump(mode="json") for r in rules],
        "grouped": grouped,
        "total": len(rules),
    }


@router.get("/{rule_id}")
def get_rule(rule_id: str):
    """Return a single rule by ID."""
    rule = get_registry().get_active(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    return rule.model_dump(mode="json")


@router.post("/", status_code=201)
def create_rule(payload: RulePayload):
    """Create a new rule. Returns 409 if a rule with the same ID already exists."""
    registry = get_registry()
    if registry.get_active(payload.id) or registry._find_source_file(payload.id):
        raise HTTPException(
            status_code=409,
            detail=f"Rule '{payload.id}' already exists. Use PUT to update.",
        )
    rd = payload.to_rule_definition()
    registry.save_rule(rd)
    return rd.model_dump(mode="json")


@router.put("/{rule_id}")
def update_rule(rule_id: str, payload: RulePayload):
    """Update an existing rule. Creates it if it does not exist yet."""
    payload.id = rule_id  # URL param is authoritative
    rd = payload.to_rule_definition()
    get_registry().save_rule(rd)
    return rd.model_dump(mode="json")


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: str):
    """Delete a rule by ID. Returns 404 if not found."""
    deleted = get_registry().delete_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    return None


@router.post("/reload")
def reload_rules():
    """Force hot-reload of all YAML rule files."""
    count = get_registry().reload()
    return {"reloaded": True, "rule_count": count}
