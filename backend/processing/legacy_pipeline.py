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
import json
import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

from config import get_settings
from models.schemas import (
    CapturedLlmCall,
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
        self._max_samples_per_phase = 5  # capture first N calls per phase

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

        # Enable prompt capture — collect all calls, trim to samples at end
        self._llm.capture_log = []
        self._llm._capture_count = 0

        # ── Phase A: Categorization ───────────────────────────────────────
        await self._emit(status_callback, session, ProcessingStatus.CATEGORIZING, 20)
        phase_a_start_idx = 0
        session, cat_metrics = await self._phase_categorize(session, provisions, rules)
        session.metrics.phases.append(cat_metrics)
        self._label_samples(session.metrics, "categorization", phase_a_start_idx)

        # Filter relevant provisions
        relevant = [p for p in session.provisions if p.relevant]
        session.metrics.provisions_relevant = len(relevant)
        session.metrics.provisions_llm_not_relevant = (
            session.metrics.provisions_categorized - len(relevant)
        )
        logger.info("Legacy — %d/%d relevant (%d LLM-rejected)",
                    len(relevant), len(provisions),
                    session.metrics.provisions_llm_not_relevant)

        # ── Phase B: Clause Extraction ────────────────────────────────────
        await self._emit(status_callback, session, ProcessingStatus.EXTRACTING_CLAUSES, 55)
        phase_b_start_idx = len(self._llm.capture_log)
        session, ext_metrics = await self._phase_extract(session, relevant, rules)
        session.metrics.phases.append(ext_metrics)
        self._label_samples(session.metrics, "clause_extraction", phase_b_start_idx)

        # ── Phase C: Analysis ─────────────────────────────────────────────
        await self._emit(status_callback, session, ProcessingStatus.ANALYZING, 80)
        phase_c_start_idx = len(self._llm.capture_log)
        session, ana_metrics = await self._phase_analyze(session, rules)
        session.metrics.phases.append(ana_metrics)
        self._label_samples(session.metrics, "analysis", phase_c_start_idx)

        # ── Finalize ─────────────────────────────────────────────────────
        self._llm.capture_log = None  # stop capturing
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
        """Phase B — Extraction of Legal Clauses and Decision Steps.

        Matches the reference architecture exactly:
          1. Assign each provision to its **primary** Decision Step (first
             rule category from Phase A categorisation).
          2. One focused LLM call per provision, scoped to that one rule.
          3. Total calls == len(relevant).  Clauses per call is typically
             0 or 1, yielding a small total clause set for Phase C.

        Reference 150-page log:
          {"2.3.2 Jan 2019 - Oct 2022": 18, "2.2.1 Article 6 Retention": 2}
          Number of LLM calls: 20, Total time: 230s
        """
        metrics = PhaseMetrics(phase="clause_extraction", started_at=datetime.now(timezone.utc))

        # Build a lookup so we can pass rule name/description to the prompt
        rule_lookup: dict[str, dict] = {r["id"]: r for r in rules}

        # ── Group provisions by primary Decision Step ────────────────────
        # Each provision is assigned to exactly one step (its first category)
        # — this mirrors the reference architecture's decision-step grouping.
        decision_step_provisions: dict[str, list[CategorizedProvision]] = defaultdict(list)
        for cp in relevant:
            primary_rule = cp.categories[0] if cp.categories else "GENERAL"
            decision_step_provisions[primary_rule].append(cp)

        step_summary = {rule_id: len(provs)
                        for rule_id, provs in decision_step_provisions.items()}
        logger.info("Starting legal clause extraction:\n%s",
                    json.dumps(step_summary, indent=2))

        # ── 1 LLM call per provision, focused on its decision-step rule ──
        def _call_one(rule_id: str, cp: CategorizedProvision) -> list[ExtractedClause]:
            rule = rule_lookup.get(rule_id,
                                   {"id": rule_id, "name": rule_id, "description": ""})
            clauses_raw, tokens = self._llm.extract_clauses_for_rule(
                cp.provision_id,
                cp.provision_text,
                rule["id"],
                rule["name"],
                rule.get("description", ""),
            )
            metrics.llm_calls += 1
            metrics.tokens_used += tokens
            extracted = []
            for c in clauses_raw:
                extracted.append(
                    ExtractedClause(
                        provision_id=cp.provision_id,
                        clause_text=c.get("clause_text", ""),
                        rule_category=rule_id,
                        obligation_type=c.get("obligation_type", ""),
                    )
                )
            return extracted

        # Flatten into task list — still 1 call per provision (total == len(relevant))
        all_tasks = [
            (rule_id, cp)
            for rule_id, step_provisions in decision_step_provisions.items()
            for cp in step_provisions
        ]

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=self._settings.legacy_max_workers) as executor:
            futures = [
                loop.run_in_executor(executor, _call_one, rule_id, cp)
                for rule_id, cp in all_tasks
            ]
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
            "Legacy Phase B: Number of LLM calls: %d, Total time: %.0fs, "
            "%d tokens, %d clauses across %d decision steps",
            metrics.llm_calls, metrics.duration_seconds, metrics.tokens_used,
            len(session.clauses), len(decision_step_provisions),
        )
        return session, metrics

    # ─── Phase C ─────────────────────────────────────────────────────────────

    async def _phase_analyze(
        self,
        session: ProcessingSession,
        rules: list[dict],
    ) -> tuple[ProcessingSession, PhaseMetrics]:
        """Phase C: Analysis — matches the architecture doc exactly.

        From page 8 (LLM Integration Points Summary):

          #3  Analyze  AiDecisionStep.process_multiple_clauses()
              → 1 LLM call per clause, ThreadpoolCompletionsBatch
              → finding + justification per clause

          #4  Analyze  AiDecisionStep._prompt_decision_step_finding()
              → 1 single call per rule (NOT batched)
              → confirm overall finding per decision step

        Phase 3a: Per-clause analysis (parallel, max_workers=5)
        Phase 3b: Per-decision-step confirmation (sequential, 1 call per rule)

        Reference 150-page: 2 decision steps, 8 clauses → 8+2 = 10 calls, 12s.
        """
        metrics = PhaseMetrics(phase="analysis", started_at=datetime.now(timezone.utc))

        # Build rule lookup for Phase 3b confirmation
        rule_lookup: dict[str, dict] = {r["id"]: r for r in rules}

        # Group clauses by rule_category (= decision step)
        decision_steps: dict[str, list[ExtractedClause]] = defaultdict(list)
        for clause in session.clauses:
            decision_steps[clause.rule_category].append(clause)

        # ── Phase 3a: Per-clause analysis (ThreadpoolCompletionsBatch) ───
        # Integration point #3: AiDecisionStep.process_multiple_clauses()
        # 1 LLM call per clause, generates finding + justification.
        # Design doc ref: page 8.
        def _analyze_one_clause(
            rule_id: str, clause: ExtractedClause
        ) -> tuple[str, ExtractedClause, dict]:
            """Integration point #3: 1 LLM call per Legal Clause."""
            result, tokens = self._llm.analyze_clause(
                clause.clause_id, clause.clause_text, rule_id
            )
            metrics.llm_calls += 1
            metrics.tokens_used += tokens
            return rule_id, clause, result

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

        # Collect per-clause findings, grouped by decision step for Phase 3b
        step_clause_findings: dict[str, list[dict]] = defaultdict(list)
        for r in results:
            if isinstance(r, Exception):
                metrics.api_errors += 1
                logger.warning("Legacy Phase 3a error: %s", r)
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
            step_clause_findings[rule_id].append(res)

        # ── Phase 3b: Per-decision-step confirmation ─────────────────────
        # Integration point #4: AiDecisionStep._prompt_decision_step_finding()
        # One non-batched LLM call per rule — receives all clause findings and
        # returns the step-level determination.
        for rule_id, clause_findings in step_clause_findings.items():
            rule = rule_lookup.get(rule_id,
                                   {"id": rule_id, "name": rule_id})
            try:
                _step_result, step_tokens = self._llm.prompt_decision_step_finding(
                    rule["id"],
                    rule["name"],
                    clause_findings,
                )
                metrics.llm_calls += 1
                metrics.tokens_used += step_tokens
                logger.info(
                    "Legacy Phase 3b: step=%s finding=%s",
                    rule_id, _step_result.get("finding", "unknown"),
                )
            except Exception as exc:
                metrics.api_errors += 1
                logger.warning("Legacy Phase 3b error for step %s: %s", rule_id, exc)

        session.metrics.findings_generated = len(session.findings)
        metrics.items_processed = len(session.findings)
        metrics.completed_at = datetime.now(timezone.utc)
        metrics.duration_seconds = (metrics.completed_at - metrics.started_at).total_seconds()
        logger.info(
            "Legacy Phase C: %d clause calls + %d step confirmations across %d decision steps, "
            "%.1fs, %d tokens",
            len(all_clause_tasks), len(step_clause_findings), len(decision_steps),
            metrics.duration_seconds, metrics.tokens_used,
        )
        return session, metrics

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _label_samples(
        self, metrics: PipelineMetrics, phase: str, start_idx: int
    ) -> None:
        """Take first N captured calls from this phase and add to prompt_samples."""
        if not self._llm.capture_log:
            return
        phase_calls = self._llm.capture_log[start_idx:]
        for raw in phase_calls[: self._max_samples_per_phase]:
            metrics.prompt_samples.append(CapturedLlmCall(
                phase=phase,
                call_index=raw["call_index"],
                system_prompt=raw["system_prompt"],
                user_prompt=raw["user_prompt"],
                response_text=raw["response_text"],
                input_tokens=raw.get("input_tokens", 0),
                output_tokens=raw.get("output_tokens", 0),
                latency_ms=raw.get("latency_ms", 0),
            ))

    @staticmethod
    async def _emit(callback, session, status: ProcessingStatus, pct: int) -> None:
        session.status = status
        if callback:
            try:
                await callback(session, pct)
            except Exception:
                pass
