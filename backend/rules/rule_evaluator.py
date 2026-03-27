"""
Rule evaluator — evaluates rule obligations against the RDF graph.
Uses SPARQL queries to find evidence, then generates a verdict + explanation.
Every result includes the SPARQL trace for explainability.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from ontology.graph_store import GraphStore
from ontology.graph_query import get_findings_by_rule, get_non_compliant_findings
from rules.rule_schema import RuleDefinition, RuleEvalResult
from rules.rule_registry import get_registry

logger = logging.getLogger(__name__)


class RuleEvaluator:

    def __init__(self) -> None:
        self._store = GraphStore.get()
        self._registry = get_registry()

    def evaluate_instrument(
        self,
        instrument_uri: str,
        on_date: Optional[date] = None,
    ) -> list[RuleEvalResult]:
        """Evaluate all applicable rules for one instrument."""
        results = []
        for rule in self._registry.get_all():
            result = self._eval_one(instrument_uri, rule)
            if result:
                results.append(result)
        return results

    def _eval_one(self, instrument_uri: str, rule: RuleDefinition) -> Optional[RuleEvalResult]:
        """SPARQL-based evaluation of one rule against one instrument."""
        sparql = self._build_sparql(instrument_uri, rule)
        try:
            rows = list(self._store.query(sparql))
        except Exception as exc:
            logger.warning("SPARQL eval error for rule %s: %s", rule.id, exc)
            rows = []

        if not rows:
            return RuleEvalResult(
                rule_id=rule.id,
                rule_name=rule.name,
                instrument_uri=instrument_uri,
                verdict="not_applicable",
                confidence=0.0,
                explanation=f"No evidence found for rule {rule.id} on this instrument.",
                sparql_trace=sparql,
                rule_version=rule.version,
            )

        # Aggregate findings
        finding_types = []
        evidence = []
        for row in rows:
            row_dict = {str(var): str(row[var]) if row[var] is not None else None
                        for var in row.labels}
            finding_types.append(row_dict.get("findingType", "unknown"))
            confidence_val = row_dict.get("confidence", "0.0")
            try:
                conf = float(confidence_val)
            except (ValueError, TypeError):
                conf = 0.0
            evidence.append({
                "finding": row_dict.get("finding", ""),
                "finding_type": row_dict.get("findingType", "unknown"),
                "risk_level": row_dict.get("riskLevel", "medium"),
                "confidence": conf,
                "page": row_dict.get("onPage"),
                "section": row_dict.get("inSection"),
                "verbatim": row_dict.get("verbatim"),
            })

        # Determine verdict
        if "non_compliant" in finding_types:
            verdict = "non_compliant"
        elif "needs_review" in finding_types:
            verdict = "needs_review"
        elif "compliant" in finding_types:
            verdict = "compliant"
        else:
            verdict = "not_applicable"

        confidences = [e["confidence"] for e in evidence if e["confidence"] > 0]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        human_review = (avg_conf < rule.confidence_threshold or verdict in ("non_compliant", "needs_review"))

        explanation = self._build_explanation(rule, verdict, evidence)

        return RuleEvalResult(
            rule_id=rule.id,
            rule_name=rule.name,
            instrument_uri=instrument_uri,
            verdict=verdict,
            confidence=avg_conf,
            evidence=evidence,
            explanation=explanation,
            sparql_trace=sparql,
            human_review_required=human_review,
            rule_version=rule.version,
        )

    def _build_sparql(self, instrument_uri: str, rule: RuleDefinition) -> str:
        """Build a SPARQL query to find findings for this rule on this instrument."""
        inst_fragment = instrument_uri.split(":")[-1]
        return f"""
            SELECT ?finding ?findingType ?riskLevel ?confidence ?onPage ?inSection ?verbatim WHERE {{
                ?finding rdf:type lc:Finding .
                ?finding lc:ruleId "{rule.id}" .
                OPTIONAL {{ ?finding lc:findingType ?findingType }}
                OPTIONAL {{ ?finding lc:riskLevel ?riskLevel }}
                OPTIONAL {{ ?finding lc:confidence ?confidence }}
                OPTIONAL {{ ?finding lc:onPage ?onPage }}
                OPTIONAL {{ ?finding lc:inSection ?inSection }}
                OPTIONAL {{ ?finding lc:verbatim ?verbatim }}
                FILTER (CONTAINS(STR(?finding), "{inst_fragment}"))
            }}
        """

    def _build_explanation(
        self, rule: RuleDefinition, verdict: str, evidence: list[dict]
    ) -> str:
        """Human-readable explanation with rule citation and evidence summary."""
        lines = [
            f"Rule: {rule.name} (ID: {rule.id}, v{rule.version})",
            f"Regulation: {rule.regulation}",
            f"Verdict: {verdict.upper()}",
        ]
        if evidence:
            lines.append("Evidence:")
            for e in evidence[:3]:
                page = f"§p.{e['page']}" if e.get("page") else ""
                section = f", {e['section']}" if e.get("section") else ""
                verbatim = f'"{e["verbatim"][:120]}..."' if e.get("verbatim") else ""
                lines.append(f"  [{e['finding_type'].upper()}, risk={e['risk_level']}, conf={e['confidence']:.2f}] {page}{section} — {verbatim}")
        return "\n".join(lines)

    def evaluate_all(self) -> list[RuleEvalResult]:
        """Evaluate all rules across all known instruments."""
        from ontology.graph_query import find_entities_by_type
        instruments = find_entities_by_type("instrument")
        results = []
        for inst in instruments:
            uri = inst.get("entity", "")
            if uri:
                results.extend(self.evaluate_instrument(uri))
        return results
