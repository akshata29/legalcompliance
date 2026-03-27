"""
Batch Scheduler
---------------
APScheduler-based scheduler for recurring ontology enrichment jobs.
Configured via environment variables — no code changes needed to change schedule.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from batch.batch_queue import BatchQueue, Priority

log = logging.getLogger(__name__)

# Scheduler singleton
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


def start_scheduler() -> None:
    """
    Register all scheduled jobs and start the scheduler.
    Call once at application startup (after event loop is running).
    """
    scheduler = get_scheduler()
    if scheduler.running:
        return

    # ── Job 1: Nightly full re-enrichment ─────────────────────────────────────
    nightly_cron = os.environ.get("BATCH_NIGHTLY_CRON", "0 2 * * *")  # 02:00 UTC
    scheduler.add_job(
        _nightly_enrichment,
        trigger=CronTrigger.from_crontab(nightly_cron),
        id="nightly_enrichment",
        name="Nightly Graph Re-enrichment",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    log.info("Registered nightly enrichment job (cron: %s)", nightly_cron)

    # ── Job 2: Hourly rule reload ──────────────────────────────────────────────
    scheduler.add_job(
        _reload_rules,
        trigger=IntervalTrigger(minutes=60),
        id="rule_reload",
        name="Rule Registry Hot Reload",
        replace_existing=True,
    )
    log.info("Registered hourly rule reload job")

    # ── Job 3: Metrics snapshot every 5 minutes ──────────────────────────────
    scheduler.add_job(
        _snapshot_metrics,
        trigger=IntervalTrigger(minutes=5),
        id="metrics_snapshot",
        name="Telemetry Snapshot",
        replace_existing=True,
    )

    scheduler.start()
    log.info("Batch scheduler started")


def stop_scheduler() -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("Batch scheduler stopped")


# ── Job implementations ────────────────────────────────────────────────────────

async def _nightly_enrichment() -> None:
    """Submit enrichment jobs for all documents registered since last run."""
    log.info("Nightly enrichment starting at %s", datetime.now(timezone.utc).isoformat())
    try:
        from services.storage_service import StorageService

        storage = StorageService()
        doc_ids = await storage.list_document_ids()
        queue = BatchQueue.get()
        submitted = 0
        for doc_id in doc_ids:
            await queue.submit(
                document_id=doc_id,
                priority=Priority.NORMAL,
                submitted_by="scheduler",
            )
            submitted += 1
        log.info("Nightly enrichment: submitted %d jobs", submitted)
    except Exception as exc:
        log.error("Nightly enrichment failed: %s", exc, exc_info=True)


async def _reload_rules() -> None:
    try:
        from rules.rule_registry import get_registry
        get_registry().reload()
        log.debug("Rule registry hot-reloaded")
    except Exception as exc:
        log.error("Rule reload failed: %s", exc)


async def _snapshot_metrics() -> None:
    try:
        from services.telemetry_service import get_summary
        summary = get_summary()
        log.debug("Telemetry snapshot: %s", summary)
    except Exception as exc:
        log.error("Metrics snapshot failed: %s", exc)

