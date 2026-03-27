"""
FIBO-aligned OWL class and property declarations.
These are asserted into the graph at startup to enable OWL-RL reasoning.
The schema does NOT access data, answer questions, or contain business logic —
it is purely the type system and relationship definitions.
"""
from __future__ import annotations

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from ontology.namespaces import (
    EU_SEC, ERISA, OM, ISSUANCE, LC, FIBO_BE, FIBO_FBC, FIBO_SEC,
)


def assert_schema(g: Graph) -> None:
    """Assert all OWL class and property declarations into graph g."""
    _assert_core(g)
    _assert_eu_sec(g)
    _assert_erisa(g)
    _assert_om(g)
    _assert_issuance(g)


# ─── Core / citation layer ────────────────────────────────────────────────────

def _assert_core(g: Graph) -> None:
    triples = [
        # LC Core classes
        (LC.Document,     RDF.type,   OWL.Class),
        (LC.Provision,    RDF.type,   OWL.Class),
        (LC.Finding,      RDF.type,   OWL.Class),
        (LC.Citation,     RDF.type,   OWL.Class),
        (LC.RegulatoryRule, RDF.type, OWL.Class),

        # LC Core properties
        (LC.citesProvision, RDF.type,    OWL.ObjectProperty),
        (LC.citesProvision, RDFS.domain, LC.Finding),
        (LC.citesProvision, RDFS.range,  LC.Provision),

        (LC.containedInDocument, RDF.type,    OWL.ObjectProperty),
        (LC.containedInDocument, RDFS.domain, LC.Provision),
        (LC.containedInDocument, RDFS.range,  LC.Document),

        (LC.extractedFrom, RDF.type,    OWL.ObjectProperty),
        (LC.extractedFrom, RDFS.domain, LC.Finding),
        (LC.extractedFrom, RDFS.range,  LC.Document),

        (LC.governedBy,  RDF.type,    OWL.ObjectProperty),
        (LC.satisfies,   RDF.type,    OWL.ObjectProperty),
        (LC.satisfies,   RDFS.domain, LC.Finding),
        (LC.satisfies,   RDFS.range,  LC.RegulatoryRule),

        (LC.violates,    RDF.type,    OWL.ObjectProperty),
        (LC.violates,    RDFS.domain, LC.Finding),
        (LC.violates,    RDFS.range,  LC.RegulatoryRule),

        # Datatype properties for citations
        (LC.onPage,       RDF.type,  OWL.DatatypeProperty),
        (LC.inSection,    RDF.type,  OWL.DatatypeProperty),
        (LC.verbatim,     RDF.type,  OWL.DatatypeProperty),
        (LC.confidence,   RDF.type,  OWL.DatatypeProperty),
        (LC.findingType,  RDF.type,  OWL.DatatypeProperty),
        (LC.riskLevel,    RDF.type,  OWL.DatatypeProperty),
        (LC.ruleId,       RDF.type,  OWL.DatatypeProperty),
    ]
    for s, p, o in triples:
        g.add((s, p, o))


# ─── EU Securitization ────────────────────────────────────────────────────────

def _assert_eu_sec(g: Graph) -> None:
    triples = [
        # Classes
        (EU_SEC.Securitization,       RDF.type,       OWL.Class),
        (EU_SEC.Securitization,       RDFS.subClassOf, FIBO_SEC.Security),
        (EU_SEC.RetentionObligation,  RDF.type,       OWL.Class),
        (EU_SEC.TransparencyReport,   RDF.type,       OWL.Class),
        (EU_SEC.Prospectus,           RDF.type,       OWL.Class),
        (EU_SEC.Originator,           RDF.type,       OWL.Class),
        (EU_SEC.Originator,           RDFS.subClassOf, FIBO_BE.LegalEntity),
        (EU_SEC.SpecialPurposeVehicle, RDF.type,      OWL.Class),
        (EU_SEC.SpecialPurposeVehicle, RDFS.subClassOf, FIBO_BE.LegalEntity),

        # Object properties
        (EU_SEC.hasOriginator,   RDF.type,    OWL.ObjectProperty),
        (EU_SEC.hasOriginator,   RDFS.domain, EU_SEC.Securitization),
        (EU_SEC.hasOriginator,   RDFS.range,  EU_SEC.Originator),

        (EU_SEC.hasSPV,          RDF.type,    OWL.ObjectProperty),
        (EU_SEC.hasSPV,          RDFS.domain, EU_SEC.Securitization),
        (EU_SEC.hasSPV,          RDFS.range,  EU_SEC.SpecialPurposeVehicle),

        (EU_SEC.hasProspectus,   RDF.type,    OWL.ObjectProperty),
        (EU_SEC.hasProspectus,   RDFS.domain, EU_SEC.Securitization),
        (EU_SEC.hasProspectus,   RDFS.range,  EU_SEC.Prospectus),

        (EU_SEC.appliesTo,       RDF.type,    OWL.ObjectProperty),
        (EU_SEC.appliesTo,       RDFS.domain, EU_SEC.RetentionObligation),
        (EU_SEC.appliesTo,       RDFS.range,  EU_SEC.Securitization),

        (EU_SEC.hasTranche,      RDF.type,    OWL.ObjectProperty),

        # Datatype properties
        (EU_SEC.isin,             RDF.type, OWL.DatatypeProperty),
        (EU_SEC.cusip,            RDF.type, OWL.DatatypeProperty),
        (EU_SEC.secType,          RDF.type, OWL.DatatypeProperty),
        (EU_SEC.retentionPct,     RDF.type, OWL.DatatypeProperty),
        (EU_SEC.retentionMethod,  RDF.type, OWL.DatatypeProperty),
        (EU_SEC.jurisdiction,     RDF.type, OWL.DatatypeProperty),
        (EU_SEC.lei,              RDF.type, OWL.DatatypeProperty),

        # OWL restriction: every Securitization has at most one Prospectus
        # (soft constraint — reasoner will flag missing prospectus via SPARQL)
        (EU_SEC.hasProspectus,  RDF.type,   OWL.FunctionalProperty),
    ]
    for s, p, o in triples:
        g.add((s, p, o))


# ─── ERISA ────────────────────────────────────────────────────────────────────

def _assert_erisa(g: Graph) -> None:
    triples = [
        (ERISA.ERISAPlan,              RDF.type, OWL.Class),
        (ERISA.PlanFiduciary,          RDF.type, OWL.Class),
        (ERISA.PlanFiduciary,          RDFS.subClassOf, FIBO_BE.LegalEntity),
        (ERISA.ProhibitedTransaction,  RDF.type, OWL.Class),
        (ERISA.ERISARestrictedAsset,   RDF.type, OWL.Class),
        (ERISA.ExemptionCertificate,   RDF.type, OWL.Class),

        # Object properties
        (ERISA.managedBy,             RDF.type,    OWL.ObjectProperty),
        (ERISA.managedBy,             RDFS.domain, ERISA.ERISAPlan),
        (ERISA.managedBy,             RDFS.range,  ERISA.PlanFiduciary),

        (ERISA.involves,              RDF.type,    OWL.ObjectProperty),
        (ERISA.involves,              RDFS.domain, ERISA.ProhibitedTransaction),
        (ERISA.involves,              RDFS.range,  ERISA.ERISARestrictedAsset),

        (ERISA.hasRestriction,        RDF.type,    OWL.ObjectProperty),

        (ERISA.grantsExemptionFor,    RDF.type,    OWL.ObjectProperty),
        (ERISA.grantsExemptionFor,    RDFS.domain, ERISA.ExemptionCertificate),
        (ERISA.grantsExemptionFor,    RDFS.range,  ERISA.ProhibitedTransaction),

        # Datatype properties
        (ERISA.planType,             RDF.type, OWL.DatatypeProperty),
        (ERISA.planAssets,           RDF.type, OWL.DatatypeProperty),
        (ERISA.ptCode,               RDF.type, OWL.DatatypeProperty),
        (ERISA.exemptionCode,        RDF.type, OWL.DatatypeProperty),
        (ERISA.exemptionType,        RDF.type, OWL.DatatypeProperty),
        (ERISA.expiryDate,           RDF.type, OWL.DatatypeProperty),
        (ERISA.restrictionBasis,     RDF.type, OWL.DatatypeProperty),
    ]
    for s, p, o in triples:
        g.add((s, p, o))


# ─── Offering Memorandum ──────────────────────────────────────────────────────

def _assert_om(g: Graph) -> None:
    triples = [
        (OM.OfferingMemorandum, RDF.type, OWL.Class),
        (OM.EconomicTerms,      RDF.type, OWL.Class),
        (OM.FeeSchedule,        RDF.type, OWL.Class),
        (OM.RiskFactor,         RDF.type, OWL.Class),
        (OM.Covenant,           RDF.type, OWL.Class),

        (OM.describes,         RDF.type,    OWL.ObjectProperty),
        (OM.describes,         RDFS.domain, OM.OfferingMemorandum),

        (OM.termsOf,           RDF.type,    OWL.ObjectProperty),
        (OM.termsOf,           RDFS.domain, OM.EconomicTerms),

        (OM.disclosedIn,       RDF.type,    OWL.ObjectProperty),
        (OM.disclosedIn,       RDFS.domain, OM.RiskFactor),
        (OM.disclosedIn,       RDFS.range,  OM.OfferingMemorandum),

        (OM.bindingOn,         RDF.type,    OWL.ObjectProperty),
        (OM.bindingOn,         RDFS.domain, OM.Covenant),

        # Datatype properties
        (OM.omDate,          RDF.type, OWL.DatatypeProperty),
        (OM.issuerLEI,       RDF.type, OWL.DatatypeProperty),
        (OM.effectiveDate,   RDF.type, OWL.DatatypeProperty),
        (OM.couponRate,      RDF.type, OWL.DatatypeProperty),
        (OM.maturityDate,    RDF.type, OWL.DatatypeProperty),
        (OM.callSchedule,    RDF.type, OWL.DatatypeProperty),
        (OM.managementFee,   RDF.type, OWL.DatatypeProperty),
        (OM.performanceFee,  RDF.type, OWL.DatatypeProperty),
        (OM.redemptionFee,   RDF.type, OWL.DatatypeProperty),
        (OM.riskType,        RDF.type, OWL.DatatypeProperty),
        (OM.severity,        RDF.type, OWL.DatatypeProperty),
        (OM.covenantType,    RDF.type, OWL.DatatypeProperty),
        (OM.threshold,       RDF.type, OWL.DatatypeProperty),
    ]
    for s, p, o in triples:
        g.add((s, p, o))


# ─── New Issuance ─────────────────────────────────────────────────────────────

def _assert_issuance(g: Graph) -> None:
    triples = [
        (ISSUANCE.SecuritySetupRequest,  RDF.type, OWL.Class),
        (ISSUANCE.ReadinessIndicator,    RDF.type, OWL.Class),
        (ISSUANCE.ComplianceClearance,   RDF.type, OWL.Class),

        (ISSUANCE["for"],      RDF.type,    OWL.ObjectProperty),
        (ISSUANCE["for"],      RDFS.domain, ISSUANCE.SecuritySetupRequest),

        (ISSUANCE.assessedFor, RDF.type,    OWL.ObjectProperty),
        (ISSUANCE.assessedFor, RDFS.domain, ISSUANCE.ReadinessIndicator),
        (ISSUANCE.assessedFor, RDFS.range,  ISSUANCE.SecuritySetupRequest),

        (ISSUANCE.clears,      RDF.type,    OWL.ObjectProperty),
        (ISSUANCE.clears,      RDFS.domain, ISSUANCE.ComplianceClearance),
        (ISSUANCE.clears,      RDFS.range,  ISSUANCE.SecuritySetupRequest),

        (ISSUANCE.requestDate,     RDF.type, OWL.DatatypeProperty),
        (ISSUANCE.requestor,       RDF.type, OWL.DatatypeProperty),
        (ISSUANCE.workflowStatus,  RDF.type, OWL.DatatypeProperty),
        (ISSUANCE.euSecReady,      RDF.type, OWL.DatatypeProperty),
        (ISSUANCE.erisaReady,      RDF.type, OWL.DatatypeProperty),
        (ISSUANCE.omComplete,      RDF.type, OWL.DatatypeProperty),
        (ISSUANCE.clearanceDate,   RDF.type, OWL.DatatypeProperty),
        (ISSUANCE.clearedBy,       RDF.type, OWL.DatatypeProperty),
    ]
    for s, p, o in triples:
        g.add((s, p, o))
