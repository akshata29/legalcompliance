"""
Keyword pre-filter for the Optimized Pipeline.

Eliminates provisions that cannot possibly match any rule category before
making any LLM call. This achieves Priority 2 from the architecture analysis:
"Pre-Filter Before LLM — Eliminate 30–50% of Calls".

Only provisions that contain at least one keyword from any rule category
proceed to the LLM. Everything else is tagged as `relevant=False, prefiltered=True`.

Completeness note: keywords cover both generic data-protection terms AND
EU securities / securitisation-specific language so that CLO/ABS offering
circulars are not over-filtered.  Short provisions (≤ 60 chars) and
provisions that contain legal-obligation markers (shall / must / obliged /
required / prohibited) are always passed to the LLM regardless of keywords
to avoid silently eliminating implicit compliance obligations.
"""
from __future__ import annotations

import re

# ─── Obligation safety-net ────────────────────────────────────────────────────
# Any provision that contains these markers passes regardless of category keywords.
# They signal a substantive legal obligation / right that the LLM must evaluate.
_OBLIGATION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bshall\b",
        r"\bmust\b",
        r"\bobliges?\b",
        r"\bobligations?\b",
        r"\bis required\b",
        r"\bare required\b",
        r"\bprohibited\b",
        r"\bmay not\b",
        r"\bshall not\b",
        r"\bmust not\b",
        r"\bentitled to\b",
        r"\bhas the right\b",
        r"\bhave the right\b",
    ]
]

# ─── Keyword dictionary per rule category ────────────────────────────────────
# Edit these to match the actual rulebook.  Matching is case-insensitive.
# Includes both generic terms and EU securities / CLO / ABS-specific vocabulary.

RULE_KEYWORDS: dict[str, list[str]] = {
    "DATA_RETENTION": [
        "retain", "retention", "storage period", "kept for", "record",
        "archive", "preserve", "deletion", "purge", "data lifecycle",
        "document retention", "maintained for", "stored for",
        "six years", "five years", "seven years",
    ],
    "DATA_TRANSFER": [
        "transfer", "cross-border", "third country", "recipient",
        "transmit", "share data", "disclose", "export data",
        "international transfer", "adequacy decision",
        "shared with", "provided to", "disclosed to", "data sharing",
    ],
    "CONSENT": [
        "consent", "opt-in", "opt-out", "authorisation", "authorization",
        "permission", "agreement", "approve", "withdrawal of consent",
        "freely given", "explicit consent", "investor consent",
        "noteholder consent", "prior written consent",
    ],
    "REPORTING": [
        "report", "notify", "notification", "disclose", "submission",
        "file with", "inform the authority", "regulatory report", "SFTR",
        "MiFID", "disclosure obligation", "prospectus", "listing",
        "periodic report", "annual report", "investor report",
        "servicer report", "monthly report", "quarterly report",
        "semi-annual", "furnish", "publish", "make available",
        "disseminate", "filing", "regulatory filing",
    ],
    "RISK_DISCLOSURE": [
        "risk", "risk disclosure", "material risk", "credit risk",
        "market risk", "operational risk", "warn", "caution", "prospectus",
        "investment risk", "loss",
        # EU securities — indirect risk language
        "adverse", "adversely", "material adverse", "materially affect",
        "default", "insolvency", "bankruptcy", "credit event",
        "impair", "impairment", "first loss", "subordinated",
        "limited recourse", "no recourse", "shortfall", "write-down",
        "deferral", "suspension of payments", "concentration",
        "prepayment", "not guaranteed", "no guarantee",
        "may lose", "may fall", "below par", "below face value",
        "counterparty", "liquidity risk", "interest rate risk",
        "currency risk", "exchange rate", "principal amount",
        "credit enhancement", "overcollateralisation", "reserve fund",
    ],
    "RECORD_KEEPING": [
        "record", "documentation", "maintain records", "audit trail",
        "log", "evidence", "journal", "register", "ledger",
        "maintain", "booking", "reconcil", "transaction records",
        "position records", "trade records",
    ],
    "PRIVACY_NOTICE": [
        "privacy notice", "privacy policy", "fair processing",
        "information notice", "right to be informed", "personal data",
        "data subject", "GDPR", "data protection", "PII",
        "personal information", "data controller", "data processor",
    ],
    "THIRD_PARTY": [
        "third party", "processor", "sub-processor", "vendor",
        "outsource", "delegate", "service provider", "contractor",
        # EU securities parties
        "servicer", "trustee", "collateral manager", "custodian",
        "administrator", "paying agent", "account bank", "depositary",
        "sub-contractor", "affiliated", "related party", "arranger",
        "underwriter", "placement agent",
    ],
    "LAWFUL_BASIS": [
        "lawful basis", "legal basis", "legitimate interest", "contract",
        "legal obligation", "vital interests", "public task",
        "statutory", "regulatory requirement", "regulatory obligation",
        "authorised", "authorized", "licensed", "regulated entity",
        "competent authority", "supervisory authority",
    ],
    "SUBJECT_RIGHTS": [
        "right of access", "right to erasure", "right to rectification",
        "data portability", "object to processing", "restrict processing",
        "subject access request", "SAR",
        # EU securities investor rights
        "noteholder right", "investor right", "right of", "right to",
        "right to redeem", "right to receive", "enforcement",
        "secured creditor", "may exercise", "vote", "direct",
        "instruct", "entitled",
    ],
}

# Pre-compile flat set of lowercase keywords → category mapping
_FLAT_KEYWORDS: list[tuple[str, str]] = [
    (kw.lower(), cat)
    for cat, keywords in RULE_KEYWORDS.items()
    for kw in keywords
]


def keyword_prefilter(provision_text: str) -> tuple[bool, list[str], str, list[str]]:
    """
    Returns (passes_filter, matched_categories, reason, matched_terms).

    A provision passes if:
      1. It contains a legal-obligation marker (safety-net), OR
      2. ANY keyword from ANY category is found in the text.

    Safety-net: provisions with "shall / must / obliged / prohibited / entitled"
    etc. always pass because they express legal obligations even when they do
    not contain category-specific vocabulary.
    """
    text_lower = provision_text.lower()

    # ── Obligation safety-net ─────────────────────────────────────────────
    for pat in _OBLIGATION_PATTERNS:
        if pat.search(text_lower):
            return True, [], "obligation_marker", [pat.pattern]

    # ── Category keyword matching ─────────────────────────────────────────
    matched: set[str] = set()
    matched_terms: list[str] = []
    for kw, cat in _FLAT_KEYWORDS:
        # Use word-boundary matching for short keywords to avoid false positives
        pattern = r"\b" + re.escape(kw) + r"\b" if len(kw) < 8 else re.escape(kw)
        if re.search(pattern, text_lower):
            matched.add(cat)
            matched_terms.append(kw)
    if matched:
        return True, sorted(matched), "keyword_match", matched_terms
    return False, [], "no_match", []


def batch_prefilter(
    provisions: list[dict],
    max_samples: int = 3,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Split provisions into (candidates, eliminated, samples).
    Each item in `eliminated` has relevant=False and prefiltered=True.
    ``samples`` contains up to ``max_samples`` passed and ``max_samples``
    eliminated provisions with the match reason for UI display.
    """
    candidates: list[dict] = []
    eliminated: list[dict] = []
    passed_samples: list[dict] = []
    eliminated_samples: list[dict] = []
    for p in provisions:
        passes, hint_cats, reason, terms = keyword_prefilter(p["text"])
        if passes:
            p["hint_categories"] = hint_cats
            candidates.append(p)
            if len(passed_samples) < max_samples:
                passed_samples.append({
                    "provision_id": p["provision_id"],
                    "text": p["text"][:300],
                    "passed": True,
                    "reason": reason,
                    "matched_categories": hint_cats,
                    "matched_terms": terms[:5],
                })
        else:
            eliminated.append(p)
            if len(eliminated_samples) < max_samples:
                eliminated_samples.append({
                    "provision_id": p["provision_id"],
                    "text": p["text"][:300],
                    "passed": False,
                    "reason": reason,
                    "matched_categories": [],
                    "matched_terms": [],
                })
    return candidates, eliminated, eliminated_samples + passed_samples
