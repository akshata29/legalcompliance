"""
Batch Queue
-----------
AsyncIO priority queue for large-document (600+ page) ontology enrichment jobs.
- Maximum 5 concurrent user slots (NFR)
- Priority: CRITICAL > HIGH > NORMAL
- Status tracking with unique job IDs
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Callable, Coroutine, Optional

from pydantic import BaseModel, Field


# ── Priority ───────────────────────────────────────────────────────────────────

class Priority(IntEnum):
    CRITICAL = 0
    HIGH     = 1
    NORMAL   = 2


# ── Job model ──────────────────────────────────────────────────────────────────

class BatchJob(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    document_id: str
    document_url: Optional[str] = None
    priority: int = int(Priority.NORMAL)
    status: str = "queued"      # queued | running | done | failed
    progress: int = 0           # 0-100
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result_summary: Optional[dict] = None
    submitted_by: str = "system"


# ── Queue implementation ───────────────────────────────────────────────────────

class BatchQueue:
    """
    Singleton async priority queue with configurable worker concurrency.
    """
    _instance: "BatchQueue | None" = None

    def __init__(self, max_workers: int = 5) -> None:
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._jobs: dict[str, BatchJob] = {}
        self._semaphore = asyncio.Semaphore(max_workers)
        self._running = False

    @classmethod
    def get(cls) -> "BatchQueue":
        if cls._instance is None:
            cls._instance = cls(max_workers=5)
        return cls._instance

    async def submit(
        self,
        document_id: str,
        *,
        document_url: Optional[str] = None,
        priority: Priority = Priority.NORMAL,
        submitted_by: str = "system",
    ) -> BatchJob:
        """Enqueue a new enrichment job and return its BatchJob record."""
        job = BatchJob(
            document_id=document_id,
            document_url=document_url,
            priority=int(priority),
            submitted_by=submitted_by,
        )
        self._jobs[job.job_id] = job
        # Priority queue: lower int = higher priority
        await self._queue.put((int(priority), job.job_id))
        return job

    def get_status(self, job_id: str) -> Optional[BatchJob]:
        return self._jobs.get(job_id)

    def list_jobs(self, status: Optional[str] = None) -> list[BatchJob]:
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        return sorted(jobs, key=lambda j: (j.priority, j.created_at))

    async def start_worker(self) -> None:
        """
        Background coroutine — start once at app startup.
        Processes jobs from the priority queue with concurrency control.
        """
        self._running = True
        while self._running:
            try:
                _, job_id = await asyncio.wait_for(self._queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue

            job = self._jobs.get(job_id)
            if job is None:
                continue

            asyncio.create_task(self._process(job))

    async def _process(self, job: BatchJob) -> None:
        async with self._semaphore:
            job.status = "running"
            job.started_at = datetime.now(timezone.utc).isoformat()
            try:
                await _run_enrichment(job)
                job.status = "done"
                job.progress = 100
                job.completed_at = datetime.now(timezone.utc).isoformat()
            except Exception as exc:
                job.status = "failed"
                job.error = str(exc)
                job.completed_at = datetime.now(timezone.utc).isoformat()
            finally:
                self._queue.task_done()

    def stop(self) -> None:
        self._running = False


# ── Enrichment task ────────────────────────────────────────────────────────────

async def _run_enrichment(job: BatchJob) -> None:
    """
    Download + process a document via Document Intelligence and enrich graph.
    Updates job.progress as it goes (0 → 30 → 70 → 100).
    """
    from services.document_service import DocumentService
    from ontology.enrichment import enrich_from_session

    job.progress = 10

    # Fetch document content from storage
    doc_service = DocumentService()
    session_data = await doc_service.process_document_for_enrichment(
        document_id=job.document_id,
        document_url=job.document_url,
    )
    job.progress = 50

    # Enrich the knowledge graph
    stats = await enrich_from_session(session_data)
    job.progress = 90

    job.result_summary = {
        "triples_added": stats.get("triples_added", 0),
        "instruments_found": stats.get("instruments_found", 0),
        "findings_recorded": stats.get("findings_recorded", 0),
    }
    job.progress = 100

