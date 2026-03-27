"""
Named SPARQL queries for the knowledge graph.
All traversal logic lives here — agents call these by name, not raw SPARQL.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from rdflib import URIRef, Literal
from rdflib.namespace import RDF

from ontology.graph_store import GraphStore
from ontology.namespaces import (
    EU_SEC, ERISA, OM, ISSUANCE, LC, FIBO_BE, FIBO_SEC,
    INST_INSTRUMENT, INST_ENTITY, INST_PROVISION, INST_FINDING, INST_DOCUMENT,
)

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _store() -> GraphStore:
    return GraphStore.get()


def _rows(result) -> list[dict]:
    return [
        {str(var): str(row[var]) if row[var] is not None else None
         for var in result.vars}
        for row in result
    ]


# ─── Entity discovery ─────────────────────────────────────────────────────────

def find_entities_by_type(entity_type: str) -> list[dict]:
    """Return all instances of a given entity_type label (Instrument, Issuer, etc.)."""
    type_map = {
        "instrument": EU_SEC.Securitization,
        "securitization": EU_SEC.Securitization,
        "issuer": EU_SEC.Originator,
        "spv": EU_SEC.SpecialPurposeVehicle,
        "erisa_plan": ERISA.ERISAPlan,
        "offering_memorandum": OM.OfferingMemorandum,
        "setup_request": ISSUANCE.SecuritySetupRequest,
        "provision": LC.Provision,
        "finding": LC.Finding,
        "document": LC.Document,
    }
    rdf_type = type_map.get(entity_type.lower())
    if rdf_type is None:
        return []
    sparql = """
        SELECT ?entity ?label WHERE {
            ?entity rdf:type ?type .
            OPTIONAL { ?entity rdfs:label ?label }
        }
    """
    result = _store().query(sparql, initNs={"type": rdf_type})
    return _rows(result)


def find_entity_by_hint(hint: str) -> list[dict]:
    """
    Search for an entity by ISIN, name fragment, or URN.
    Returns matches ranked by exactness.
    """
    hint_lower = hint.lower()
    sparql = f"""
        SELECT ?entity ?type ?isin ?label ?secType WHERE {{
            ?entity rdf:type ?type .
            OPTIONAL {{ ?entity eu-sec:isin ?isin }}
            OPTIONAL {{ ?entity rdfs:label ?label }}
            OPTIONAL {{ ?entity eu-sec:secType ?secType }}
            FILTER (
                CONTAINS(LCASE(STR(?entity)), "{hint_lower}") ||
                CONTAINS(LCASE(STR(?isin)), "{hint_lower}") ||
                CONTAINS(LCASE(STR(?label)), "{hint_lower}")
            )
        }} LIMIT 10
    """
    return _rows(_store().query(sparql))


# ─── Instrument queries ───────────────────────────────────────────────────────

def get_instrument_detail(instrument_uri: str) -> dict:
    """Full detail for one instrument: attributes + issuer + tranches + ratings."""
    # Normalise: accept both urn:instrument: and urn:document:
    uuid = instrument_uri.split(":")[-1]
    inst_uri = f"urn:instrument:{uuid}"
    sparql = f"""
        SELECT ?predicate ?value WHERE {{
            <{inst_uri}> ?predicate ?value .
        }}
    """
    props = _rows(_store().query(sparql))

    sparql2 = f"""
        SELECT ?issuerUri ?issuerLabel ?lei ?jurisdiction WHERE {{
            <{instrument_uri}> eu-sec:hasOriginator ?issuerUri .
            OPTIONAL {{ ?issuerUri rdfs:label ?issuerLabel }}
            OPTIONAL {{ ?issuerUri eu-sec:lei ?lei }}
            OPTIONAL {{ ?issuerUri eu-sec:jurisdiction ?jurisdiction }}
        }}
    """
    issuers = _rows(_store().query(sparql2))

    sparql3 = f"""
        SELECT ?findingUri ?findingType ?riskLevel ?ruleId ?confidence WHERE {{
            ?findingUri lc:extractedFrom ?doc .
            <{instrument_uri}> eu-sec:hasOriginator ?issuer .
            ?findingUri lc:extractedFrom ?doc .
            OPTIONAL {{ ?findingUri lc:findingType ?findingType }}
            OPTIONAL {{ ?findingUri lc:riskLevel ?riskLevel }}
            OPTIONAL {{ ?findingUri lc:ruleId ?ruleId }}
            OPTIONAL {{ ?findingUri lc:confidence ?confidence }}
        }} LIMIT 20
    """

    sparql4 = f"""
        SELECT ?findingUri ?findingType ?riskLevel ?ruleId ?confidence WHERE {{
            ?findingUri rdf:type lc:Finding .
            OPTIONAL {{ ?findingUri lc:findingType ?findingType }}
            OPTIONAL {{ ?findingUri lc:riskLevel ?riskLevel }}
            OPTIONAL {{ ?findingUri lc:ruleId ?ruleId }}
            OPTIONAL {{ ?findingUri lc:confidence ?confidence }}
            FILTER (CONTAINS(STR(?findingUri), "{instrument_uri.split(':')[-1]}"))
        }} LIMIT 20
    """

    return {
        "uri": instrument_uri,
        "properties": props,
        "issuers": issuers,
    }


def get_instrument_findings(instrument_uri: str) -> list[dict]:
    """Return all findings linked to a document via lc:extractedFrom.

    Accepts either urn:instrument:{uuid} or urn:document:{uuid} — both map to
    the same document UUID so the query works either way.
    """
    # Normalise: instrument and document share the same UUID
    uuid = instrument_uri.split(":")[-1]
    doc_uri = f"urn:document:{uuid}"
    sparql = f"""
        SELECT ?finding ?findingType ?riskLevel ?ruleId ?confidence ?page ?section ?verbatim WHERE {{
            ?finding rdf:type lc:Finding ;
                     lc:extractedFrom <{doc_uri}> .
            OPTIONAL {{ ?finding lc:findingType ?findingType }}
            OPTIONAL {{ ?finding lc:riskLevel ?riskLevel }}
            OPTIONAL {{ ?finding lc:ruleId ?ruleId }}
            OPTIONAL {{ ?finding lc:confidence ?confidence }}
            OPTIONAL {{ ?finding lc:onPage ?page }}
            OPTIONAL {{ ?finding lc:inSection ?section }}
            OPTIONAL {{ ?finding lc:verbatim ?verbatim }}
        }} ORDER BY ?ruleId
    """
    return _rows(_store().query(sparql))


# ─── Citation chain ───────────────────────────────────────────────────────────

def get_citation_chain(finding_uri: str) -> list[dict]:
    """Return the full citation chain: finding → provisions → document."""
    sparql = f"""
        SELECT ?provision ?page ?section ?verbatim ?document ?confidence WHERE {{
            <{finding_uri}> lc:citesProvision ?provision .
            OPTIONAL {{ <{finding_uri}> lc:onPage ?page }}
            OPTIONAL {{ <{finding_uri}> lc:inSection ?section }}
            OPTIONAL {{ <{finding_uri}> lc:verbatim ?verbatim }}
            OPTIONAL {{ <{finding_uri}> lc:extractedFrom ?document }}
            OPTIONAL {{ <{finding_uri}> lc:confidence ?confidence }}
        }}
    """
    return _rows(_store().query(sparql))


# ─── Rule queries ─────────────────────────────────────────────────────────────

def get_findings_by_rule(rule_id: str) -> list[dict]:
    """All findings for a given rule category."""
    sparql = f"""
        SELECT ?finding ?findingType ?riskLevel ?confidence ?page ?section WHERE {{
            ?finding rdf:type lc:Finding .
            ?finding lc:ruleId "{rule_id}" .
            OPTIONAL {{ ?finding lc:findingType ?findingType }}
            OPTIONAL {{ ?finding lc:riskLevel ?riskLevel }}
            OPTIONAL {{ ?finding lc:confidence ?confidence }}
            OPTIONAL {{ ?finding lc:onPage ?page }}
            OPTIONAL {{ ?finding lc:inSection ?section }}
        }}
    """
    return _rows(_store().query(sparql))


def get_ingested_document_names() -> list[str]:
    """Return the rdfs:label of every lc:Document node in the graph.

    Used by the Ingest panel to mark which documents are already enriched.
    """
    sparql = """
        SELECT ?label WHERE {
            ?doc rdf:type lc:Document .
            ?doc rdfs:label ?label .
        }
    """
    rows = _rows(_store().query(sparql))
    return [r["label"] for r in rows if r.get("label")]


def get_non_compliant_findings() -> list[dict]:
    """All non-compliant findings across the graph."""
    sparql = """
        SELECT ?finding ?ruleId ?riskLevel ?confidence ?page ?section ?verbatim WHERE {
            ?finding rdf:type lc:Finding .
            ?finding lc:findingType "non_compliant" .
            OPTIONAL { ?finding lc:ruleId ?ruleId }
            OPTIONAL { ?finding lc:riskLevel ?riskLevel }
            OPTIONAL { ?finding lc:confidence ?confidence }
            OPTIONAL { ?finding lc:onPage ?page }
            OPTIONAL { ?finding lc:inSection ?section }
            OPTIONAL { ?finding lc:verbatim ?verbatim }
        } ORDER BY ?riskLevel
    """
    return _rows(_store().query(sparql))


# ─── ERISA queries ────────────────────────────────────────────────────────────

def get_erisa_restricted_instruments() -> list[dict]:
    """Instruments flagged as ERISA-restricted."""
    sparql = """
        SELECT ?instrument ?isin ?label ?restrictionBasis WHERE {
            ?instrument erisa:hasRestriction ?restriction .
            OPTIONAL { ?instrument eu-sec:isin ?isin }
            OPTIONAL { ?instrument rdfs:label ?label }
            OPTIONAL { ?restriction erisa:restrictionBasis ?restrictionBasis }
        }
    """
    return _rows(_store().query(sparql))


def check_erisa_exemption(instrument_uri: str) -> dict:
    """Check if an ERISA-restricted instrument has a valid exemption certificate."""
    sparql = f"""
        SELECT ?cert ?exemptionType ?expiryDate WHERE {{
            <{instrument_uri}> erisa:hasRestriction ?restriction .
            ?cert erisa:grantsExemptionFor ?pt .
            ?pt erisa:involves ?restriction .
            OPTIONAL {{ ?cert erisa:exemptionType ?exemptionType }}
            OPTIONAL {{ ?cert erisa:expiryDate ?expiryDate }}
        }}
    """
    rows = _rows(_store().query(sparql))
    return {"has_exemption": len(rows) > 0, "certificates": rows}


# ─── Subgraph for conversation context ───────────────────────────────────────

def get_compact_subgraph(entity_uri: str, depth: int = 2) -> dict:
    """
    Return a compact subgraph around an entity for LLM context injection.
    Limits to depth hops and the most relevant properties to stay ≤400 tokens.
    """
    sparql = f"""
        SELECT ?s ?p ?o WHERE {{
            {{
                <{entity_uri}> ?p ?o .
                BIND(<{entity_uri}> AS ?s)
            }} UNION {{
                ?s ?p <{entity_uri}> .
                BIND(<{entity_uri}> AS ?o)
            }} UNION {{
                <{entity_uri}> ?rel ?neighbor .
                ?neighbor ?p ?o .
                BIND(?neighbor AS ?s)
            }}
        }} LIMIT 60
    """
    rows = _rows(_store().query(sparql))
    # Format as compact, LLM-readable key-value
    facts = []
    seen = set()
    for row in rows:
        key = f"{_shorten(row.get('s',''))} {_shorten(row.get('p',''))} {_shorten(row.get('o',''))}"
        if key not in seen:
            facts.append(key)
            seen.add(key)
    return {"entity": entity_uri, "facts": facts[:50]}


def get_full_graph_json() -> dict:
    """Export graph as nodes+edges JSON for frontend visualization.

    Excludes low-value Provision nodes (they create hairballs).
    Uses rdfs:label where available for human-readable node names.
    """
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    # Only instance URN prefixes — exclude ontology class/property URNs (urn:legalcompliance:*)
    INSTANCE_PREFIXES = (
        "urn:document:", "urn:instrument:", "urn:entity:",
        "urn:tranche:", "urn:finding:", "urn:rating:",
    )
    EXCLUDED = ("urn:provision:",)

    # 1. Collect URI–URI edges (structural relationships)
    sparql = """
        SELECT ?s ?p ?o WHERE {
            ?s ?p ?o .
            FILTER (isURI(?s) && STRSTARTS(STR(?s), "urn:"))
            FILTER (isURI(?o) && STRSTARTS(STR(?o), "urn:"))
        } LIMIT 1000
    """
    for row in _store().query(sparql):
        s, p, o = str(row[0]), str(row[1]), str(row[2])
        # Only keep instance nodes — skip ontology class/property URNs
        if not any(s.startswith(px) for px in INSTANCE_PREFIXES): continue
        if not any(o.startswith(px) for px in INSTANCE_PREFIXES): continue
        if any(s.startswith(ex) for ex in EXCLUDED): continue
        if any(o.startswith(ex) for ex in EXCLUDED): continue
        if s not in nodes:
            nodes[s] = {"id": s, "label": _shorten(s), "type": _node_type(s)}
        if o not in nodes:
            nodes[o] = {"id": o, "label": _shorten(o), "type": _node_type(o)}
        edges.append({"source": s, "target": o, "relation": _shorten(p)})

    # 2a. Fetch rdfs:label for all instance nodes in a targeted query (no LIMIT issue)
    label_sparql = """
        SELECT ?s ?label WHERE {
            ?s rdfs:label ?label .
            FILTER (isURI(?s))
            FILTER (
                STRSTARTS(STR(?s), "urn:document:") ||
                STRSTARTS(STR(?s), "urn:instrument:") ||
                STRSTARTS(STR(?s), "urn:entity:") ||
                STRSTARTS(STR(?s), "urn:tranche:") ||
                STRSTARTS(STR(?s), "urn:finding:") ||
                STRSTARTS(STR(?s), "urn:rating:")
            )
        }
    """
    for row in _store().query(label_sparql):
        s, label = str(row[0]), str(row[1])
        if s not in nodes:
            nodes[s] = {"id": s, "label": str(label), "type": _node_type(s)}
        else:
            nodes[s]["label"] = str(label)

    # 2b. Enrich nodes with other literal properties (non-provision, limited)
    sparql2 = """
        SELECT ?s ?p ?o WHERE {
            ?s ?p ?o .
            FILTER (isURI(?s))
            FILTER (isLiteral(?o))
            FILTER (
                STRSTARTS(STR(?s), "urn:document:") ||
                STRSTARTS(STR(?s), "urn:instrument:") ||
                STRSTARTS(STR(?s), "urn:entity:") ||
                STRSTARTS(STR(?s), "urn:tranche:") ||
                STRSTARTS(STR(?s), "urn:finding:") ||
                STRSTARTS(STR(?s), "urn:rating:")
            )
            FILTER (STR(?p) != "http://www.w3.org/2000/01/rdf-schema#label")
        } LIMIT 2000
    """
    for row in _store().query(sparql2):
        s, p, o = str(row[0]), str(row[1]), str(row[2])
        if s not in nodes:
            nodes[s] = {"id": s, "label": _shorten(s), "type": _node_type(s)}
        key = _shorten(p)
        nodes[s][key] = str(o)

    # 3. Compose human-readable labels for Finding nodes from their literal properties.
    # Findings have no rdfs:label; build one from ruleId + findingType + riskLevel.
    # Keys use the _shorten() prefix form: "lc:ruleId", "lc:findingType", "lc:riskLevel"
    for n in nodes.values():
        if n.get("type") != "Finding":
            continue
        rule   = n.get("lc:ruleId", "")
        status = n.get("lc:findingType", "")
        risk   = n.get("lc:riskLevel", "")
        parts = []
        if rule:
            parts.append(rule.replace("_", " ").title())
        if status:
            if status == "compliant":
                parts.append("✓")
            elif status == "non_compliant":
                parts.append("✗")
            else:
                parts.append(status)
        if risk == "high":
            parts.append("⚠")
        if parts:
            n["label"] = " · ".join(parts)

    # 4. Assign visual weight (val) by node type so instruments appear larger
    TYPE_VAL = {
        "Instrument": 12, "Document": 10, "Issuer": 8,
        "Finding": 5, "Tranche": 4, "Rule": 4, "Other": 3,
    }
    for n in nodes.values():
        n["val"] = TYPE_VAL.get(n["type"], 3)

    return {"nodes": list(nodes.values()), "edges": edges}


# ─── Private helpers ──────────────────────────────────────────────────────────

def _shorten(uri: str) -> str:
    """Produce a readable short name from a URI."""
    for prefix, ns in {
        "urn:legalcompliance:eu-sec:": "eu-sec:",
        "urn:legalcompliance:erisa:": "erisa:",
        "urn:legalcompliance:om:": "om:",
        "urn:legalcompliance:issuance:": "issuance:",
        "urn:legalcompliance:core:": "lc:",
        "urn:instrument:": "inst:",
        "urn:entity:": "entity:",
        "urn:provision:": "prov:",
        "urn:finding:": "finding:",
        "urn:document:": "doc:",
        "https://spec.edmcouncil.org/fibo/ontology/": "fibo:",
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
        "http://www.w3.org/2000/01/rdf-schema#": "rdfs:",
        "http://www.w3.org/2002/07/owl#": "owl:",
    }.items():
        if uri.startswith(prefix):
            return ns + uri[len(prefix):]
    return uri.split("/")[-1].split("#")[-1]


def _node_type(uri: str) -> str:
    if uri.startswith("urn:instrument:"): return "Instrument"
    if uri.startswith("urn:entity:"):     return "Issuer"
    if uri.startswith("urn:tranche:"):    return "Tranche"
    if uri.startswith("urn:rating:"):     return "Rating"
    if uri.startswith("urn:provision:"):  return "Provision"
    if uri.startswith("urn:finding:"):    return "Finding"
    if uri.startswith("urn:document:"):   return "Document"
    if uri.startswith("urn:rule:"):       return "Rule"
    return "Other"
