"""
Intent Listener
---------------
Converts a free-text question into a structured intent object using a
fast/cheap LLM (~200 input tokens, ~80 output tokens).

The listener is intentionally thin — no graph access, no business logic.
It only classifies what the user wants so the KnowledgeAgent can route correctly.
"""
from __future__ import annotations

import json
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

from agents.model_adapter import ModelAdapter, get_listener_adapter


# ── Output schema ─────────────────────────────────────────────────────────────

IntentType = Literal[
    "instrument_detail",   # "Tell me about CLO-2024-01"
    "compliance_check",    # "Is EU-CLO-2024-01 ERISA compliant?"
    "rule_explain",        # "What does Article 6 retention mean?"
    "graph_explore",       # "Show me the graph for structured products"
    "find_entities",       # "Which instruments have STS designation?"
    "erisa_restricted",    # "List all ERISA-restricted instruments"
    "om_extract",          # "What are the economic terms in this OM?"
    "batch_status",        # "What's the status of my batch job?"
    "generic",             # fallback
]


class ParsedIntent(BaseModel):
    intent: IntentType = "generic"
    entity_type: Optional[str] = None      # CLO | ABS | OM | RMBS | …
    entity_hint: Optional[str] = None      # free-text identifier or ISIN
    attribute: Optional[str] = None        # retention | coupon_rate | erisa_flag …
    related_rule: Optional[str] = None     # RISK_RETENTION | ERISA_SECTION_3 …
    persona: Optional[str] = None          # trader | compliance | legal | data_mgmt
    raw_question: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a financial-instrument compliance assistant. 
Extract a JSON intent object from the user's question.

Output ONLY valid JSON with keys:
  intent        — one of: instrument_detail, compliance_check, rule_explain,
                          graph_explore, find_entities, erisa_restricted,
                          om_extract, batch_status, generic
  entity_type   — e.g. CLO, ABS, RMBS, OM, ERISA (or null)
  entity_hint   — an ISIN, ticker, name, or descriptive hint (or null)
  attribute     — the specific data field asked about (or null)
  related_rule  — rule code if mentioned, e.g. RISK_RETENTION (or null)
  persona       — trader, compliance, legal, data_mgmt (or null)
  confidence    — float 0-1

Example input : "Is CLO-2024-01 compliant with the 5% retention rule?"
Example output: {"intent":"compliance_check","entity_type":"CLO",
                 "entity_hint":"CLO-2024-01","attribute":"retention_percentage",
                 "related_rule":"RISK_RETENTION","persona":null,"confidence":0.97}
"""


# ── Listener class ────────────────────────────────────────────────────────────

class Listener:
    def __init__(self, adapter: ModelAdapter | None = None) -> None:
        self._adapter = adapter or get_listener_adapter()

    async def parse(self, question: str, persona: str | None = None) -> ParsedIntent:
        """
        Send the question to the listener model and return a ParsedIntent.
        Falls back to `generic` if the model returns malformed JSON.
        """
        user_msg = question
        if persona:
            user_msg = f"[Persona: {persona}]\n{question}"

        raw = await self._adapter.complete(
            system_prompt=_SYSTEM_PROMPT,
            user_message=user_msg,
            max_tokens=128,
            temperature=0.0,
        )

        intent_data = _safe_parse_json(raw)
        intent_data["raw_question"] = question
        if persona and not intent_data.get("persona"):
            intent_data["persona"] = persona

        return ParsedIntent(**intent_data)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_parse_json(text: str) -> dict:
    """Extract the first JSON object from the model response, with fallback."""
    # Strip markdown fences if present
    text = re.sub(r"```(?:json)?", "", text).strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass
    # Try to extract JSON substring
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group())
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass
    return {"intent": "generic", "confidence": 0.5}

