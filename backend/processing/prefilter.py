"""
Keyword pre-filter for the Optimized Pipeline.

Eliminates provisions that cannot possibly match any rule category before
making any LLM call. This achieves Priority 2 from the architecture analysis:
"Pre-Filter Before LLM — Eliminate 30–50% of Calls".

Only provisions that contain at least one keyword from any rule category
proceed to the LLM. Everything else is tagged as `relevant=False, prefiltered=True`.
"""
from __future__ import annotations

import re

# ─── Keyword dictionary per rule category ────────────────────────────────────
# Edit these to match the actual rulebook.  Matching is case-insensitive.

RULE_KEYWORDS: dict[str, list[str]] = {
    "DATA_RETENTION": [
        "retain", "retention", "storage period", "kept for", "record",
        "archive", "preserve", "deletion", "purge", "data lifecycle",
    ],
    "DATA_TRANSFER": [
        "transfer", "cross-border", "third country", "recipient",
        "transmit", "share data", "disclose", "export data",
        "international transfer", "adequacy decision",
    ],
    "CONSENT": [
        "consent", "opt-in", "opt-out", "authorisation", "authorization",
        "permission", "agreement", "approve", "withdrawal of consent",
        "freely given",
    ],
    "REPORTING": [
        "report", "notify", "notification", "disclose", "submission",
        "file with", "inform the authority", "regulatory report", "SFTR",
        "MiFID", "disclosure obligation",
    ],
    "RISK_DISCLOSURE": [
        "risk", "risk disclosure", "material risk", "credit risk",
        "market risk", "operational risk", "warn", "caution", "prospectus",
        "investment risk", "loss",
    ],
    "RECORD_KEEPING": [
        "record", "documentation", "maintain records", "audit trail",
        "log", "evidence", "journal", "register", "ledger",
    ],
    "PRIVACY_NOTICE": [
        "privacy notice", "privacy policy", "fair processing",
        "information notice", "right to be informed", "personal data",
        "data subject", "GDPR", "data protection",
    ],
    "THIRD_PARTY": [
        "third party", "processor", "sub-processor", "vendor",
        "outsource", "delegate", "service provider", "contractor",
    ],
    "LAWFUL_BASIS": [
        "lawful basis", "legal basis", "legitimate interest", "contract",
        "legal obligation", "vital interests", "public task",
    ],
    "SUBJECT_RIGHTS": [
        "right of access", "right to erasure", "right to rectification",
        "data portability", "object to processing", "restrict processing",
        "subject access request", "SAR",
    ],
}

# Pre-compile flat set of lowercase keywords → category mapping
_FLAT_KEYWORDS: list[tuple[str, str]] = [
    (kw.lower(), cat)
    for cat, keywords in RULE_KEYWORDS.items()
    for kw in keywords
]


def keyword_prefilter(provision_text: str) -> tuple[bool, list[str]]:
    """
    Returns (passes_filter, matched_categories).
    A provision passes if ANY keyword from ANY category is found.
    """
    text_lower = provision_text.lower()
    matched: set[str] = set()
    for kw, cat in _FLAT_KEYWORDS:
        # Use word-boundary matching for short keywords to avoid false positives
        pattern = r"\b" + re.escape(kw) + r"\b" if len(kw) < 8 else re.escape(kw)
        if re.search(pattern, text_lower):
            matched.add(cat)
    return bool(matched), sorted(matched)


def batch_prefilter(
    provisions: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Split provisions into (candidates, eliminated).
    Each item in `eliminated` has relevant=False and prefiltered=True.
    """
    candidates: list[dict] = []
    eliminated: list[dict] = []
    for p in provisions:
        passes, hint_cats = keyword_prefilter(p["text"])
        if passes:
            p["hint_categories"] = hint_cats   # pass hints to LLM as soft context
            candidates.append(p)
        else:
            eliminated.append(p)
    return candidates, eliminated
