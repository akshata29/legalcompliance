"""Rule schema — Pydantic models for versioned, externally-configurable rules."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional
from pydantic import BaseModel, Field


class RuleDefinition(BaseModel):
    id: str
    version: str
    name: str
    regulation: str
    use_case: str = "eu_sec"        # eu_sec | erisa | om | new_issuance
    condition: str = ""             # Plain English condition description
    obligation: str = ""            # Obligation text
    evidence_fields: list[str] = Field(default_factory=list)
    confidence_threshold: float = 0.85
    human_review_trigger: str = ""  # condition string
    effective_from: date
    effective_until: Optional[date] = None
    supersedes: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    description: str = ""

    @property
    def rule_id(self) -> str:
        """Alias for id — used by agent and API layers."""
        return self.id


class RuleVersion(BaseModel):
    rule_id: str
    versions: list[RuleDefinition]

    def active_on(self, target_date: date) -> Optional[RuleDefinition]:
        """Return the version of this rule active on target_date."""
        candidates = [
            v for v in self.versions
            if v.effective_from <= target_date
            and (v.effective_until is None or v.effective_until >= target_date)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda v: v.effective_from)


class RuleEvalResult(BaseModel):
    rule_id: str
    rule_name: str
    instrument_uri: str
    verdict: str                    # compliant | non_compliant | needs_review | not_applicable
    confidence: float = 0.0
    evidence: list[dict] = Field(default_factory=list)  # citation list
    explanation: str = ""
    sparql_trace: str = ""          # The SPARQL query that produced this result
    human_review_required: bool = False
    rule_version: str = ""


class BDDScenarioResult(BaseModel):
    feature: str
    scenario: str
    status: str                     # passed | failed | skipped
    error_message: Optional[str] = None
    duration_ms: int = 0
