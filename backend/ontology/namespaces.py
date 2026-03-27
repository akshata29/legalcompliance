"""
All RDF namespace definitions used across the ontology.
FIBO-aligned application namespaces for EU Sec, ERISA, OM, and New Issuance.
"""
from __future__ import annotations

from rdflib import Namespace
from rdflib.namespace import RDF, RDFS, OWL, XSD

# ── FIBO Core (subset we reference by URI, not imported as full OWL) ──────────
FIBO_FBC  = Namespace("https://spec.edmcouncil.org/fibo/ontology/FBC/")
FIBO_BE   = Namespace("https://spec.edmcouncil.org/fibo/ontology/BE/")
FIBO_SEC  = Namespace("https://spec.edmcouncil.org/fibo/ontology/SEC/")
FIBO_FND  = Namespace("https://spec.edmcouncil.org/fibo/ontology/FND/")
FIBO_LAW  = Namespace("https://spec.edmcouncil.org/fibo/ontology/FND/Law/")

# ── Application-level namespaces (FIBO-aligned local extensions) ──────────────
EU_SEC    = Namespace("urn:legalcompliance:eu-sec:")
ERISA     = Namespace("urn:legalcompliance:erisa:")
OM        = Namespace("urn:legalcompliance:om:")
ISSUANCE  = Namespace("urn:legalcompliance:issuance:")
LC        = Namespace("urn:legalcompliance:core:")

# ── Instance URN bases (minted at enrichment time) ────────────────────────────
INST_INSTRUMENT  = "urn:instrument:"
INST_ENTITY      = "urn:entity:"
INST_TRANCHE     = "urn:tranche:"
INST_RATING      = "urn:rating:"
INST_PROVISION   = "urn:provision:"
INST_FINDING     = "urn:finding:"
INST_DOCUMENT    = "urn:document:"
INST_RULE        = "urn:rule:"

# ── Prefix map for serialization ─────────────────────────────────────────────
PREFIX_MAP: dict[str, str] = {
    "rdf":       str(RDF),
    "rdfs":      str(RDFS),
    "owl":       str(OWL),
    "xsd":       str(XSD),
    "fibo-fbc":  str(FIBO_FBC),
    "fibo-be":   str(FIBO_BE),
    "fibo-sec":  str(FIBO_SEC),
    "fibo-fnd":  str(FIBO_FND),
    "fibo-law":  str(FIBO_LAW),
    "eu-sec":    str(EU_SEC),
    "erisa":     str(ERISA),
    "om":        str(OM),
    "issuance":  str(ISSUANCE),
    "lc":        str(LC),
}
