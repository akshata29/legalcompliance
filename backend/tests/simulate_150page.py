#!/usr/bin/env python3
"""
simulate_150page.py — Reproduces the 150-page EU Sec document from the dev docs.

Reference (eusec_api_documentation.docx):
  Provisions:  ~1690 total, 20 relevant
  Rules:       2 decision steps
                 "2.3.2 Jan 2019 - Oct 2022"   (18 relevant provisions, 6 clauses)
                 "2.2.1 Article 6 Retention"   ( 2 relevant provisions, 2 clauses)
  LLM calls:   1690 cat + 20 extract + 8 analyze = 1718 (legacy)
  Real times:  cat=676.6s  extract=230.5s  analyze=12.3s  total≈919s

Time-scale factor 1/50 compresses the run to ~18s legacy, ~3s optimized.
All delays are deterministic — no real Azure OpenAI calls are made.

Usage (from backend/):
    python tests/simulate_150page.py
    python tests/simulate_150page.py --scale 100   # compressed 100× (faster)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from random import Random
from uuid import uuid4

# Allow running from backend/ or repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import (
    PipelineMode,
    ProcessingSession,
    ProcessingStatus,
    Provision,
)
from processing.legacy_pipeline import LegacyPipeline
from processing.optimized_pipeline import OptimizedPipeline
from services.openai_service import OpenAIService

# Suppress unrelated log noise during simulation
logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(message)s")

# ─── CLI args ──────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Simulate 150-page EU Sec document processing")
    p.add_argument(
        "--scale", type=int, default=50,
        help="Time-compression factor (default 50 → ~18s legacy, ~3s optimized)"
    )
    p.add_argument(
        "--legacy-only", action="store_true",
        help="Run legacy pipeline only"
    )
    p.add_argument(
        "--optimized-only", action="store_true",
        help="Run optimized pipeline only"
    )
    return p.parse_args()


# ─── Document profile (from docx) ─────────────────────────────────────────────

RULE_1_ID    = "2.3.2_JAN19_OCT22"
RULE_2_ID    = "2.2.1_ARTICLE6_RETENTION"
RULES = [
    {
        "id": RULE_1_ID,
        "name": "2.3.2 Jan 2019 - Oct 2022",
        "description": (
            "Conditions under which the retention requirement applies for CLO structures "
            "sold between January 2019 and October 2022 under the EU Securitization Regulation."
        ),
    },
    {
        "id": RULE_2_ID,
        "name": "2.2.1 Article 6 Retention",
        "description": (
            "Article 6 EU Securitization Regulation — the originator, sponsor or original lender "
            "shall retain a material net economic interest of not less than 5% on an ongoing basis."
        ),
    },
]

N_PROVISIONS    = 1690   # total chunks in a 150-page document
N_RELEVANT      = 20     # only 20 pass LLM categorization as relevant
RULE_1_RELEVANT = 18     # of these 20, 18 go under rule 1  (from docx log)
RULE_2_RELEVANT = 2      # and 2 go under rule 2
CLAUSES_RULE_1  = 6      # extraction yields 6 clauses from all rule-1 provisions
CLAUSES_RULE_2  = 2      # and 2 clauses from all rule-2 provisions
TOTAL_CLAUSES   = CLAUSES_RULE_1 + CLAUSES_RULE_2  # = 8 per docx


# ─── Synthetic provision builder ──────────────────────────────────────────────

def build_provisions(
    rng: Random,
) -> tuple[list[Provision], set[str], dict[str, list[dict]]]:
    """
    Build 1690 synthetic provisions that reproduce the 150-page document profile.

    Markers embedded in provision texts:
      [RULE1]  → this provision is relevant to rule 2.3.2
      [RULE2]  → this provision is relevant to rule 2.2.1
      (none)   → irrelevant provision

    The word "risk" is included everywhere so all provisions pass the
    keyword pre-filter in the optimized pipeline (matching real behaviour
    where all provisions went through LLM categorisation).

    Returns:
        provisions          — shuffled list of Provision objects
        relevant_ids        — set of provision_ids that are relevant
        clauses_by_pid      — provision_id → list of clause dicts to return
                              from extraction (only for provisions yielding clauses)
    """
    provisions: list[Provision] = []
    relevant_ids: set[str] = set()
    clauses_by_pid: dict[str, list[dict]] = {}

    # ── Rule-1 relevant provisions (18) ────────────────────────────────────
    for i in range(RULE_1_RELEVANT):
        pid = str(uuid4())
        text = (
            f"[RULE1] Provision {i+1}/{RULE_1_RELEVANT} — Article 6 Retention, Jan 2019–Oct 2022. "
            f"The originator shall, on an ongoing basis, retain a material net economic interest "
            f"in the securitisation of not less than 5% as set out in Article 6 of the "
            f"EU Securitization Regulation. Risk-weighted assets must be calculated accordingly. "
            f"This requirement applies to all CLO structures sold between Jan 2019 and Oct 2022. "
            f"Quarterly risk reports shall be submitted to the competent authority."
        )
        # First CLAUSES_RULE_1 rule-1 provisions each produce exactly one clause
        if i < CLAUSES_RULE_1:
            clauses_by_pid[pid] = [
                {
                    "clause_text": (
                        f"The originator shall retain a material net economic interest of not "
                        f"less than 5% in the securitisation position (Provision {i+1}, "
                        f"Rule 2.3.2 Jan 2019–Oct 2022)."
                    ),
                    "rule_category": RULE_1_ID,
                    "obligation_type": "shall",
                }
            ]
        provisions.append(Provision(provision_id=pid, text=text, page_number=(i * 8) + 1))
        relevant_ids.add(pid)

    # ── Rule-2 relevant provisions (2) ─────────────────────────────────────
    for i in range(RULE_2_RELEVANT):
        pid = str(uuid4())
        text = (
            f"[RULE2] Provision {i+1}/{RULE_2_RELEVANT} — Article 6 Retention Holder. "
            f"The retention requirement shall be met by the retention holder who retains not "
            f"less than 5% of the nominal value of each tranche sold or transferred to investors. "
            f"Risk transfer arrangements shall be notified to the competent authority without delay. "
            f"The originator's risk exposure must remain aligned with investor interests."
        )
        clauses_by_pid[pid] = [
            {
                "clause_text": (
                    f"The retention holder shall retain not less than 5% of the nominal value "
                    f"of each tranche (Provision {i+1}, Rule 2.2.1 Article 6)."
                ),
                "rule_category": RULE_2_ID,
                "obligation_type": "shall",
            }
        ]
        provisions.append(Provision(provision_id=pid, text=text, page_number=(i * 70) + 5))
        relevant_ids.add(pid)

    # ── Irrelevant provisions (~1670) ────────────────────────────────────────
    irr_templates = [
        (
            "General risk governance framework, clause {n}. This provision establishes "
            "senior management responsibility for overseeing and managing operational risk "
            "within the institution. All risk-related decisions must be documented."
        ),
        (
            "Transitional provision {n}. The requirements set out in this chapter shall "
            "apply from the date of entry into force, subject to applicable risk-based "
            "transitional arrangements. Competent authorities may extend applicable periods."
        ),
        (
            "Definitions clause {n}. For the purposes of this Regulation, 'securitisation' "
            "means a transaction or scheme whereby the credit risk associated with an exposure "
            "is tranched. Material risk participation is determined at the transaction level."
        ),
        (
            "General provision {n}. Without prejudice to any other applicable risk requirement, "
            "the institution shall implement and maintain adequate oversight procedures and "
            "risk management arrangements throughout the life of the transaction."
        ),
        (
            "Enforcement provision {n}. Competent authorities shall have the power to require "
            "risk reports and transaction documentation at any time. Non-compliance with risk "
            "retention requirements may result in administrative sanctions."
        ),
        (
            "Recital {n}. In order to ensure that originators have skin-in-the-game, the "
            "risk retention rule should apply on an ongoing basis. This recital reflects "
            "the overall policy objectives of the EU Securitization Regulation."
        ),
        (
            "Scope clause {n}. The provisions of this chapter apply to all parties involved "
            "in a securitisation transaction. The applicable risk framework is set out in "
            "the relevant technical standards issued by the European Supervisory Authorities."
        ),
    ]
    n_irrelevant = N_PROVISIONS - N_RELEVANT
    for i in range(n_irrelevant):
        text = irr_templates[i % len(irr_templates)].format(n=i + 1)
        provisions.append(
            Provision(
                provision_id=str(uuid4()),
                text=text,
                page_number=(i % 150) + 1,
            )
        )

    rng.shuffle(provisions)
    return provisions, relevant_ids, clauses_by_pid


# ─── Mock response helpers ─────────────────────────────────────────────────────

class _MockResponse:
    """Mimics the openai ChatCompletion response structure."""
    class _Msg:
        def __init__(self, c: str): self.content = c
    class _Choice:
        def __init__(self, c: str): self.message = _MockResponse._Msg(c)
    class _Usage:
        def __init__(self, t: int): self.total_tokens = t

    def __init__(self, content: str, tokens: int = 60):
        self.choices = [self._Choice(content)]
        self.usage = self._Usage(tokens)


def _detect_phase(system: str) -> str:
    """Identify the pipeline phase from the system prompt content."""
    sl = system.lower()
    if "classify each numbered provision" in sl:
        return "cat_batch"
    if "classify it against the provided rule categories" in sl:
        return "cat_single"
    if "clause extractor" in sl:
        return "extract"
    if "compliance officer" in sl:
        return "analyze"
    return "unknown"


def _cat_single_response(user: str) -> str:
    """Return categorization JSON for one provision, based on text markers."""
    if "[RULE1]" in user:
        return json.dumps({"relevant": True,  "categories": [RULE_1_ID], "confidence": 0.97})
    if "[RULE2]" in user:
        return json.dumps({"relevant": True,  "categories": [RULE_2_ID], "confidence": 0.96})
    return     json.dumps({"relevant": False, "categories": [],           "confidence": 0.05})


def _cat_batch_response(user: str) -> str:
    """Return batch categorization JSON, one entry per provision in the batch."""
    # The provisions section follows "PROVISIONS:\n" in the user message
    prov_section = user.split("PROVISIONS:\n", 1)[-1] if "PROVISIONS:\n" in user else user

    # Split into individual provision blocks: each starts with "[N] ID=<pid>"
    blocks = re.split(r"\n\n(?=\[\d+\])", prov_section.strip())
    results = []
    for block in blocks:
        m = re.match(r"\[(\d+)\] ID=(\S+)\n(.*)", block, re.DOTALL)
        if not m:
            continue
        _, pid, text = m.groups()
        if "[RULE1]" in text:
            results.append({"provision_id": pid, "relevant": True,  "categories": [RULE_1_ID], "confidence": 0.97})
        elif "[RULE2]" in text:
            results.append({"provision_id": pid, "relevant": True,  "categories": [RULE_2_ID], "confidence": 0.96})
        else:
            results.append({"provision_id": pid, "relevant": False, "categories": [],           "confidence": 0.05})
    return json.dumps({"results": results})


def _extract_response(user: str, clauses_by_pid: dict[str, list[dict]]) -> str:
    """Return extraction JSON for a provision, using precomputed clause data."""
    m = re.search(r"PROVISION \(ID=(\S+)\)", user)
    pid = m.group(1) if m else None
    clauses = clauses_by_pid.get(pid, [])
    return json.dumps({"clauses": clauses})


def _analyze_response() -> str:
    """Return a fixed clause-level finding (deterministic)."""
    return json.dumps({
        "finding":        "non_compliant",
        "justification":  (
            "The provision does not fully satisfy the 5% retention requirement "
            "under Article 6 of the EU Securitization Regulation."
        ),
        "risk_level":     "high",
        "recommendation": (
            "Ensure the originator explicitly maintains a 5% net economic interest "
            "on an ongoing basis and submits required quarterly reports."
        ),
    })


# ─── Mock OpenAI service — Legacy Pipeline ────────────────────────────────────

class MockOpenAIService(OpenAIService):
    """
    Replaces the real OpenAI client for legacy pipeline simulation.
    Overrides _chat() so ALL openai_service methods go through the mock.
    """

    def __init__(
        self,
        relevant_ids: set[str],
        clauses_by_pid: dict[str, list[dict]],
        cat_delay: float,
        extract_delay: float,
        analyze_delay: float,
    ):
        # Skip super().__init__() — no real Azure client needed
        from config import get_settings
        self._settings = get_settings()
        self._cat_delay     = cat_delay
        self._extract_delay = extract_delay
        self._analyze_delay = analyze_delay
        self._clauses_by_pid = clauses_by_pid

    def _chat(self, system: str, user: str, model: str, **kwargs) -> tuple[str, int]:
        phase = _detect_phase(system)
        if phase == "cat_single":
            time.sleep(self._cat_delay)
            return _cat_single_response(user), 80
        if phase == "extract":
            time.sleep(self._extract_delay)
            return _extract_response(user, self._clauses_by_pid), 120
        # analyze (phase C) or anything else
        time.sleep(self._analyze_delay)
        return _analyze_response(), 150


# ─── Mock Async OpenAI client — Optimized Pipeline ────────────────────────────

class _MockAsyncCompletions:
    def __init__(
        self,
        clauses_by_pid: dict[str, list[dict]],
        cat_batch_delay: float,
        extract_delay: float,
        analyze_delay: float,
    ):
        self._clauses_by_pid  = clauses_by_pid
        self._cat_batch_delay = cat_batch_delay
        self._extract_delay   = extract_delay
        self._analyze_delay   = analyze_delay

    async def create(self, *, model: str, messages: list, **kwargs) -> _MockResponse:
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user   = next((m["content"] for m in messages if m["role"] == "user"),   "")
        phase  = _detect_phase(system)

        if phase == "cat_batch":
            await asyncio.sleep(self._cat_batch_delay)
            return _MockResponse(_cat_batch_response(user), tokens=len(messages) * 30)

        if phase == "cat_single":
            await asyncio.sleep(self._cat_batch_delay)
            return _MockResponse(_cat_single_response(user), tokens=80)

        if phase == "extract":
            await asyncio.sleep(self._extract_delay)
            return _MockResponse(_extract_response(user, self._clauses_by_pid), tokens=120)

        # analyze / confirm-step
        await asyncio.sleep(self._analyze_delay)
        return _MockResponse(_analyze_response(), tokens=150)


class _MockAsyncChat:
    def __init__(self, completions: _MockAsyncCompletions):
        self.completions = completions


class MockAsyncClient:
    """Drop-in replacement for AsyncAzureOpenAI, patched onto OptimizedPipeline._client."""

    def __init__(
        self,
        clauses_by_pid: dict[str, list[dict]],
        cat_batch_delay: float,
        extract_delay: float,
        analyze_delay: float,
    ):
        self.chat = _MockAsyncChat(
            _MockAsyncCompletions(clauses_by_pid, cat_batch_delay, extract_delay, analyze_delay)
        )


# ─── Result printer ───────────────────────────────────────────────────────────

def _fmt(v, unit: str = "") -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.1f}{unit}"
    return f"{v}{unit}"


def print_comparison(
    legacy_sess: ProcessingSession | None,
    opt_sess:    ProcessingSession | None,
    scale:       int,
) -> None:
    print()
    print("=" * 78)
    print(f"  SIMULATION RESULTS — 150-PAGE EU SEC DOCUMENT  (1/{scale} time scale)")
    print(f"  Reference log: Cat=676.6s · Extract=230.5s · Analyze=12.3s · Total≈919s")
    print("=" * 78)

    hdr = f"  {'Metric':<35} {'Legacy':>18} {'Optimized':>18}"
    print(hdr)
    print("  " + "─" * 72)

    def row(label, lv, ov):
        print(f"  {label:<35} {lv:>18} {ov:>18}")

    # Phase breakdown
    if legacy_sess:
        lm = legacy_sess.metrics
        l_total = lm.total_duration_seconds or 1
        for lp in lm.phases:
            pct = f"({lp.duration_seconds / l_total * 100:.0f}%)" if l_total else ""
            lv = f"{_fmt(lp.duration_seconds,'s')} {pct}"
            ov = "—"
            if opt_sess:
                for op in opt_sess.metrics.phases:
                    if op.phase == lp.phase:
                        o_total = opt_sess.metrics.total_duration_seconds or 1
                        op_pct = f"({op.duration_seconds / o_total * 100:.0f}%)"
                        ov = f"{_fmt(op.duration_seconds,'s')} {op_pct}"
            label = lp.phase.replace("_", " ").title()
            row(label, lv, ov)

    print("  " + "─" * 72)

    l_total_s = _fmt(legacy_sess.metrics.total_duration_seconds, "s") if legacy_sess else "—"
    o_total_s = _fmt(opt_sess.metrics.total_duration_seconds,    "s") if opt_sess    else "—"
    row("Total Duration", l_total_s, o_total_s)

    if legacy_sess and opt_sess:
        lt = legacy_sess.metrics.total_duration_seconds or 0
        ot = opt_sess.metrics.total_duration_seconds    or 1
        row("Speedup", "—", f"{lt/ot:.1f}×")

    print()

    l_calls = _fmt(legacy_sess.metrics.total_llm_calls) if legacy_sess else "—"
    o_calls = _fmt(opt_sess.metrics.total_llm_calls)    if opt_sess    else "—"
    row("LLM Calls Total", l_calls, o_calls)

    if legacy_sess and opt_sess:
        lc = legacy_sess.metrics.total_llm_calls
        oc = opt_sess.metrics.total_llm_calls
        red = (lc - oc) / lc * 100 if lc else 0
        row("Call Reduction", "—", f"{red:.0f}%")

    print()
    row(
        "Provisions Processed",
        _fmt(legacy_sess.metrics.provisions_categorized) if legacy_sess else "—",
        _fmt(opt_sess.metrics.provisions_categorized)    if opt_sess    else "—",
    )
    row(
        "Relevant Provisions",
        _fmt(legacy_sess.metrics.provisions_relevant) if legacy_sess else "—",
        _fmt(opt_sess.metrics.provisions_relevant)    if opt_sess    else "—",
    )
    row(
        "Clauses Extracted",
        _fmt(legacy_sess.metrics.clauses_extracted) if legacy_sess else "—",
        _fmt(opt_sess.metrics.clauses_extracted)    if opt_sess    else "—",
    )
    row(
        "Findings Generated",
        _fmt(legacy_sess.metrics.findings_generated) if legacy_sess else "—",
        _fmt(opt_sess.metrics.findings_generated)    if opt_sess    else "—",
    )

    print()
    print(f"  Extrapolated real-time equivalent (×{scale}):")
    if legacy_sess:
        lt = (legacy_sess.metrics.total_duration_seconds or 0) * scale
        print(f"    Legacy:    {lt:>7,.0f}s  ({lt/60:.0f} min)")
    if opt_sess:
        ot = (opt_sess.metrics.total_duration_seconds or 0) * scale
        print(f"    Optimized: {ot:>7,.0f}s  ({ot/60:.0f} min)")

    print()
    print("  Expected from docx reference:")
    print("    Legacy:    919s total  (Cat 68% · Extract 25% · Analyze 1%)")
    print("    Optimized: ~120s (estimated from architecture doc ~7.5× speedup)")
    print("=" * 78)


# ─── Main ────────────────────────────────────────────────────────────────────

async def main() -> None:
    args = _parse_args()
    scale = args.scale

    # Per-call delay targets scaled from real single-call times:
    #   cat:     676.6s with 1690 calls, 5 workers → 2.0s/call real → 2.0/scale simulated
    #   extract: 230.5s with 20 calls,   5 workers  → 57.5s/call real → 57.5/scale simulated
    #   analyze:  12.3s with 8 calls,    5 workers  → 7.7s/call real  → 7.7/scale simulated
    #   opt cat batch: ~15s real per 10-provision batch (6 workers overhead) → 15/scale

    cat_single_delay  = 2.0  / scale
    extract_delay     = 57.5 / scale
    analyze_delay     = 7.7  / scale
    cat_batch_delay   = 15.0 / scale   # per batch of 10 provisions

    expected_legacy = (
        N_PROVISIONS * cat_single_delay / 5
        + N_RELEVANT * extract_delay / 5
        + TOTAL_CLAUSES * analyze_delay / 5
    )
    # Optimized: 169 batches / semaphore=15, 20 extract / semaphore=10, 8 analyze / semaphore=15
    n_batches = (N_PROVISIONS + 9) // 10
    expected_opt = (
        n_batches * cat_batch_delay / 15
        + N_RELEVANT * extract_delay / 10
        + TOTAL_CLAUSES * analyze_delay / 15
    )

    print()
    print("─" * 60)
    print(f"  150-Page EU Sec Document Simulation  (1/{scale} time scale)")
    print("─" * 60)
    print(f"  Provisions:      {N_PROVISIONS:,} total  ({N_RELEVANT} relevant)")
    print(f"  Decision steps:  2  ({CLAUSES_RULE_1} clauses + {CLAUSES_RULE_2} clauses = {TOTAL_CLAUSES} total)")
    print(f"  Delays/call:     cat={cat_single_delay:.3f}s  "
          f"extract={extract_delay:.3f}s  analyze={analyze_delay:.3f}s")
    print(f"  Expected:        legacy≈{expected_legacy:.0f}s  optimized≈{expected_opt:.0f}s")
    print("─" * 60)

    rng = Random(42)
    provisions, relevant_ids, clauses_by_pid = build_provisions(rng)

    legacy_sess: ProcessingSession | None = None
    opt_sess:    ProcessingSession | None = None

    # ── Legacy ──────────────────────────────────────────────────────────────
    if not args.optimized_only:
        print(f"\n  Running LEGACY pipeline ({N_PROVISIONS:,} provisions, {5} workers)…", flush=True)
        t0 = time.perf_counter()
        legacy_sess = ProcessingSession(
            document_id="sim-150page",
            document_name="Simulated 150-Page EU Sec Document",
            pipeline_mode=PipelineMode.LEGACY,
        )
        mock_llm = MockOpenAIService(
            relevant_ids, clauses_by_pid,
            cat_delay=cat_single_delay,
            extract_delay=extract_delay,
            analyze_delay=analyze_delay,
        )
        legacy_pipeline = LegacyPipeline(openai_service=mock_llm)
        legacy_sess = await legacy_pipeline.run(legacy_sess, provisions, RULES)
        elapsed = time.perf_counter() - t0
        lm = legacy_sess.metrics
        print(f"  ✓  {elapsed:.1f}s  |  calls={lm.total_llm_calls}  "
              f"relevant={lm.provisions_relevant}  clauses={lm.clauses_extracted}  "
              f"findings={lm.findings_generated}")

    # ── Optimized ────────────────────────────────────────────────────────────
    if not args.legacy_only:
        print(f"\n  Running OPTIMIZED pipeline ({N_PROVISIONS:,} provisions, semaphore=15)…", flush=True)
        t0 = time.perf_counter()
        opt_sess = ProcessingSession(
            document_id="sim-150page",
            document_name="Simulated 150-Page EU Sec Document",
            pipeline_mode=PipelineMode.OPTIMIZED,
        )
        opt_pipeline = OptimizedPipeline()
        opt_pipeline._client = MockAsyncClient(
            clauses_by_pid,
            cat_batch_delay=cat_batch_delay,
            extract_delay=extract_delay,
            analyze_delay=analyze_delay,
        )
        opt_sess = await opt_pipeline.run(opt_sess, provisions, RULES)
        elapsed = time.perf_counter() - t0
        om = opt_sess.metrics
        print(f"  ✓  {elapsed:.1f}s  |  calls={om.total_llm_calls}  "
              f"relevant={om.provisions_relevant}  clauses={om.clauses_extracted}  "
              f"findings={om.findings_generated}")

    print_comparison(legacy_sess, opt_sess, scale)


if __name__ == "__main__":
    asyncio.run(main())
