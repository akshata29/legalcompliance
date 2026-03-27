"""
Enrichment layer — converts ProcessingSession facts into RDF triples.
After processing a document through the existing pipeline, this module
mints RDF URIs and asserts instrument/issuer/finding/citation triples
into the GraphStore.

Also contains a compact LLM-based entity extractor that identifies
financial instrument metadata from provision text.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any, Optional

from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from ontology.graph_store import GraphStore
from ontology.namespaces import (
    EU_SEC, ERISA, OM, ISSUANCE, LC, FIBO_BE,
    INST_INSTRUMENT, INST_ENTITY, INST_PROVISION, INST_FINDING, INST_DOCUMENT,
)

logger = logging.getLogger(__name__)


# ─── URI minting ──────────────────────────────────────────────────────────────

def _uri(base: str, key: str) -> URIRef:
    """Mint a stable URN for an instance."""
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", key)
    return URIRef(base + safe)


def _instrument_uri(doc_id: str) -> URIRef:
    return _uri(INST_INSTRUMENT, doc_id)


def _document_uri(doc_id: str) -> URIRef:
    return _uri(INST_DOCUMENT, doc_id)


def _provision_uri(provision_id: str) -> URIRef:
    return _uri(INST_PROVISION, provision_id)


def _finding_uri(clause_id: str) -> URIRef:
    return _uri(INST_FINDING, clause_id)


def _entity_uri(name: str) -> URIRef:
    return _uri(INST_ENTITY, name)


# ─── Namespace-aware instrument factory ──────────────────────────────────────

def _instrument_triples(inst_uri, doc_uri, doc_name: str) -> list[tuple]:
    """Return RDF triples for the instrument node, typed by document namespace."""
    name = doc_name.lower()
    label = Literal(doc_name.replace(".txt", "").replace("_", " "))
    if "erisa" in name:
        return [
            (inst_uri, RDF.type,         ERISA.ERISAPlan),
            (inst_uri, RDFS.label,       label),
            (inst_uri, ERISA.planType,   Literal("401k_DB")),
            (inst_uri, LC["governedBy"], LC.RegulatoryRule),
            (doc_uri,  LC.hasInstrument, inst_uri),
            (inst_uri, LC.extractedFrom, doc_uri),
        ]
    elif name.startswith("om_") or "_om_" in name:
        return [
            (inst_uri, RDF.type,             OM.OfferingMemorandum),
            (inst_uri, RDFS.label,           label),
            (inst_uri, OM["fundType"],       Literal("private_credit")),
            (inst_uri, LC["governedBy"],     LC.RegulatoryRule),
            (doc_uri,  LC.hasInstrument,     inst_uri),
            (inst_uri, LC.extractedFrom,     doc_uri),
        ]
    elif "issuance" in name:
        return [
            (inst_uri, RDF.type,                  ISSUANCE.SecuritySetupRequest),
            (inst_uri, RDFS.label,                label),
            (inst_uri, ISSUANCE["setupType"],     Literal("public_offering")),
            (inst_uri, LC["governedBy"],          LC.RegulatoryRule),
            (doc_uri,  LC.hasInstrument,          inst_uri),
            (inst_uri, LC.extractedFrom,          doc_uri),
        ]
    else:
        return [
            (inst_uri, RDF.type,             EU_SEC.Securitization),
            (inst_uri, RDFS.label,           label),
            (inst_uri, EU_SEC.secType,       Literal("CLO")),
            (inst_uri, EU_SEC["governedBy"], LC.RegulatoryRule),
            (doc_uri,  LC.hasInstrument,     inst_uri),
            (inst_uri, LC.extractedFrom,     doc_uri),
        ]


# ─── Session → RDF triples ────────────────────────────────────────────────────

async def enrich_from_session(session_dict: dict) -> int:
    """
    Convert a ProcessingSession (as dict) into RDF triples and add to GraphStore.
    Returns the number of new triples added.
    """
    store = GraphStore.get()
    triples: list[tuple] = []

    doc_id = session_dict.get("document_id", "unknown")
    doc_name = session_dict.get("document_name", doc_id)

    doc_uri = _document_uri(doc_id)
    inst_uri = _instrument_uri(doc_id)

    # ── Document node ─────────────────────────────────────────────────────────
    triples += [
        (doc_uri, RDF.type,   LC.Document),
        (doc_uri, RDFS.label, Literal(doc_name)),
        (doc_uri, LC.ruleId,  Literal(doc_id)),
    ]

    # ── Instrument node (one per document, typed by namespace) ───────────────
    triples += _instrument_triples(inst_uri, doc_uri, doc_name)

    # ── Provision nodes ───────────────────────────────────────────────────────
    for prov in session_dict.get("provisions", []):
        prov_id = prov.get("provision_id", "")
        prov_uri = _provision_uri(prov_id)
        text = prov.get("provision_text", "")  # store full text
        triples += [
            (prov_uri, RDF.type,              LC.Provision),
            (prov_uri, LC.containedInDocument, doc_uri),
            (prov_uri, LC.verbatim,           Literal(text)),
        ]

    # ── Finding nodes (from clauses + findings) ───────────────────────────────
    findings_by_clause: dict[str, dict] = {}
    for f in session_dict.get("findings", []):
        findings_by_clause[f.get("clause_id", "")] = f

    for clause in session_dict.get("clauses", []):
        clause_id = clause.get("clause_id", "")
        finding = findings_by_clause.get(clause_id, {})
        finding_uri = _finding_uri(clause_id)
        prov_uri = _provision_uri(clause.get("provision_id", ""))

        triples += [
            (finding_uri, RDF.type,           LC.Finding),
            (finding_uri, LC.citesProvision,  prov_uri),
            (finding_uri, LC.extractedFrom,   doc_uri),
            (finding_uri, LC.ruleId,          Literal(clause.get("rule_category", ""))),
            (finding_uri, LC.verbatim,        Literal(clause.get("clause_text", ""))),  # no truncation, ranked at query time
        ]
        if finding:
            f_type = finding.get("finding", "unknown")
            triples += [
                (finding_uri, LC.findingType, Literal(f_type)),
                (finding_uri, LC.riskLevel,   Literal(finding.get("risk_level", "medium"))),
                (finding_uri, LC.confidence,  Literal(str(0.9), datatype=XSD.decimal)),
            ]
            # Wire satisfies / violates
            if f_type == "compliant":
                rule_uri = _uri("urn:rule:", clause.get("rule_category", ""))
                triples.append((finding_uri, LC.satisfies, rule_uri))
            elif f_type == "non_compliant":
                rule_uri = _uri("urn:rule:", clause.get("rule_category", ""))
                triples.append((finding_uri, LC.violates, rule_uri))

            # Page/section from provision text if available
            prov_text = clause.get("clause_text", "")
            page_match = re.search(r"[Pp]age\s+(\d+)", prov_text)
            if page_match:
                triples.append((finding_uri, LC.onPage, Literal(int(page_match.group(1)), datatype=XSD.integer)))

    added = await store.add_triples(triples, run_reasoner=False, persist=True)
    logger.info("Enriched session %s: %d new triples added", doc_id, added)
    return {
        "triples_added": added,
        "instruments_found": 1,
        "provisions_enriched": len(session_dict.get("provisions", [])),
        "findings_enriched": len(session_dict.get("findings", [])),
    }


def enrich_from_session_sync(session_dict: dict) -> int:
    """Synchronous variant for startup pre-loading of existing sessions."""
    store = GraphStore.get()
    triples: list[tuple] = []

    doc_id = session_dict.get("document_id", "unknown")
    doc_name = session_dict.get("document_name", doc_id)
    doc_uri = _document_uri(doc_id)
    inst_uri = _instrument_uri(doc_id)

    triples += [
        (doc_uri, RDF.type,   LC.Document),
        (doc_uri, RDFS.label, Literal(doc_name)),
        (doc_uri, LC.ruleId,  Literal(doc_id)),
    ]
    triples += _instrument_triples(inst_uri, doc_uri, doc_name)

    for prov in session_dict.get("provisions", []):
        prov_uri = _provision_uri(prov.get("provision_id", ""))
        triples += [
            (prov_uri, RDF.type, LC.Provision),
            (prov_uri, LC.containedInDocument, doc_uri),
            (prov_uri, LC.verbatim, Literal(prov.get("provision_text", "")[:500])),
        ]

    findings_map = {f.get("clause_id", ""): f for f in session_dict.get("findings", [])}
    for clause in session_dict.get("clauses", []):
        clause_id = clause.get("clause_id", "")
        finding = findings_map.get(clause_id, {})
        finding_uri = _finding_uri(clause_id)
        prov_uri = _provision_uri(clause.get("provision_id", ""))
        triples += [
            (finding_uri, RDF.type,          LC.Finding),
            (finding_uri, LC.citesProvision, prov_uri),
            (finding_uri, LC.extractedFrom,  doc_uri),
            (finding_uri, LC.ruleId,         Literal(clause.get("rule_category", ""))),
        ]
        if finding:
            triples += [
                (finding_uri, LC.findingType, Literal(finding.get("finding", "unknown"))),
                (finding_uri, LC.riskLevel,   Literal(finding.get("risk_level", "medium"))),
            ]

    return store.add_triples_sync(triples, run_reasoner=False, persist=True)
