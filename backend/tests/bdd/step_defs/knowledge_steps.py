"""
BDD Step Definitions — Knowledge Graph / Rule Evaluation
Covers: eu_sec_retention.feature, erisa_restriction.feature, om_extraction.feature
"""
from __future__ import annotations

from datetime import date

import pytest
from pytest_bdd import given, then, when, parsers
from rdflib import Literal, URIRef
from rdflib.namespace import XSD

from backend.ontology.graph_store import GraphStore
from backend.ontology.namespaces import LC, EU_SEC, ERISA, OM, XSDNS
from backend.rules.rule_evaluator import RuleEvaluator
from backend.rules.rule_registry import get_registry

# ── Shared state (per-scenario) ───────────────────────────────────────────────

@pytest.fixture
def ctx() -> dict:
    """Mutable context dict shared across steps in one scenario."""
    return {}


# ── Background ────────────────────────────────────────────────────────────────

@given("the knowledge graph is initialised with FIBO schema")
def init_graph(ctx) -> None:
    store = GraphStore.get()
    assert store is not None
    ctx["store"] = store


@given(parsers.parse('the rule registry is loaded with "{yaml_file}"'))
def load_registry(ctx, yaml_file: str) -> None:
    registry = get_registry()
    registry.reload()
    ctx["registry"] = registry


# ── Instrument setup ──────────────────────────────────────────────────────────

def _instrument_urn(isin: str) -> URIRef:
    return URIRef(f"urn:instrument:{isin}")


@given(parsers.parse('a CLO instrument with ISIN "{isin}"'))
def setup_clo(ctx, isin: str) -> None:
    store = ctx["store"]
    urn = _instrument_urn(isin)
    store.add_triples_sync([
        (urn, LC.hasISIN,  Literal(isin)),
        (urn, LC.secType,  Literal("CLO")),
    ])
    ctx["instrument_urn"] = isin  # evaluator takes ISIN string
    ctx["urn"] = urn


@given(parsers.parse('an ABS instrument with ISIN "{isin}"'))
def setup_abs(ctx, isin: str) -> None:
    store = ctx["store"]
    urn = _instrument_urn(isin)
    store.add_triples_sync([
        (urn, LC.hasISIN, Literal(isin)),
        (urn, LC.secType, Literal("ABS")),
    ])
    ctx["instrument_urn"] = isin
    ctx["urn"] = urn


@given(parsers.parse('a RMBS instrument with ISIN "{isin}"'))
def setup_rmbs(ctx, isin: str) -> None:
    store = ctx["store"]
    urn = _instrument_urn(isin)
    store.add_triples_sync([
        (urn, LC.hasISIN, Literal(isin)),
        (urn, LC.secType, Literal("RMBS")),
    ])
    ctx["instrument_urn"] = isin
    ctx["urn"] = urn


@given(parsers.parse('the instrument has a retention percentage of {pct:f}'))
def set_retention(ctx, pct: float) -> None:
    ctx["store"].add_triples_sync([
        (ctx["urn"], EU_SEC.retentionPercentage, Literal(pct, datatype=XSD.float)),
    ])


@given("the instrument has no retention data recorded")
def no_retention(ctx) -> None:
    pass  # simply don't add the triple


@given(parsers.parse('the retained interest is held by the originator'))
def set_originator_retained(ctx) -> None:
    orig_urn = URIRef(f"{ctx['urn']}_originator")
    ctx["store"].add_triples_sync([
        (ctx["urn"], EU_SEC.retainedInterestHolder, orig_urn),
        (orig_urn, LC.role, Literal("Originator")),
    ])


@given(parsers.parse('the instrument has STS designation "{value}"'))
def set_sts(ctx, value: str) -> None:
    ctx["store"].add_triples_sync([
        (ctx["urn"], EU_SEC.stsDesignated, Literal(value == "true", datatype=XSD.boolean)),
    ])


@given("the instrument has a quarterly investor report published")
def set_quarterly_report(ctx) -> None:
    ctx["store"].add_triples_sync([
        (ctx["urn"], EU_SEC.reportFrequency, Literal("quarterly")),
    ])


@given("the instrument has an ERISA restriction recorded")
def set_erisa_restricted(ctx) -> None:
    ctx["store"].add_triples_sync([
        (ctx["urn"], ERISA.hasRestriction, ERISA.ERISARestricted),
    ])


@given("the instrument has no ERISA restriction recorded")
def no_erisa_restriction(ctx) -> None:
    pass


@given(parsers.parse('the instrument has a QPAM exemption certificate with status "{status}"'))
def set_qpam(ctx, status: str) -> None:
    cert_urn = URIRef(f"{ctx['urn']}_qpam_cert")
    ctx["store"].add_triples_sync([
        (ctx["urn"], ERISA.hasExemptionCertificate, cert_urn),
        (cert_urn, ERISA.exemptionType, Literal("QPAM")),
        (cert_urn, ERISA.exemptionStatus, Literal(status)),
    ])


# ── Document setup ────────────────────────────────────────────────────────────

def _doc_urn(doc_id: str) -> URIRef:
    return URIRef(f"urn:document:{doc_id}")


@given(parsers.parse('a document of type "{doc_type}" with ID "{doc_id}"'))
def setup_document(ctx, doc_type: str, doc_id: str) -> None:
    store = ctx["store"]
    urn = _doc_urn(doc_id)
    store.add_triples_sync([
        (urn, LC.documentType, Literal(doc_type)),
        (urn, LC.documentId,   Literal(doc_id)),
    ])
    ctx["instrument_urn"] = doc_id
    ctx["urn"] = urn


@given(parsers.parse('the document discloses coupon rate "{rate}"'))
def set_coupon(ctx, rate: str) -> None:
    ctx["store"].add_triples_sync([
        (ctx["urn"], OM.couponRate, Literal(rate)),
    ])


@given(parsers.parse('the document discloses maturity date "{maturity}"'))
def set_maturity(ctx, maturity: str) -> None:
    ctx["store"].add_triples_sync([
        (ctx["urn"], OM.maturityDate, Literal(maturity, datatype=XSD.date)),
    ])


@given("the document has no maturity date")
def no_maturity(ctx) -> None:
    pass


@given(parsers.parse('the document discloses management fee "{fee}"'))
def set_fee(ctx, fee: str) -> None:
    ctx["store"].add_triples_sync([
        (ctx["urn"], OM.managementFee, Literal(fee)),
    ])


@given(parsers.parse('the document identifies manager "{name}"'))
def set_manager(ctx, name: str) -> None:
    ctx["store"].add_triples_sync([
        (ctx["urn"], OM.hasManager, Literal(name)),
    ])


@given(parsers.parse('the document identifies trustee "{name}"'))
def set_trustee(ctx, name: str) -> None:
    ctx["store"].add_triples_sync([
        (ctx["urn"], OM.hasTrustee, Literal(name)),
    ])


@given("the document has no trustee identified")
def no_trustee(ctx) -> None:
    pass


@given(parsers.parse('the document identifies servicer "{name}"'))
def set_servicer(ctx, name: str) -> None:
    ctx["store"].add_triples_sync([
        (ctx["urn"], OM.hasServicer, Literal(name)),
    ])


# ── Rule evaluation ───────────────────────────────────────────────────────────

@when(parsers.parse('rule "{rule_id}" is evaluated against the instrument'))
def evaluate_rule(ctx, rule_id: str) -> None:
    evaluator = RuleEvaluator()
    result = evaluator.evaluate_instrument(
        instrument_urn=ctx["instrument_urn"],
        rule_id=rule_id,
    )
    ctx["result"] = result


@when(parsers.parse('rule "{rule_id}" is evaluated against the document'))
def evaluate_rule_doc(ctx, rule_id: str) -> None:
    return evaluate_rule(ctx, rule_id)


# ── Assertions ────────────────────────────────────────────────────────────────

@then(parsers.parse('the verdict is "{expected_verdict}"'))
def assert_verdict(ctx, expected_verdict: str) -> None:
    assert ctx["result"].verdict == expected_verdict, (
        f"Expected {expected_verdict!r}, got {ctx['result'].verdict!r}. "
        f"Explanation: {ctx['result'].explanation}"
    )


@then(parsers.parse("the confidence score is greater than {threshold:f}"))
def assert_confidence(ctx, threshold: float) -> None:
    score = ctx["result"].confidence
    assert score >= threshold, (
        f"Confidence {score} is below threshold {threshold}"
    )


@then("the result flags human review required")
def assert_human_review(ctx) -> None:
    assert ctx["result"].human_review_required is True, (
        "Expected human_review_required=True"
    )


@then("the result includes evidence citing the retention figure")
def assert_evidence_retention(ctx) -> None:
    evidence = " ".join(str(e) for e in ctx["result"].evidence)
    assert "retention" in evidence.lower() or "5" in evidence, (
        f"Evidence does not mention retention: {ctx['result'].evidence}"
    )


@then(parsers.parse('the explanation mentions "{phrase_a}" and "{phrase_b}"'))
def assert_explanation_both(ctx, phrase_a: str, phrase_b: str) -> None:
    expl = ctx["result"].explanation.lower()
    assert phrase_a.lower() in expl, f"Explanation missing '{phrase_a}': {expl}"
    assert phrase_b.lower() in expl, f"Explanation missing '{phrase_b}': {expl}"


@then(parsers.parse('the explanation mentions "{phrase}"'))
def assert_explanation_phrase(ctx, phrase: str) -> None:
    expl = ctx["result"].explanation.lower()
    assert phrase.lower() in expl, f"Explanation missing '{phrase}': {expl}"


@then(parsers.parse('the result includes "{phrase}" in the explanation'))
def assert_explanation_contains(ctx, phrase: str) -> None:
    return assert_explanation_phrase(ctx, phrase)
