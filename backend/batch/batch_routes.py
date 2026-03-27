"""
Batch API Routes — /batch/...
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from batch.batch_queue import BatchJob, BatchQueue, Priority

router = APIRouter(prefix="/batch", tags=["batch"])


# ── Request/Response models ────────────────────────────────────────────────────

class SubmitBatchRequest(BaseModel):
    document_id: str
    document_url: Optional[str] = None
    priority: str = "NORMAL"   # CRITICAL | HIGH | NORMAL
    submitted_by: str = "user"


class SubmitBatchResponse(BaseModel):
    job_id: str
    status: str
    document_id: str
    priority: int


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/submit", response_model=SubmitBatchResponse, status_code=202)
async def submit_batch_job(req: SubmitBatchRequest):
    """Submit a document for asynchronous ontology enrichment."""
    try:
        prio = Priority[req.priority.upper()]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {req.priority}")

    job = await BatchQueue.get().submit(
        document_id=req.document_id,
        document_url=req.document_url,
        priority=prio,
        submitted_by=req.submitted_by,
    )
    return SubmitBatchResponse(
        job_id=job.job_id,
        status=job.status,
        document_id=job.document_id,
        priority=job.priority,
    )


@router.get("/status/{job_id}", response_model=BatchJob)
async def get_job_status(job_id: str):
    """Get the current status and progress of a batch job."""
    job = BatchQueue.get().get_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@router.get("/jobs", response_model=list[BatchJob])
async def list_jobs(
    status: Optional[str] = Query(default=None, description="Filter by status: queued | running | done | failed"),
):
    """List all batch jobs optionally filtered by status."""
    return BatchQueue.get().list_jobs(status=status)

