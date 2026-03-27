"""
Knowledge Agent
---------------
Orchestrates: Listener → Graph queries → LLM → SSE response + Citations.

Flow:
  1. Listener.parse(question)  → ParsedIntent
  2. Route intent to graph query helper
  3. Build compact context (≤400 tokens) from subgraph
  4. Call LLM (streaming) with system prompt + graph context
  5. Attach citations from graph to final response
"""
from __future__ import annotations

import json
from typing import AsyncIterator

from pydantic import BaseModel

from agents.citation_builder import Citation, CitationBuilder
from agents.listener import Listener, ParsedIntent
from agents.model_adapter import ModelAdapter, get_agent_adapter
from ontology.graph_query import (
    check_erisa_exemption,
    find_entity_by_hint,
    get_compact_subgraph,
    get_erisa_restricted_instruments,
    get_instrument_detail,
    get_instrument_findings,
    get_non_compliant_findings,
)
from rules.rule_evaluator import RuleEvaluator


# ── Response model ─────────────────────────────────────────────────────────────

class AgentResponse(BaseModel):
    answer: str
    citations: list[dict]
    intent: str
    entity_hint: str | None = None
    confidence: float = 1.0
    human_review_required: bool = False


# ── System prompts ─────────────────────────────────────────────────────────────

_BASE_SYSTEM = """\
You are a financial compliance assistant specialising in EU Securitisation Regulation,
ERISA, Offering Memoranda, and New Issuance workflows.

Rules:
1. Answer ONLY from the provided knowledge-graph context.
2. Always cite the specific page/section when making a claim.
3. Be concise but complete — 2-4 sentences per claim.
4. If information is missing from the context, say so explicitly.
5. Never speculate beyond the evidence provided.
6. Format monetary values with currency symbols, percentages with % sign.
"""

_PERSONA_ADDENDA: dict[str, str] = {
    "trader": "\nFocus on economic terms: coupon, maturity, yield, liquidity profile, tranche structure.",
    "compliance": "\nFocus on regulatory obligations: retention %, STS criteria, ERISA flags, prohibited transactions.",
    "legal": "\nFocus on legal entity relationships, trustee obligations, covenant compliance, prospectus disclosures.",
    "data_mgmt": "\nInclude technical metadata: URNs, provision references, graph topology, confidence scores.",
}

_NAMESPACE_ADDENDA: dict[str, str] = {
    "erisa": (
        "\n\nDocument context: ERISA Plan Document (US pension/retirement).\n"
        "Applicable rules: fiduciary duty (\u00a7404), prohibited transactions (\u00a7406), "
        "plan assets, vesting schedules (\u00a7203), contribution timing (\u00a7412), "
        "distribution rules, claims procedure (\u00a7503), fidelity bond, anti-alienation (\u00a7206(d)).\n"
        "Do NOT apply EU Securitisation / STS / retention % rules \u2014 they are irrelevant for ERISA plans."
    ),
    "om": (
        "\n\nDocument context: Offering Memorandum (private fund).\n"
        "Applicable rules: fee disclosure, accredited investor, conflicts of interest, "
        "distribution waterfall, transfer restrictions, key person, ERISA 25% plan asset limit, AIFMD."
    ),
    "issuance": (
        "\n\nDocument context: New Securities Issuance / Prospectus.\n"
        "Applicable rules: UK Prospectus Regulation, FCA approval, UK MAR insider list, "
        "MiFIR transaction reporting, ISIN, indenture covenants, sanctions/AML, ESG disclosure."
    ),
}


# ── Knowledge Agent ────────────────────────────────────────────────────────────

class KnowledgeAgent:
    def __init__(
        self,
        adapter: ModelAdapter | None = None,
        listener: Listener | None = None,
    ) -> None:
        self._adapter = adapter or get_agent_adapter()
        self._listener = listener or Listener()
        self._citations = CitationBuilder()
        self._evaluator = RuleEvaluator()

    async def ask(
        self,
        question: str,
        persona: str | None = None,
        session_history: list[dict] | None = None,
        instrument_urn: str | None = None,
    ) -> AgentResponse:
        """Non-streaming answer for REST endpoint."""
        intent = await self._listener.parse(question, persona)
        context, entity_urns = await self._build_context(intent, instrument_urn=instrument_urn)
        system_prompt = _build_system_prompt(persona, instrument_urn)
        user_msg = _build_user_message(question, context, session_history)

        answer = await self._adapter.complete(
            system_prompt=system_prompt,
            user_message=user_msg,
            max_tokens=768,
            temperature=0.2,
        )

        raw_citations = self._citations.from_entities(entity_urns)
        citations = self._citations.deduplicate(self._citations.top_n(raw_citations))

        return AgentResponse(
            answer=answer,
            citations=[c.to_dict() for c in citations],
            intent=intent.intent,
            entity_hint=intent.entity_hint,
            confidence=intent.confidence,
        )

    async def stream_ask(
        self,
        question: str,
        persona: str | None = None,
        session_history: list[dict] | None = None,
        instrument_urn: str | None = None,
    ) -> AsyncIterator[str]:
        """
        SSE streaming generator.
        Yields: "data: <json>\n\n" for each token chunk.
        Final event: "data: [CITATIONS] <json>\n\n"
        """
        intent = await self._listener.parse(question, persona)
        context, entity_urns = await self._build_context(intent, instrument_urn=instrument_urn)
        system_prompt = _build_system_prompt(persona, instrument_urn)
        user_msg = _build_user_message(question, context, session_history)

        async for token in self._adapter.stream(
            system_prompt=system_prompt,
            user_message=user_msg,
            max_tokens=768,
            temperature=0.2,
        ):
            yield f"data: {json.dumps({'token': token})}\n\n"

        # Append citations as a final SSE event
        raw_citations = self._citations.from_entities(entity_urns)
        citations = self._citations.deduplicate(self._citations.top_n(raw_citations))
        yield (
            f"data: {json.dumps({'citations': [c.to_dict() for c in citations], 'done': True})}\n\n"
        )

    # ── Context routing ────────────────────────────────────────────────────────

    async def _build_context(
        self,
        intent: ParsedIntent,
        instrument_urn: str | None = None,
    ) -> tuple[str, list[str]]:
        """
        Route the parsed intent to the appropriate graph query and return
        (compact_context_text, [entity_urns_for_citations]).
        If instrument_urn is provided (scoped chat), use it directly instead of
        searching by entity hint.
        """
        hint   = intent.entity_hint or ""
        i_type = intent.intent

        # Normalise: accept urn:document:{uuid} or urn:instrument:{uuid}
        _scoped_urn: str | None = None
        if instrument_urn:
            uuid = instrument_urn.split(":")[-1]
            _scoped_urn = f"urn:instrument:{uuid}"

        entity_urns: list[str] = []

        # ── When scoped to a specific instrument, ALWAYS load its findings so
        #    the LLM has real evidence regardless of how the intent was classified.
        scoped_findings_ctx = ""
        if _scoped_urn:
            findings = get_instrument_findings(_scoped_urn)
            detail   = get_instrument_detail(_scoped_urn)
            entity_urns = [_scoped_urn]
            scoped_findings_ctx = _format_instrument_context(detail, findings)

        if i_type == "instrument_detail" and (hint or _scoped_urn):
            if _scoped_urn:
                context = scoped_findings_ctx
            else:
                rows = find_entity_by_hint(hint)
                urn = str(rows[0]["uri"]) if rows else None
                if urn:
                    entity_urns = [urn]
                    detail = get_instrument_detail(urn)
                    findings = get_instrument_findings(urn)
                    context = _format_instrument_context(detail, findings)
                else:
                    context = f"No instrument found matching '{hint}'."

        elif i_type == "compliance_check" and (hint or _scoped_urn):
            if _scoped_urn:
                urn = _scoped_urn
            else:
                rows = find_entity_by_hint(hint)
                urn = str(rows[0]["uri"]) if rows else None
            if urn:
                if urn not in entity_urns:
                    entity_urns = [urn]
                rule_id = intent.related_rule
                if rule_id:
                    # evaluate_instrument returns list[RuleEvalResult]
                    eval_results = self._evaluator.evaluate_instrument(urn)
                    match = next((r for r in eval_results if r.rule_id == rule_id), None)
                    if match:
                        rule_ctx = (
                            f"Rule: {match.rule_id}\nVerdict: {match.verdict}\n"
                            f"Confidence: {match.confidence:.2f}\n"
                            f"Explanation: {match.explanation}\n"
                            f"Evidence: {'; '.join(str(e) for e in match.evidence)}"
                        )
                        context = (scoped_findings_ctx + "\n" + rule_ctx) if scoped_findings_ctx else rule_ctx
                    else:
                        context = scoped_findings_ctx or f"No findings for rule '{rule_id}'."
                else:
                    context = scoped_findings_ctx or _format_instrument_context(
                        get_instrument_detail(urn), get_instrument_findings(urn)
                    )
            else:
                context = scoped_findings_ctx or f"No instrument found matching '{hint}'."

        elif i_type == "erisa_restricted":
            rows = get_erisa_restricted_instruments()
            entity_urns = [str(r["uri"]) for r in rows]
            context = _format_list("ERISA-restricted instruments", rows, "label")
            # Check for exemptions
            for r in rows[:5]:
                urn = str(r["uri"])
                exempt = check_erisa_exemption(urn)
                if exempt:
                    context += f"\n  → {urn}: exemption {exempt[0].get('type','?')} ({exempt[0].get('status','?')})"

        elif i_type == "find_entities":
            rows = find_entity_by_hint(hint or intent.entity_type or "")
            entity_urns = [str(r["uri"]) for r in rows]
            context = _format_list("Matching entities", rows, "label") or "No matching entities found."

        elif i_type == "graph_explore":
            subgraph = get_compact_subgraph(hint or intent.entity_type or "")
            entity_urns = [n["id"] for n in subgraph.get("nodes", [])]
            context = _format_subgraph(subgraph)

        elif i_type == "rule_explain" and intent.related_rule:
            from rules.rule_registry import get_registry
            rule = get_registry().get_active(intent.related_rule)
            context = (
                f"Rule: {rule.rule_id}\nName: {rule.name}\n"
                f"Regulation: {rule.regulation}\nDescription: {rule.description}\n"
                f"Obligation: {rule.obligation}"
            ) if rule else f"Rule '{intent.related_rule}' not found."

        else:
            # Generic fallback — if we have a scoped instrument use its findings;
            # otherwise search by hint and return a compact subgraph.
            if scoped_findings_ctx:
                context = scoped_findings_ctx
            elif hint:
                subgraph = get_compact_subgraph(hint)
                entity_urns = [n["id"] for n in subgraph.get("nodes", [])]
                context = _format_subgraph(subgraph)
            else:
                context = "No specific entity context found. Please refine your question."

        return context, entity_urns


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _build_system_prompt(persona: str | None, instrument_urn: str | None = None) -> str:
    prompt = _BASE_SYSTEM
    # Add namespace-specific context before persona addenda
    if instrument_urn:
        name = instrument_urn.lower()
        if "erisa" in name:
            ns = "erisa"
        elif "_om_" in name or name.startswith("om_"):
            ns = "om"
        elif "issuance" in name:
            ns = "issuance"
        else:
            ns = None
        if ns and ns in _NAMESPACE_ADDENDA:
            prompt += _NAMESPACE_ADDENDA[ns]
    if persona and persona in _PERSONA_ADDENDA:
        prompt += _PERSONA_ADDENDA[persona]
    return prompt


def _build_user_message(
    question: str,
    context: str,
    history: list[dict] | None,
) -> str:
    parts: list[str] = []
    if history:
        recent = history[-4:]  # last 2 turns
        parts.append("CONVERSATION HISTORY:")
        for msg in recent:
            role = msg.get("role", "user").upper()
            parts.append(f"{role}: {msg.get('content', '')}")
        parts.append("")
    parts.append("KNOWLEDGE GRAPH CONTEXT:")
    parts.append(context)
    parts.append("")
    parts.append(f"QUESTION: {question}")
    return "\n".join(parts)


def _format_instrument_context(detail: dict, findings: list[dict]) -> str:
    """Combine instrument properties and findings into LLM-readable context."""
    out: list[str] = []
    props = detail.get("properties", [])
    if props:
        out.append("INSTRUMENT PROPERTIES:")
        for r in props:
            pred = r.get("predicate", "?")
            val  = r.get("value", "?")
            # Skip verbose RDF-type lines, keep human-relevant props
            if any(skip in pred for skip in ["rdf-syntax", "rdf#type", "owl#", "22-rdf"]):
                continue
            short_pred = pred.split("#")[-1].split("/")[-1].split(":")[-1]
            out.append(f"  {short_pred}: {val}")
    if findings:
        out.append("\nCOMPLIANCE FINDINGS:")
        for r in findings:
            rule     = r.get("ruleId", "?")
            verdict  = r.get("findingType", "?")
            risk     = r.get("riskLevel", "?")
            page     = r.get("page") or "?"
            verbatim = (r.get("verbatim") or "")[:200]
            out.append(f"  [{rule}] {verdict} (risk={risk}) p.{page} — \"{verbatim}\"")
    else:
        out.append("\nFINDINGS: none recorded.")
    return "\n".join(out) + "\n"


def _format_list(title: str, rows: list[dict], label_key: str) -> str:
    if not rows:
        return f"{title}: none.\n"
    out = [f"{title}:"]
    for r in rows:
        out.append(f"  • {r.get('uri','?')} ({r.get(label_key,'?')})")
    return "\n".join(out) + "\n"


def _format_subgraph(subgraph: dict) -> str:
    nodes = subgraph.get("nodes", [])
    edges = subgraph.get("edges", [])
    if not nodes:
        return "Empty subgraph.\n"
    out = [f"SUBGRAPH ({len(nodes)} nodes, {len(edges)} edges):"]
    for n in nodes[:20]:
        out.append(f"  [{n.get('type','?')}] {n.get('id','?')} — {n.get('label','')}")
    for e in edges[:30]:
        out.append(f"  {e.get('source','?')} --{e.get('relation','?')}--> {e.get('target','?')}")
    return "\n".join(out) + "\n"

