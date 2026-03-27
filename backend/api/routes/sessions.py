"""Session history routes — backed by CosmosDB."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from models.schemas import ProcessingSession, SessionListItem
from ontology.graph_store import GraphStore
from services.cosmos_service import CosmosService
from services.storage_service import StorageService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/health")
async def cosmos_health():
    """
    Verify CosmosDB connectivity and ensure the container exists.
    Returns {ok: true, ...} when healthy, {ok: false, error: ...} when not.
    """
    cosmos = CosmosService()
    result = await asyncio.to_thread(cosmos.ensure_container)
    return result


@router.get("/", response_model=list[SessionListItem])
async def list_sessions(limit: int = 50):
    """List recent processing sessions from CosmosDB, newest first."""
    cosmos = CosmosService()
    return await cosmos.list_sessions(limit=limit)


@router.get("/by-document/{document_id}", response_model=list[SessionListItem])
async def list_sessions_by_document(document_id: str):
    """
    Return all pipeline runs for a given document.
    Typically 2 entries: one legacy + one optimized, ordered newest first.
    Used by the frontend to show a paired comparison view per document.
    """
    cosmos = CosmosService()
    return await cosmos.list_sessions_by_document(document_id)


@router.get("/{session_id}", response_model=ProcessingSession)
async def get_session(session_id: str, document_id: str | None = None):
    """
    Retrieve the full session (provisions + clauses + findings) by ID.
    Pass document_id as a query param to avoid a cross-partition read.
    """
    cosmos = CosmosService()
    session = await cosmos.get_session(session_id, document_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")
    return session


@router.delete("/by-document/{document_id}")
async def delete_sessions_by_document(document_id: str):
    """
    Delete ALL pipeline runs (legacy + optimized) for a given document_id,
    and remove the corresponding blobs from Azure Storage.
    Returns the number of Cosmos items and blobs deleted.
    """
    cosmos = CosmosService()
    storage = StorageService()
    try:
        deleted_sessions = await cosmos.delete_sessions_by_document(document_id)
        deleted_blobs = await storage.delete_blobs_for_document(document_id)
        deleted_triples = await asyncio.to_thread(
            GraphStore.get().remove_document_triples, document_id
        )
        from services.search_service import SearchService
        deleted_chunks = await asyncio.to_thread(
            SearchService().delete_document, document_id
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "deleted": deleted_sessions,
        "deleted_blobs": deleted_blobs,
        "deleted_triples": deleted_triples,
        "deleted_chunks": deleted_chunks,
        "document_id": document_id,
    }
