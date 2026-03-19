"""Document upload and listing routes."""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, UploadFile

from models.schemas import DocumentInfo, DocumentUploadResponse, ProcessingStatus
from services.storage_service import StorageService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

_MAX_FILE_SIZE = 50 * 1024 * 1024   # 50 MB


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile):
    """Upload a document (PDF, DOCX, or TXT) to Azure Blob Storage."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in {"pdf", "docx", "txt", "md"}:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: .{ext}")

    data = await file.read()
    if len(data) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413, detail=f"File exceeds 50 MB limit ({len(data)} bytes)."
        )

    doc_id = str(uuid.uuid4())
    blob_name = f"{doc_id}/{file.filename}"
    content_type = file.content_type or "application/octet-stream"

    storage = StorageService()
    try:
        blob_url, size = await storage.upload_document(
            io.BytesIO(data), blob_name, content_type
        )
    except Exception as exc:
        logger.error("Upload failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")

    return DocumentUploadResponse(
        document_id=doc_id,
        filename=file.filename,
        blob_url=blob_url,
        size_bytes=size,
        uploaded_at=datetime.now(timezone.utc),
    )


@router.get("/", response_model=list[DocumentInfo])
async def list_documents():
    """List all documents stored in Azure Blob Storage."""
    storage = StorageService()
    try:
        blobs = storage.list_documents()
    except Exception as exc:
        logger.error("List failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    docs: list[DocumentInfo] = []
    for b in blobs:
        parts = b["name"].split("/", 1)
        doc_id = parts[0] if len(parts) > 1 else b["name"]
        filename = parts[1] if len(parts) > 1 else b["name"]
        docs.append(
            DocumentInfo(
                document_id=doc_id,
                filename=filename,
                blob_url=b["url"],
                uploaded_at=b.get("last_modified") or datetime.now(timezone.utc),
                status=ProcessingStatus.PENDING,
            )
        )
    return docs


@router.get("/synthetic", response_model=DocumentInfo)
async def get_synthetic_document():
    """Return metadata for the built-in synthetic 150-page EU Sec document."""
    return DocumentInfo(
        document_id="synthetic-001",
        filename="eu_sec_150page.txt",
        blob_url="",
        page_count=150,
        provision_count=1765,
        uploaded_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        status=ProcessingStatus.PENDING,
    )
