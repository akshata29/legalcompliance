"""
LEGACY PIPELINE  — mirrors the original architecture described in the
EU Sec architecture document (eusec-architecture-2026-03-17.pdf).

Characteristics that match the reference architecture exactly:
  • Phase A (Categorization): 1 LLM call per provision, run concurrently
    via ThreadPoolExecutor (ThreadpoolCompletionsBatch equivalent).
    Original: ~677s / 68% of total time — the main bottleneck.
  • Phase B (Clause Extraction): 1 LLM call per relevant provision,
    concurrent via ThreadPoolExecutor. ~230s / 23%.
  • Phase C (Analysis): 1 LLM call per Legal Clause, submitted concurrently
    via ThreadPoolExecutor. Total calls = sum of all clauses across all
    decision steps. Reference: 2 decision steps / 8 clauses = 8 calls / 12s.
    This is the legacy bottleneck when many clauses are extracted.
  • Phases run strictly sequentially (A must finish before B starts, etc.).
  • No pre-filter, no prompt-level batching, no adaptive rate limiting.
  • Each DB write happens immediately after each LLM response (N writes).

This is intentionally the "slow" path so the UI Toggle can demonstrate
the measurable impact of the Optimized Pipeline.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

from config import get_settings
from models.schemas import (
    CategorizedProvision,
    ClauseFinding,
    ExtractedClause,
    FindingType,
    PhaseMetrics,
    PipelineMetrics,
    ProcessingSession,
    ProcessingStatus,
    Provision,
)
from services.openai_service import OpenAIService

logger = logging.getLogger(__name__)


class LegacyPipeline:
    """
    Replicates the bottleneck architecture:
    N individual LLM calls, ThreadPoolExecutor, sequential phases.
    """

    def __init__(self, openai_service: OpenAIService | None = None) -> None:
        self._llm = openai_service or OpenAIService()
        self._settings = get_settings()

    # ─── Main entry point ────────────────────────────────────────────────────

    async def run(
        self,
        session: ProcessingSession,
        provisions: list[Provision],
        rules: list[dict],
        status_callback=None,
    ) -> ProcessingSession:
        """
        Execute all three LLM phases sequentially.
        Updates `session` in place and returns it.
        """
        pipeline_start = time.perf_counter()
        session.metrics = PipelineMetrics()

        # ── Phase A: Categorization ───────────────────────────────────────
        await self._emit(status_callback, session, ProcessingStatus.CATEGORIZING, 20)
        session, cat_metrics = await self._phase_categorize(session, provisions, rules)
        session.metrics.phases.append(cat_metrics)

        # Filter relevant provisions
        relevant = [p for p in session.provisions if p.relevant]
        session.metrics.provisions_relevant = len(relevant)
        logger.info("Legacy — %d/%d provisions relevant", len(relevant), len(provisions))

        # ── Phase B: Clause Extraction ────────────────────────────────────
        await self._emit(status_callback, session, ProcessingStatus.EXTRACTING_CLAUSES, 55)
        session, ext_metrics = await self._phase_extract(session, relevant, rules)
        session.metrics.phases.append(ext_metrics)

        # ── Phase C: Analysis ─────────────────────────────────────────────
        await self._emit(status_callback, session, ProcessingStatus.ANALYZING, 80)
        session, ana_metrics = await self._phase_analyze(session, rules)
        session.metrics.phases.append(ana_metrics)

        # ── Finalize ─────────────────────────────────────────────────────
        session.metrics.total_duration_seconds = round(time.perf_counter() - pipeline_start, 2)
        session.metrics.total_llm_calls = sum(p.llm_calls for p in session.metrics.phases)
        session.metrics.total_tokens_used = sum(p.tokens_used for p in session.metrics.phases)
        session.status = ProcessingStatus.COMPLETE
        session.completed_at = datetime.now(timezone.utc)
        await self._emit(status_callback, session, ProcessingStatus.COMPLETE, 100)
        return session

    # ─── Phase A ─────────────────────────────────────────────────────────────

    async def _phase_categorize(
        self,
        session: ProcessingSession,
        provisions: list[Provision],
        rules: list[dict],
    ) -> tuple[ProcessingSession, PhaseMetrics]:
        metrics = PhaseMetrics(phase="categorization", started_at=datetime.now(timezone.utc))
        session.metrics.provisions_categorized = len(provisions)

        def _call_one(prov: Provision) -> CategorizedProvision:
            result, tokens = self._llm.categorize_single(prov.text, rules)
            metrics.llm_calls += 1
            metrics.tokens_used += tokens
            return CategorizedProvision(
                provision_id=prov.provision_id,
                provision_text=prov.text,
                relevant=result.get("relevant", False),
                categories=result.get("categories", []),
                confidence=result.get("confidence", 0.0),
                llm_call_index=metrics.llm_calls,
            )

        loop = asyncio.get_event_loop()
        max_workers = self._settings.legacy_max_workers

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [loop.run_in_executor(executor, _call_one, prov) for prov in provisions]
            results = await asyncio.gather(*futures, return_exceptions=True)

        categorized: list[CategorizedProvision] = []
        for r in results:
            if isinstance(r, Exception):
                metrics.api_errors += 1
                logger.warning("Legacy categorize error: %s", r)
            else:
                categorized.append(r)

        session.provisions = categorized
        metrics.items_processed = len(categorized)
        metrics.completed_at = datetime.now(timezone.utc)
        metrics.duration_seconds = (
            metrics.completed_at - metrics.started_at
        ).total_seconds()
        logger.info(
            "Legacy Phase A: %d calls, %.1fs, %d tokens",
            metrics.llm_calls, metrics.duration_seconds, metrics.tokens_used,
        )
        return session, metrics

    # ─── Phase B ─────────────────────────────────────────────────────────────

    async def _phase_extract(
        self,
        session: ProcessingSession,
        relevant: list[CategorizedProvision],
        rules: list[dict],
    ) -> tuple[ProcessingSession, PhaseMetrics]:
        metrics = PhaseMetrics(phase="clause_extraction", started_at=datetime.now(timezone.utc))

        def _call_one(cp: CategorizedProvision) -> list[ExtractedClause]:
            clauses_raw, tokens = self._llm.extract_clauses(
                cp.provision_id, cp.provision_text, cp.categories
            )
            metrics.llm_calls += 1
            metrics.tokens_used += tokens
            extracted = []
            for c in clauses_raw:
                extracted.append(
                    ExtractedClause(
                        provision_id=cp.provision_id,
                        clause_text=c.get("clause_text", ""),
                        rule_category=c.get("rule_category", "GENERAL"),
                        obligation_type=c.get("obligation_type", ""),
                    )
                )
            return extracted

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=self._settings.legacy_max_workers) as executor:
            futures = [loop.run_in_executor(executor, _call_one, cp) for cp in relevant]
            results = await asyncio.gather(*futures, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                metrics.api_errors += 1
            else:
                session.clauses.extend(r)

        session.metrics.clauses_extracted = len(session.clauses)
        metrics.items_processed = len(session.clauses)
        metrics.completed_at = datetime.now(timezone.utc)
        metrics.duration_seconds = (metrics.completed_at - metrics.started_at).total_seconds()
        logger.info(
            "Legacy Phase B: %d calls, %.1fs, %d tokens",
            metrics.llm_calls, metrics.duration_seconds, metrics.tokens_used,
        )
        return session, metrics

    # ─── Phase C ─────────────────────────────────────────────────────────────

    async def _phase_analyze(
        self,
        session: ProcessingSession,
        rules: list[dict],
    ) -> tuple[ProcessingSession, PhaseMetrics]:
        """
        Phase C: Analysis — exactly as documented in the dev documentation:

          "One LLM call per Legal Clause within each Decision Step.
           The total number of calls is therefore the sum of all clauses
           across all decision steps."

        All calls are submitted concurrently to a ThreadpoolCompletionsBatch
        (ThreadPoolExecutor, max_workers=legacy_max_workers).

        For the reference 150-page document: 8 clauses → 8 LLM calls, 12s.
        For this test document: len(session.clauses) calls, runtime ∝ clauses.
        """
        metrics = PhaseMetrics(phase="analysis", started_at=datetime.now(timezone.utc))

        # Group clauses by rule_category to resolve rule_id per clause
        decision_steps: dict[str, list[ExtractedClause]] = defaultdict(list)
        for clause in session.clauses:
            decision_steps[clause.rule_category].append(clause)

        def _analyze_one_clause(
            rule_id: str, clause: ExtractedClause
        ) -> tuple[str, ExtractedClause, dict]:
            """1 LLM call per Legal Clause — the legacy bottleneck."""
            result, tokens = self._llm.analyze_clause(
                clause.clause_id, clause.clause_text, rule_id
            )
            metrics.llm_calls += 1
            metrics.tokens_used += tokens
            return rule_id, clause, result

        # Flat list of every clause across all decision steps
        all_clause_tasks = [
            (rule_id, clause)
            for rule_id, step_clauses in decision_steps.items()
            for clause in step_clauses
        ]

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=self._settings.legacy_max_workers) as executor:
            futures = [
                loop.run_in_executor(executor, _analyze_one_clause, rule_id, clause)
                for rule_id, clause in all_clause_tasks
            ]
            results = await asyncio.gather(*futures, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                metrics.api_errors += 1
                logger.warning("Legacy Phase C error: %s", r)
                continue
            rule_id, clause, res = r
            try:
                finding_type = FindingType(res.get("finding", "needs_review"))
            except ValueError:
                finding_type = FindingType.NEEDS_REVIEW
            session.findings.append(ClauseFinding(
                clause_id=clause.clause_id,
                provision_id=clause.provision_id,
                rule_category=rule_id,
                finding=finding_type,
                justification=res.get("justification", ""),
                risk_level=res.get("risk_level", "medium"),
                recommendation=res.get("recommendation"),
            ))

        session.metrics.findings_generated = len(session.findings)
        metrics.items_processed = len(session.findings)
        metrics.completed_at = datetime.now(timezone.utc)
        metrics.duration_seconds = (metrics.completed_at - metrics.started_at).total_seconds()
        logger.info(
            "Legacy Phase C: %d clause calls across %d decision steps, %.1fs, %d tokens",
            metrics.llm_calls, len(decision_steps),
            metrics.duration_seconds, metrics.tokens_used,
        )
        return session, metrics

    # ─── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    async def _emit(callback, session, status: ProcessingStatus, pct: int) -> None:
        session.status = status
        if callback:
            try:
                await callback(session, pct)
            except Exception:
                pass
