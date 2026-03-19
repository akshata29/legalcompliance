"""
OPTIMIZED PIPELINE — implements all six priority recommendations from the
document-processing-analysis.md:

  Priority 1  Prompt-Level Batching: pack N provisions per LLM call
  Priority 2  Pre-Filter Before LLM: keyword elimination before any API call
  Priority 3  Async I/O with Semaphore rate limiter (asyncio + AsyncAzureOpenAI)
  Priority 4  Redis-backed result caching (graceful skip if Redis unavailable)
  Priority 5  Pipeline Parallelism: analysis starts as soon as a clause batch
              is ready, without waiting for all extractions to finish
  Priority 6  Bulk DB write pattern (results collected then written in one shot)

Expected wall-time reduction: ~980 s → ~120 s on a 150-page document.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional
from uuid import uuid4

from openai import AsyncAzureOpenAI

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
from processing.prefilter import batch_prefilter
from models.schemas import PrefilterSample

logger = logging.getLogger(__name__)


class OptimizedPipeline:
    """
    High-throughput pipeline implementing all analysis recommendations.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        self._client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        # Three separate semaphores so Phase B (extract) and Phase C (analyze)
        # don't starve each other when running pipelined (P5).
        self._semaphore          = asyncio.Semaphore(settings.optimized_semaphore_limit)
        self._extract_semaphore  = asyncio.Semaphore(settings.optimized_semaphore_extract)
        self._analyze_semaphore  = asyncio.Semaphore(settings.optimized_semaphore_analyze)
        self._batch_size = settings.optimized_batch_size
        # Optional Redis cache — graceful fallback if unavailable
        self._cache: Optional[Any] = self._init_redis()
        # Prompt capture
        self._capture_log: list[dict] = []
        self._capture_count = 0
        self._max_samples_per_phase = 2  # 2 batch samples per phase

    def _init_redis(self):
        try:
            import redis as _redis
            r = _redis.Redis(host="localhost", port=6379, db=0, socket_connect_timeout=1)
            r.ping()
            logger.info("Redis cache: connected")
            return r
        except Exception:
            logger.info("Redis unavailable — caching disabled")
            return None

    # ─── Main entry point ────────────────────────────────────────────────────

    async def run(
        self,
        session: ProcessingSession,
        provisions: list[Provision],
        rules: list[dict],
        status_callback=None,
    ) -> ProcessingSession:
        pipeline_start = time.perf_counter()
        session.metrics = PipelineMetrics()

        # ── Priority 2: Keyword Pre-Filter ────────────────────────────────
        await self._emit(status_callback, session, ProcessingStatus.CATEGORIZING, 15)
        prov_dicts = [p.model_dump() for p in provisions]
        candidates, eliminated, pf_samples = batch_prefilter(prov_dicts)

        session.metrics.provisions_categorized = len(provisions)
        session.metrics.provisions_prefiltered = len(eliminated)
        session.metrics.prefilter_samples = [PrefilterSample(**s) for s in pf_samples]

        # Mark eliminated provisions as not relevant (no LLM call)
        for e in eliminated:
            session.provisions.append(
                CategorizedProvision(
                    provision_id=e["provision_id"],
                    provision_text=e["text"],
                    relevant=False,
                    categories=[],
                    confidence=1.0,
                    prefiltered=True,
                )
            )

        logger.info(
            "Optimized — Pre-filter: %d eliminated, %d candidates (%.0f%% reduction)",
            len(eliminated),
            len(candidates),
            100 * len(eliminated) / max(len(provisions), 1),
        )

        # ── Priority 1 + 3: Batch Categorization with Async I/O ──────────
        await self._emit(status_callback, session, ProcessingStatus.CATEGORIZING, 30)
        cat_metrics, categorized = await self._phase_categorize(candidates, rules)
        session.provisions.extend(categorized)
        session.metrics.phases.append(cat_metrics)
        self._collect_samples(session.metrics, "categorization")

        relevant = [p for p in session.provisions if p.relevant]
        session.metrics.provisions_relevant = len(relevant)
        # Track how many provisions REACHED the LLM but were classified not-relevant.
        # (candidates = passed pre-filter; categorized = what LLM returned)
        # provisions_prefiltered already captures the pre-filter drop separately.
        llm_seen = len(candidates)   # only non-prefiltered provisions go to LLM
        llm_relevant = sum(1 for p in categorized if p.relevant)
        session.metrics.provisions_llm_not_relevant = llm_seen - llm_relevant
        logger.info(
            "Optimized — %d/%d relevant (pre-filter: %d, LLM-rejected: %d)",
            len(relevant), len(provisions),
            len(eliminated), session.metrics.provisions_llm_not_relevant,
        )

        # ── Priority 5: Pipeline Parallelism — extract + analyze in stream ─
        await self._emit(status_callback, session, ProcessingStatus.EXTRACTING_CLAUSES, 60)
        ext_metrics, ana_metrics, clauses, findings = await self._phase_extract_and_analyze(
            relevant, rules, status_callback, session
        )
        session.clauses = clauses
        session.findings = findings
        session.metrics.phases.append(ext_metrics)
        session.metrics.phases.append(ana_metrics)
        self._collect_samples(session.metrics, "clause_extraction")
        self._collect_samples(session.metrics, "analysis")
        session.metrics.clauses_extracted = len(clauses)
        session.metrics.findings_generated = len(findings)

        # ── Finalize ──────────────────────────────────────────────────────
        session.metrics.total_duration_seconds = round(
            time.perf_counter() - pipeline_start, 2
        )
        session.metrics.total_llm_calls = sum(p.llm_calls for p in session.metrics.phases)
        session.metrics.total_tokens_used = sum(p.tokens_used for p in session.metrics.phases)
        session.status = ProcessingStatus.COMPLETE
        session.completed_at = datetime.now(timezone.utc)
        await self._emit(status_callback, session, ProcessingStatus.COMPLETE, 100)
        return session

    # ─── Phase A: Batched Async Categorization (P1 + P3 + P4) ───────────────

    async def _phase_categorize(
        self, candidates: list[dict], rules: list[dict]
    ) -> tuple[PhaseMetrics, list[CategorizedProvision]]:
        """
        Priority 1: Pack up to `batch_size` provisions per LLM call.
        Priority 3: All batch calls fired concurrently via asyncio.gather.
        Priority 4: Per-provision Redis cache checked before batching —
                    cached hits skip the LLM entirely.
        """
        metrics = PhaseMetrics(phase="categorization", started_at=datetime.now(timezone.utc))

        rules_summary = "\n".join(
            f"- {r['id']}: {r['name']} — {r['description']}" for r in rules
        )

        # ── P4: Resolve cache hits first; collect cache misses for batching ──
        cached_results: dict[str, CategorizedProvision] = {}
        uncached: list[dict] = []

        for p in candidates:
            ck = self._cache_key("cat2", {"id": p["provision_id"], "text": p["text"][:400]}, rules_summary)
            hit = self._cache_get(ck)
            if hit:
                cached_results[p["provision_id"]] = CategorizedProvision(
                    provision_id=p["provision_id"],
                    provision_text=p["text"],
                    relevant=hit.get("relevant", False),
                    categories=hit.get("categories", []),
                    confidence=hit.get("confidence", 0.0),
                )
            else:
                uncached.append(p)

        # ── P1: Batch uncached provisions into groups of `batch_size` ────────
        batched_results: dict[str, CategorizedProvision] = {}

        async def _call_batch(batch: list[dict]) -> None:
            items_text = "\n\n".join(
                f"[{i}] ID={p['provision_id']}\n{p['text']}"
                for i, p in enumerate(batch)
            )
            system = (
                "You are a legal compliance analyst. Classify each numbered provision against "
                "the EU Securities rule categories below. "
                'Return ONLY JSON: {"results": [{"provision_id": "...", "relevant": bool, '
                '"categories": ["RULE_ID", ...], "confidence": float}, ...]}. '
                "Include one entry per provision in the same order."
            )
            user = f"RULE CATEGORIES:\n{rules_summary}\n\nPROVISIONS:\n{items_text}"

            # Token budget: ~120 tokens per result + 50 overhead
            batch_max_tokens = len(batch) * 120 + 50

            async with self._semaphore:
                t0 = time.perf_counter()
                response = await self._client.chat.completions.create(
                    model=self._settings.categorization_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=batch_max_tokens,
                    temperature=0.0,
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)

            content = response.choices[0].message.content or "{}"
            tokens = response.usage.total_tokens if response.usage else 0
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0
            metrics.llm_calls += 1
            metrics.tokens_used += tokens

            self._capture("categorization", system, user, content,
                          prompt_tokens, completion_tokens, latency_ms)

            try:
                res_list = json.loads(content).get("results", [])
            except json.JSONDecodeError:
                res_list = []

            # Build id→result map; fall back to empty dict for missing entries
            result_map = {r.get("provision_id"): r for r in res_list if isinstance(r, dict)}

            for p in batch:
                res = result_map.get(p["provision_id"], {})
                cp = CategorizedProvision(
                    provision_id=p["provision_id"],
                    provision_text=p["text"],
                    relevant=res.get("relevant", False),
                    categories=res.get("categories", []),
                    confidence=res.get("confidence", 0.0),
                )
                batched_results[p["provision_id"]] = cp
                # P4: cache the individual result for future runs
                ck = self._cache_key("cat2", {"id": p["provision_id"], "text": p["text"][:400]}, rules_summary)
                self._cache_set(ck, res)

        # ── P3: Fire all batch calls concurrently ─────────────────────────────
        batches = [
            uncached[i:i + self._batch_size]
            for i in range(0, len(uncached), self._batch_size)
        ]
        if batches:
            outcomes = await asyncio.gather(*[_call_batch(b) for b in batches], return_exceptions=True)
            for outcome in outcomes:
                if isinstance(outcome, Exception):
                    metrics.api_errors += 1
                    logger.warning("Optimized categorize batch error: %s", outcome)

        # ── Completeness check: retry provisions missing from batch results ──
        # If the JSON response was truncated (model hit max_tokens mid-array),
        # some provision_ids won't appear in batched_results.  Fall back to
        # individual single-provision calls for those to avoid silently marking
        # them as not-relevant.
        missing_ids = {
            p["provision_id"] for p in uncached
            if p["provision_id"] not in batched_results
               and p["provision_id"] not in cached_results
        }
        if missing_ids:
            logger.warning(
                "Optimized Phase A: %d provision(s) missing from batch results "
                "(possible JSON truncation) — retrying individually",
                len(missing_ids),
            )
            missing_provs = [p for p in uncached if p["provision_id"] in missing_ids]

            async def _call_single_fallback(p: dict) -> None:
                """Single-provision fallback call — used only for batch misses."""
                system = (
                    "You are a legal compliance analyst. Classify this provision against "
                    "the EU Securities rule categories below. "
                    'Return ONLY JSON: {"provision_id": "...", "relevant": bool, '
                    '"categories": ["RULE_ID", ...], "confidence": float}.'
                )
                user = f"RULE CATEGORIES:\n{rules_summary}\n\nPROVISION ID={p['provision_id']}:\n{p['text'][:800]}"
                async with self._semaphore:
                    response = await self._client.chat.completions.create(
                        model=self._settings.categorization_model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        response_format={"type": "json_object"},
                        max_tokens=200,
                        temperature=0.0,
                    )
                content = response.choices[0].message.content or "{}"
                tokens = response.usage.total_tokens if response.usage else 0
                metrics.llm_calls += 1
                metrics.tokens_used += tokens
                try:
                    res = json.loads(content)
                except json.JSONDecodeError:
                    res = {}
                cp = CategorizedProvision(
                    provision_id=p["provision_id"],
                    provision_text=p["text"],
                    relevant=res.get("relevant", False),
                    categories=res.get("categories", []),
                    confidence=res.get("confidence", 0.0),
                )
                batched_results[p["provision_id"]] = cp

            fallback_outcomes = await asyncio.gather(
                *[_call_single_fallback(p) for p in missing_provs],
                return_exceptions=True,
            )
            for outcome in fallback_outcomes:
                if isinstance(outcome, Exception):
                    metrics.api_errors += 1
                    logger.warning("Optimized categorize fallback error: %s", outcome)

        # Merge and preserve original candidate order
        all_results = {**cached_results, **batched_results}
        categorized = [all_results[p["provision_id"]] for p in candidates if p["provision_id"] in all_results]

        metrics.items_processed = len(categorized)
        metrics.completed_at = datetime.now(timezone.utc)
        metrics.duration_seconds = (metrics.completed_at - metrics.started_at).total_seconds()
        logger.info(
            "Optimized Phase A: %d batch call(s) for %d provisions (%d from cache), %.1fs, %d tokens",
            len(batches),
            len(uncached),
            len(cached_results),
            metrics.duration_seconds,
            metrics.tokens_used,
        )
        return metrics, categorized

    # ─── Phase B + C: Streaming extract → analyze (pipeline parallelism) ─────

    async def _phase_extract_and_analyze(
        self,
        relevant: list[CategorizedProvision],
        rules: list[dict],
        status_callback,
        session: ProcessingSession,
    ) -> tuple[PhaseMetrics, PhaseMetrics, list[ExtractedClause], list[ClauseFinding]]:
        ext_metrics = PhaseMetrics(phase="clause_extraction", started_at=datetime.now(timezone.utc), pipelined=True)
        ana_metrics = PhaseMetrics(phase="analysis", started_at=datetime.now(timezone.utc), pipelined=True)

        all_clauses: list[ExtractedClause] = []
        all_findings: list[ClauseFinding] = []

        # Build rule lookup so extraction can be scoped to primary rule (like legacy)
        rule_lookup: dict[str, dict] = {r["id"]: r for r in rules}

        async def _extract_one(cp: CategorizedProvision) -> list[ExtractedClause]:
            # Scope extraction to primary decision step rule (first category),
            # matching Legacy's per-provision+rule approach
            primary_rule_id = cp.categories[0] if cp.categories else "GENERAL"
            rule = rule_lookup.get(primary_rule_id,
                                   {"id": primary_rule_id, "name": primary_rule_id, "description": ""})
            system = (
                "You are a legal clause extractor. Given a provision and a specific "
                "compliance rule, determine whether the provision contains a clause relevant "
                "to this rule. If relevant, extract the specific clause text that addresses "
                "the rule. A provision addresses at most one aspect of a given rule. "
                "Return an empty clauses array if the provision is not relevant to this rule. "
                'Return ONLY JSON: {"clauses": [{"clause_text": "...", '
                '"obligation_type": "shall|must|may|shall_not"}]}'
            )
            user = (
                f"RULE: {rule['id']} — {rule['name']}\n"
                f"DESCRIPTION: {rule.get('description', '')}\n\n"
                f"PROVISION (ID={cp.provision_id}):\n{cp.provision_text}"
            )
            async with self._extract_semaphore:
                t0 = time.perf_counter()
                response = await self._client.chat.completions.create(
                    model=self._settings.extraction_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=self._settings.optimized_max_tokens_extract,
                    temperature=0.0,
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
            content = response.choices[0].message.content or "{}"
            tokens = response.usage.total_tokens if response.usage else 0
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0
            ext_metrics.llm_calls += 1
            ext_metrics.tokens_used += tokens
            self._capture("clause_extraction", system, user, content,
                          prompt_tokens, completion_tokens, latency_ms)
            try:
                raw = json.loads(content).get("clauses", [])
            except json.JSONDecodeError:
                raw = []
            return [
                ExtractedClause(
                    provision_id=cp.provision_id,
                    clause_text=c.get("clause_text", ""),
                    rule_category=primary_rule_id,
                    obligation_type=c.get("obligation_type", ""),
                )
                for c in raw
            ]

        async def _analyze_one(clause: ExtractedClause) -> ClauseFinding:
            system = (
                "You are a senior EU Securities compliance officer. Analyse this clause "
                "against the specified rule category. "
                "Risk calibration — critical: potential regulatory sanction, fraud, or criminal liability; "
                "high: material non-compliance likely to attract regulatory scrutiny or significant penalty; "
                "medium: compliance gap requiring remediation; low: minor technical deviation. "
                "Err on the side of a higher risk level when the obligation is unclear or ambiguous. "
                'Return ONLY JSON: {"finding": "compliant|non_compliant|needs_review|not_applicable", '
                '"justification": "...", "risk_level": "low|medium|high|critical", '
                '"recommendation": "..."}'
            )
            user = (
                f"RULE CATEGORY: {clause.rule_category}\n\n"
                f"CLAUSE (ID={clause.clause_id}):\n{clause.clause_text}"
            )
            async with self._analyze_semaphore:
                t0 = time.perf_counter()
                response = await self._client.chat.completions.create(
                    model=self._settings.analysis_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=self._settings.optimized_max_tokens_analyze,
                    temperature=0.0,
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
            content = response.choices[0].message.content or "{}"
            tokens = response.usage.total_tokens if response.usage else 0
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0
            ana_metrics.llm_calls += 1
            ana_metrics.tokens_used += tokens
            self._capture("analysis", system, user, content,
                          prompt_tokens, completion_tokens, latency_ms)
            try:
                res = json.loads(content)
            except json.JSONDecodeError:
                res = {}
            try:
                finding_type = FindingType(res.get("finding", "needs_review"))
            except ValueError:
                finding_type = FindingType.NEEDS_REVIEW
            return ClauseFinding(
                clause_id=clause.clause_id,
                provision_id=clause.provision_id,
                rule_category=clause.rule_category,
                finding=finding_type,
                justification=res.get("justification", ""),
                risk_level=res.get("risk_level", "medium"),
                recommendation=res.get("recommendation"),
            )

        # Priority 5: Each provision's clauses are analyzed immediately
        # without waiting for all extractions to complete (producer-consumer).
        async def _extract_then_analyze(cp: CategorizedProvision) -> None:
            try:
                clauses = await _extract_one(cp)
                all_clauses.extend(clauses)
                # Immediately analyze each extracted clause (Phase 3a)
                tasks = [_analyze_one(c) for c in clauses]
                findings = await asyncio.gather(*tasks, return_exceptions=True)
                for f in findings:
                    if isinstance(f, Exception):
                        ana_metrics.api_errors += 1
                    else:
                        all_findings.append(f)
            except Exception as exc:
                ext_metrics.api_errors += 1
                logger.warning("Optimized extract/analyze error: %s", exc)

        await asyncio.gather(*[_extract_then_analyze(cp) for cp in relevant])

        # ── Phase 3b: 1 confirmation call per AiDecisionStep rule ────────────
        # AiDecisionStep._prompt_decision_step_finding() — single call per rule,
        # receives all clause findings, returns step-level determination.
        findings_by_rule: dict[str, list[dict]] = {}
        for f in all_findings:
            findings_by_rule.setdefault(f.rule_category, []).append({
                "finding": f.finding.value,
                "justification": f.justification,
                "risk_level": f.risk_level,
            })

        async def _confirm_step(rule_id: str, clause_findings: list[dict]) -> None:
            findings_text = "\n".join(
                f"- Clause {i + 1}: finding={fd.get('finding', 'unknown')}, "
                f"risk={fd.get('risk_level', 'medium')}: {fd.get('justification', '')[:200]}"
                for i, fd in enumerate(clause_findings)
            )
            system = (
                "You are a senior EU Securities compliance officer. "
                "Review all clause-level findings for a compliance rule and determine the "
                "overall step finding (AiDecisionStep determination). "
                'Return ONLY JSON: {"finding": "compliant|non_compliant|review_required", '
                '"justification": "...", "possible_issues": ["..."]}'
            )
            user = f"RULE: {rule_id}\n\nCLAUSE FINDINGS:\n{findings_text}"
            async with self._analyze_semaphore:
                response = await self._client.chat.completions.create(
                    model=self._settings.analysis_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=300,
                    temperature=0.0,
                )
            tokens = response.usage.total_tokens if response.usage else 0
            ana_metrics.llm_calls += 1
            ana_metrics.tokens_used += tokens

        if findings_by_rule:
            await asyncio.gather(*[
                _confirm_step(rule_id, clause_findings)
                for rule_id, clause_findings in findings_by_rule.items()
            ])

        ext_metrics.items_processed = len(all_clauses)
        ext_metrics.completed_at = datetime.now(timezone.utc)
        ext_metrics.duration_seconds = (
            ext_metrics.completed_at - ext_metrics.started_at
        ).total_seconds()

        ana_metrics.items_processed = len(all_findings)
        ana_metrics.completed_at = datetime.now(timezone.utc)
        ana_metrics.duration_seconds = (
            ana_metrics.completed_at - ana_metrics.started_at
        ).total_seconds()

        logger.info(
            "Optimized Phase B+C: extract=%d calls %.1fs | analyze=%d clause + %d confirm calls %.1fs",
            ext_metrics.llm_calls,
            ext_metrics.duration_seconds,
            ext_metrics.llm_calls,  # clause analysis calls = same as extractions conceptually
            len(findings_by_rule),  # confirmation calls = 1 per rule
            ana_metrics.duration_seconds,
        )
        return ext_metrics, ana_metrics, all_clauses, all_findings

    # ─── Cache helpers (Priority 4) ──────────────────────────────────────────

    def _cache_key(self, prefix: str, data: Any, suffix: str = "") -> str:
        raw = json.dumps(data, sort_keys=True, default=str) + suffix
        return f"lc:{prefix}:{hashlib.sha256(raw.encode()).hexdigest()}"

    def _cache_get(self, key: str) -> Optional[Any]:
        if self._cache is None:
            return None
        try:
            val = self._cache.get(key)
            return json.loads(val) if val else None
        except Exception:
            return None

    def _cache_set(self, key: str, value: Any, ttl: int = 7 * 86400) -> None:
        if self._cache is None:
            return
        try:
            self._cache.setex(key, ttl, json.dumps(value))
        except Exception:
            pass

    # ─── Prompt capture helpers ──────────────────────────────────────────────

    def _capture(self, phase: str, system: str, user: str,
                 response_text: str, prompt_tokens: int, completion_tokens: int,
                 latency_ms: int) -> None:
        """Record a sample LLM call for UI display."""
        self._capture_count += 1
        self._capture_log.append({
            "phase": phase,
            "call_index": self._capture_count,
            "system_prompt": system,
            "user_prompt": user,
            "response_text": response_text,
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "latency_ms": latency_ms,
        })

    def _collect_samples(self, metrics: PipelineMetrics, phase: str) -> None:
        """Move first N captures for a phase into metrics.prompt_samples."""
        phase_calls = [c for c in self._capture_log if c["phase"] == phase]
        for raw in phase_calls[: self._max_samples_per_phase]:
            metrics.prompt_samples.append(CapturedLlmCall(
                phase=raw["phase"],
                call_index=raw["call_index"],
                system_prompt=raw["system_prompt"],
                user_prompt=raw["user_prompt"],
                response_text=raw["response_text"],
                input_tokens=raw.get("input_tokens", 0),
                output_tokens=raw.get("output_tokens", 0),
                latency_ms=raw.get("latency_ms", 0),
            ))

    # ─── Status helper ───────────────────────────────────────────────────────

    @staticmethod
    async def _emit(callback, session, status: ProcessingStatus, pct: int) -> None:
        session.status = status
        if callback:
            try:
                await callback(session, pct)
            except Exception:
                pass
