"""
Synthetic instrument graph generator.
Populates the RDF graph store with demo instruments, issuers, tranches,
ratings, findings, and readiness indicators so the UI works out-of-the-box
without needing a real document processing run.

Run standalone:  python -m data.synthetic.instruments_graph
Or import:       from data.synthetic.instruments_graph import seed_graph
"""
from __future__ import annotations

import sys
import os
# Allow running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from ontology.graph_store import GraphStore
from ontology.namespaces import (
    EU_SEC, ERISA, OM, ISSUANCE, LC, FIBO_BE,
)

# ─── Synthetic data definitions ───────────────────────────────────────────────

INSTRUMENTS = [
    {
        "id": "CLO-2024-01", "isin": "XS1234567890", "type": "CLO",
        "label": "Alpine CLO 2024-01 Ltd",
        "issuer": {"id": "AlpineSPV-SA", "label": "Alpine SPV S.A.", "lei": "549300ABCDEF123456", "jurisdiction": "LU"},
        "retention_pct": 0.05, "retention_method": "vertical_slice",
        "sts": True, "erisa_restricted": True,
        "tranches": [
            {"id": "T-A1", "class": "Senior",     "attach": 0.0,  "detach": 0.65},
            {"id": "T-B",  "class": "Mezzanine",  "attach": 0.65, "detach": 0.80},
            {"id": "T-C",  "class": "Junior",     "attach": 0.80, "detach": 0.90},
            {"id": "T-D",  "class": "Equity",     "attach": 0.90, "detach": 1.00},
        ],
        "findings": [
            {"rule": "RISK_RETENTION", "type": "compliant",     "risk": "low",    "page": 47, "section": "5.2", "confidence": 0.94,
             "verbatim": "The Issuer shall retain a material net economic interest of not less than 5% in accordance with Article 6."},
            {"rule": "TRANSPARENCY",   "type": "compliant",     "risk": "low",    "page": 52, "section": "6.1", "confidence": 0.91,
             "verbatim": "Quarterly investor reports shall be published on the designated repository within 15 days."},
            {"rule": "RISK_DISCLOSURE","type": "needs_review",  "risk": "medium", "page": 31, "section": "3.8", "confidence": 0.72,
             "verbatim": "Market risk factors include interest rate movements and credit spread volatility."},
        ],
    },
    {
        "id": "ABS-2024-02", "isin": "XS9876543210", "type": "ABS",
        "label": "Thames ABS 2024-02 PLC",
        "issuer": {"id": "ThamesSPV-Ltd", "label": "Thames SPV Ltd", "lei": "213800XYZABC789012", "jurisdiction": "GB"},
        "retention_pct": 0.05, "retention_method": "first_loss",
        "sts": False, "erisa_restricted": False,
        "tranches": [
            {"id": "ABS-T-A", "class": "Senior",   "attach": 0.0,  "detach": 0.70},
            {"id": "ABS-T-B", "class": "Mezzanine","attach": 0.70, "detach": 0.85},
            {"id": "ABS-T-C", "class": "Equity",   "attach": 0.85, "detach": 1.00},
        ],
        "findings": [
            {"rule": "RISK_RETENTION",  "type": "compliant",     "risk": "low",    "page": 38, "section": "4.1", "confidence": 0.96,
             "verbatim": "First loss position retained by originator constitutes the required 5% net economic interest."},
            {"rule": "DUE_DILIGENCE",   "type": "non_compliant", "risk": "high",   "page": 19, "section": "2.4", "confidence": 0.88,
             "verbatim": "Institutional investor due diligence obligations were partially documented."},
        ],
    },
    {
        "id": "RMBS-2024-03", "isin": "XS1122334455", "type": "RMBS",
        "label": "Nordic RMBS 2024-03 DAC",
        "issuer": {"id": "NordicDAC", "label": "Nordic Mortgage DAC", "lei": "635400NORDIC123456", "jurisdiction": "IE"},
        "retention_pct": 0.05, "retention_method": "random_portion",
        "sts": True, "erisa_restricted": False,
        "tranches": [
            {"id": "RMBS-T-A", "class": "Senior",   "attach": 0.0,  "detach": 0.75},
            {"id": "RMBS-T-B", "class": "Mezzanine","attach": 0.75, "detach": 0.88},
        ],
        "findings": [
            {"rule": "RISK_RETENTION",   "type": "compliant",  "risk": "low",    "page": 65, "section": "7.2", "confidence": 0.92,
             "verbatim": "Random portion retention method applied to 5.0% of the securitised exposures."},
            {"rule": "RECORD_KEEPING",   "type": "compliant",  "risk": "low",    "page": 72, "section": "8.1", "confidence": 0.89,
             "verbatim": "Servicer maintains complete loan-level data for the life of the transaction plus 5 years."},
        ],
    },
    {
        "id": "CLO-2024-04", "isin": "XS5566778899", "type": "CLO",
        "label": "Iberian CLO 2024-04 S.A.",
        "issuer": {"id": "IberianSPV-SA", "label": "Iberian SPV S.A.", "lei": "724500IBERIA789012", "jurisdiction": "ES"},
        "retention_pct": 0.03, "retention_method": "vertical_slice",
        "sts": False, "erisa_restricted": True,
        "tranches": [
            {"id": "ICLO-T-A1", "class": "Senior",  "attach": 0.0,  "detach": 0.60},
            {"id": "ICLO-T-A2", "class": "Senior",  "attach": 0.60, "detach": 0.72},
            {"id": "ICLO-T-B",  "class": "Mezzanine","attach": 0.72,"detach": 0.82},
        ],
        "findings": [
            {"rule": "RISK_RETENTION",  "type": "non_compliant", "risk": "high",   "page": 41, "section": "4.3", "confidence": 0.91,
             "verbatim": "The retained interest of 3% does not meet the minimum 5% requirement under Article 6(1) EU SR."},
            {"rule": "ERISA_SECTION_3", "type": "non_compliant", "risk": "critical","page": 18, "section": "2.1","confidence": 0.95,
             "verbatim": "This instrument is offered to ERISA plan investors without a valid exemption certificate on file."},
        ],
    },
    {
        "id": "ABS-2024-05", "isin": "XS3344556677", "type": "ABS",
        "label": "Adriatic SME ABS 2024-05",
        "issuer": {"id": "AdriaticSPV", "label": "Adriatic SPV S.r.l.", "lei": "815600ADRIATIC0123", "jurisdiction": "IT"},
        "retention_pct": 0.05, "retention_method": "originator_share",
        "sts": True, "erisa_restricted": False,
        "tranches": [
            {"id": "SME-T-A", "class": "Senior", "attach": 0.0,  "detach": 0.68},
            {"id": "SME-T-B", "class": "Junior", "attach": 0.68, "detach": 1.00},
        ],
        "findings": [
            {"rule": "RISK_RETENTION", "type": "compliant", "risk": "low", "page": 33, "section": "3.1", "confidence": 0.97,
             "verbatim": "Originator retains 5% of the nominal value of each securitised exposure on an ongoing basis."},
        ],
    },
]


def _u(base: str, key: str) -> URIRef:
    import re
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", key)
    return URIRef(base + safe)


def seed_graph() -> int:
    """Seed the GraphStore with all synthetic instruments. Returns triple count added."""
    store = GraphStore.get()
    triples: list[tuple] = []

    for inst in INSTRUMENTS:
        inst_uri   = _u("urn:instrument:", inst["id"])
        issuer_uri = _u("urn:entity:", inst["issuer"]["id"])
        doc_uri    = _u("urn:document:", inst["id"] + "_prospectus")

        # ── Instrument ────────────────────────────────────────────────────────
        triples += [
            (inst_uri, RDF.type,            EU_SEC.Securitization),
            (inst_uri, RDFS.label,          Literal(inst["label"])),
            (inst_uri, EU_SEC.isin,         Literal(inst["isin"])),
            (inst_uri, EU_SEC.secType,      Literal(inst["type"])),
            (inst_uri, EU_SEC.retentionPct, Literal(inst["retention_pct"], datatype=XSD.decimal)),
            (inst_uri, EU_SEC.retentionMethod, Literal(inst["retention_method"])),
            (inst_uri, EU_SEC.stsDesignated,   Literal(inst["sts"], datatype=XSD.boolean)),
            (inst_uri, EU_SEC.hasOriginator,   issuer_uri),
        ]

        # ── ERISA restriction ─────────────────────────────────────────────────
        if inst["erisa_restricted"]:
            triples.append((inst_uri, ERISA.hasRestriction, ERISA.ERISARestricted))

        # ── Issuer ────────────────────────────────────────────────────────────
        triples += [
            (issuer_uri, RDF.type,           EU_SEC.Originator),
            (issuer_uri, RDFS.label,         Literal(inst["issuer"]["label"])),
            (issuer_uri, EU_SEC.lei,         Literal(inst["issuer"]["lei"])),
            (issuer_uri, EU_SEC.jurisdiction,Literal(inst["issuer"]["jurisdiction"])),
        ]

        # ── Document ──────────────────────────────────────────────────────────
        triples += [
            (doc_uri, RDF.type,   LC.Document),
            (doc_uri, RDFS.label, Literal(f"{inst['label']} Prospectus")),
            (inst_uri, EU_SEC.hasProspectus, doc_uri),
        ]

        # ── Tranches ──────────────────────────────────────────────────────────
        for tr in inst["tranches"]:
            tr_uri = _u("urn:tranche:", inst["id"] + "_" + tr["id"])
            triples += [
                (tr_uri, RDF.type,           EU_SEC.Tranche),
                (tr_uri, RDFS.label,         Literal(f"{inst['id']} {tr['class']} ({tr['id']})")),
                (tr_uri, EU_SEC.trancheClass, Literal(tr["class"])),
                (tr_uri, EU_SEC.attachmentPt, Literal(tr["attach"], datatype=XSD.decimal)),
                (tr_uri, EU_SEC.detachmentPt, Literal(tr["detach"], datatype=XSD.decimal)),
                (inst_uri, EU_SEC.hasTranche, tr_uri),
            ]

        # ── Findings + Provisions ─────────────────────────────────────────────
        for i, f in enumerate(inst["findings"]):
            prov_id    = f"{inst['id']}_PROV_{i+1:03d}"
            clause_id  = f"{inst['id']}_CLAUSE_{i+1:03d}"
            prov_uri   = _u("urn:provision:", prov_id)
            finding_uri = _u("urn:finding:", clause_id)

            triples += [
                (prov_uri, RDF.type,              LC.Provision),
                (prov_uri, LC.containedInDocument, doc_uri),
                (prov_uri, LC.verbatim,            Literal(f["verbatim"])),
                (prov_uri, LC.onPage,              Literal(f["page"], datatype=XSD.integer)),
                (prov_uri, LC.inSection,           Literal(f["section"])),

                (finding_uri, RDF.type,           LC.Finding),
                (finding_uri, LC.citesProvision,  prov_uri),
                (finding_uri, LC.extractedFrom,   doc_uri),
                (finding_uri, LC.ruleId,          Literal(f["rule"])),
                (finding_uri, LC.findingType,     Literal(f["type"])),
                (finding_uri, LC.riskLevel,       Literal(f["risk"])),
                (finding_uri, LC.confidence,      Literal(str(f["confidence"]), datatype=XSD.decimal)),
                (finding_uri, LC.onPage,          Literal(f["page"], datatype=XSD.integer)),
                (finding_uri, LC.inSection,       Literal(f["section"])),
                (finding_uri, LC.verbatim,        Literal(f["verbatim"])),
            ]
            if f["type"] == "compliant":
                rule_uri = _u("urn:rule:", f["rule"])
                triples.append((finding_uri, LC.satisfies, rule_uri))
            elif f["type"] == "non_compliant":
                rule_uri = _u("urn:rule:", f["rule"])
                triples.append((finding_uri, LC.violates, rule_uri))

        # ── Readiness indicator ───────────────────────────────────────────────
        req_uri = _u("urn:issuance:", inst["id"] + "_setup")
        ri_uri  = _u("urn:issuance:", inst["id"] + "_readiness")
        non_compliant_count = sum(1 for f in inst["findings"] if f["type"] == "non_compliant")
        eu_ready   = non_compliant_count == 0
        erisa_ready = not inst["erisa_restricted"] or non_compliant_count == 0

        triples += [
            (req_uri, RDF.type,               ISSUANCE.SecuritySetupRequest),
            (req_uri, RDFS.label,             Literal(f"Setup: {inst['label']}")),
            (req_uri, ISSUANCE["for"],        inst_uri),
            (req_uri, ISSUANCE.workflowStatus,Literal("in_review" if non_compliant_count > 0 else "cleared")),

            (ri_uri, RDF.type,           ISSUANCE.ReadinessIndicator),
            (ri_uri, ISSUANCE.assessedFor, req_uri),
            (ri_uri, ISSUANCE.euSecReady,  Literal(eu_ready, datatype=XSD.boolean)),
            (ri_uri, ISSUANCE.erisaReady,  Literal(erisa_ready, datatype=XSD.boolean)),
            (ri_uri, ISSUANCE.omComplete,  Literal(True, datatype=XSD.boolean)),
        ]

    added = store.add_triples_sync(triples, run_reasoner=True, persist=True)
    print(f"Seeded {added} triples into graph store ({store.count()} total).")
    return added


if __name__ == "__main__":
    seed_graph()
