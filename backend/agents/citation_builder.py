"""
Citation Builder
----------------
Constructs Citation objects from the RDF graph by following
lc:citesProvision triples back to document + page + section + verbatim.

Citations are attached to every agent response so users can verify claims
against the source document pages.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from rdflib import URIRef

from ontology.graph_store import GraphStore
from ontology.namespaces import LC


@dataclass
class Citation:
    document_id: str
    page: Optional[int]
    section: Optional[str]
    verbatim: Optional[str]
    rule_id: Optional[str]
    confidence: float = 1.0
    provision_urn: str = ""

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "page": self.page,
            "section": self.section,
            "verbatim": self.verbatim,
            "rule_id": self.rule_id,
            "confidence": self.confidence,
            "provision_urn": self.provision_urn,
        }


_CITATION_SPARQL = """\
PREFIX lc:  <urn:lc:>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?provisionUrn ?docId ?page ?section ?verbatim ?ruleRef ?confidence
WHERE {{
  ?entity lc:citesProvision ?provisionUrn .
  OPTIONAL {{ ?provisionUrn lc:fromDocument  ?docId     . }}
  OPTIONAL {{ ?provisionUrn lc:onPage        ?page      . }}
  OPTIONAL {{ ?provisionUrn lc:inSection     ?section   . }}
  OPTIONAL {{ ?provisionUrn lc:verbatimText  ?verbatim  . }}
  OPTIONAL {{ ?provisionUrn lc:refersToRule  ?ruleRef   . }}
  OPTIONAL {{ ?provisionUrn lc:confidence    ?confidence . }}
  VALUES ?entity {{ {entities} }}
}}
ORDER BY ?docId ?page
LIMIT 50
"""

_FINDING_CITATION_SPARQL = """\
PREFIX lc:  <urn:lc:>

SELECT ?provisionUrn ?docId ?page ?section ?verbatim ?ruleRef ?confidence
WHERE {{
  {{
    ?finding lc:forInstrument <{instrument_urn}> .
    ?finding lc:citesProvision ?provisionUrn .
  }} UNION {{
    <{instrument_urn}> lc:hasProvision ?provisionUrn .
  }}
  OPTIONAL {{ ?provisionUrn lc:fromDocument  ?docId     . }}
  OPTIONAL {{ ?provisionUrn lc:onPage        ?page      . }}
  OPTIONAL {{ ?provisionUrn lc:inSection     ?section   . }}
  OPTIONAL {{ ?provisionUrn lc:verbatimText  ?verbatim  . }}
  OPTIONAL {{ ?provisionUrn lc:refersToRule  ?ruleRef   . }}
  OPTIONAL {{ ?provisionUrn lc:confidence    ?confidence . }}
}}
ORDER BY ?docId ?page
LIMIT 30
"""


class CitationBuilder:
    def __init__(self) -> None:
        self._store = GraphStore.get()

    def from_instrument(self, instrument_urn: str) -> list[Citation]:
        """Return all citations associated with an instrument URN."""
        sparql = _FINDING_CITATION_SPARQL.format(instrument_urn=instrument_urn)
        rows = list(self._store.query(sparql))
        return [_row_to_citation(r) for r in rows if r]

    def from_entities(self, entity_urns: list[str]) -> list[Citation]:
        """Return citations for a list of entity URNs."""
        if not entity_urns:
            return []
        values = " ".join(f"<{u}>" for u in entity_urns)
        sparql = _CITATION_SPARQL.format(entities=values)
        rows = list(self._store.query(sparql))
        return [_row_to_citation(r) for r in rows if r]

    def deduplicate(self, citations: list[Citation]) -> list[Citation]:
        """Remove duplicate citations by (document_id, page, section)."""
        seen: set[tuple] = set()
        result: list[Citation] = []
        for c in citations:
            key = (c.document_id, c.page, c.section)
            if key not in seen:
                seen.add(key)
                result.append(c)
        return result

    def top_n(self, citations: list[Citation], n: int = 5) -> list[Citation]:
        """Return top-N citations sorted by confidence descending."""
        return sorted(citations, key=lambda c: c.confidence, reverse=True)[:n]


def _row_to_citation(row) -> Citation:
    def _str(val) -> Optional[str]:
        return str(val) if val is not None else None

    def _int(val) -> Optional[int]:
        try:
            return int(str(val)) if val is not None else None
        except (ValueError, TypeError):
            return None

    def _float(val) -> float:
        try:
            return float(str(val)) if val is not None else 1.0
        except (ValueError, TypeError):
            return 1.0

    return Citation(
        provision_urn=_str(row.provisionUrn) or "",
        document_id=_str(row.docId) or "unknown",
        page=_int(row.page),
        section=_str(row.section),
        verbatim=_str(row.verbatim),
        rule_id=_str(row.ruleRef),
        confidence=_float(row.confidence),
    )

