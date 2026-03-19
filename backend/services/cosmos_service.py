"""
CosmosDB service — session and memory management.
Uses ClientSecretCredential (no API key required).

Cosmos document schema (id = session_id, partitionKey = /document_id):
  {
    "id": "<session_id>",
    "session_id": "<session_id>",
    "document_id": "<document_id>",        ← partition key
    "document_name": "...",
    "pipeline_mode": "legacy" | "optimized",
    "status": "<ProcessingStatus>",
    "created_at": "<iso>",
    "completed_at": "<iso>",
    "metrics": { ... PipelineMetrics ... },
    "provisions": [ ... CategorizedProvision ... ],
    "clauses":    [ ... ExtractedClause ... ],
    "findings":   [ ... ClauseFinding ... ],
    "error_message": null
  }

Partition key is /document_id so all runs for the same document sit in
the same logical partition and can be queried within a single partition.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from azure.cosmos import CosmosClient, PartitionKey, exceptions

from config import get_settings
from models.schemas import ProcessingSession, SessionListItem

logger = logging.getLogger(__name__)


class CosmosService:
    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        self._client = CosmosClient(
            url=settings.cosmosdb_endpoint,
            credential=settings.azure_credential,
        )
        self._database_name = settings.cosmos_db_database
        self._container_name = settings.cosmos_db_container
        self._container = self._get_or_create_container()

    def _get_or_create_container(self):
        try:
            db = self._client.create_database_if_not_exists(self._database_name)
            container = db.create_container_if_not_exists(
                id=self._container_name,
                # Partition by document_id — all pipeline runs for a document
                # land in the same partition, enabling cheap cross-pipeline queries.
                partition_key=PartitionKey(path="/document_id"),
            )
            logger.info(
                "CosmosDB container ready: %s/%s",
                self._database_name, self._container_name,
            )
            return container
        except Exception as exc:
            logger.error(
                "CosmosDB container init FAILED — sessions will NOT be persisted. "
                "Endpoint: %s  DB: %s  Container: %s  Error: %s",
                self._settings.cosmosdb_endpoint,
                self._database_name,
                self._container_name,
                exc,
            )
            return None

    def ensure_container(self) -> dict:
        """
        Explicitly verify (and if needed create) the CosmosDB container.
        Returns a status dict suitable for a health-check response.
        """
        if self._container is not None:
            # Already initialised — run a cheap existence check
            try:
                props = self._container.read()
                return {
                    "ok": True,
                    "database": self._database_name,
                    "container": self._container_name,
                    "partition_key": props.get("partitionKey", {}).get("paths", []),
                }
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        # Container is None — attempt to create it now
        self._container = self._get_or_create_container()
        if self._container is None:
            return {
                "ok": False,
                "database": self._database_name,
                "container": self._container_name,
                "error": "Container creation failed — check logs for details.",
            }
        return {
            "ok": True,
            "database": self._database_name,
            "container": self._container_name,
            "created": True,
        }

    # ─── Write ───────────────────────────────────────────────────────────────

    async def upsert_session(self, session: ProcessingSession) -> None:
        """Async wrapper — runs the sync upsert in a thread."""
        if self._container is None:
            return
        await __import__("asyncio").to_thread(self.upsert_item_sync, session)

    def upsert_item_sync(self, session: ProcessingSession) -> None:
        """
        Synchronous upsert — call directly from threads or via asyncio.to_thread().

        Stores metrics, status, findings, and all summary fields.
        The `provisions` and `clauses` arrays are intentionally excluded because
        they contain full extracted text and can easily push a 150-page document
        past CosmosDB's 2 MB item limit.  Counts are preserved in the
        `metrics` sub-document (provisions_categorized, clauses_extracted).
        Full detail is available from the in-memory session store while the
        server is running, and can be re-fetched via a new pipeline run.
        """
        if self._container is None:
            return
        doc = session.model_dump(mode="json")
        doc["id"] = session.session_id
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        # Strip bulk text arrays — not needed for session-list queries and
        # they are the primary reason writes exceed the 2 MB CosmosDB limit.
        doc.pop("provisions", None)
        doc.pop("clauses", None)
        try:
            self._container.upsert_item(doc)
            logger.debug(
                "CosmosDB upsert OK: session=%s status=%s findings=%d",
                session.session_id, session.status, len(session.findings),
            )
        except Exception as exc:
            logger.error(
                "CosmosDB upsert FAILED: session=%s status=%s findings=%d — %s",
                session.session_id, session.status, len(session.findings), exc,
            )

    # ─── Read — single session ────────────────────────────────────────────────

    async def get_session(self, session_id: str, document_id: str | None = None) -> Optional[ProcessingSession]:
        """
        Read a full session by session_id.  If document_id is known pass it
        to use the partition key (cheaper read); otherwise cross-partition query.
        """
        if self._container is None:
            return None
        try:
            if document_id:
                item = self._container.read_item(
                    item=session_id, partition_key=document_id
                )
            else:
                # Cross-partition point read by id
                results = list(self._container.query_items(
                    query="SELECT * FROM c WHERE c.id = @sid",
                    parameters=[{"name": "@sid", "value": session_id}],
                    enable_cross_partition_query=True,
                ))
                if not results:
                    return None
                item = results[0]
            return ProcessingSession(**item)
        except exceptions.CosmosResourceNotFoundError:
            return None
        except Exception as exc:
            logger.warning("CosmosDB read failed: %s", exc)
            return None

    # ─── Read — list (flat) ──────────────────────────────────────────────────

    async def list_sessions(self, limit: int = 50) -> list[SessionListItem]:
        """All sessions ordered by creation date, newest first."""
        if self._container is None:
            return []
        try:
            query = (
                "SELECT c.session_id, c.document_id, c.document_name, "
                "c.pipeline_mode, c.status, c.created_at, c.completed_at, "
                "c.metrics, c.findings, c.provisions, c.error_message "
                "FROM c ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
            )
            items = list(self._container.query_items(
                query=query,
                parameters=[{"name": "@limit", "value": limit}],
                enable_cross_partition_query=True,
            ))
            return [self._to_list_item(i) for i in items]
        except Exception as exc:
            logger.warning("CosmosDB list failed: %s", exc)
            return []

    # ─── Read — grouped by document ──────────────────────────────────────────

    async def list_sessions_by_document(self, document_id: str) -> list[SessionListItem]:
        """
        Return ALL pipeline runs for a specific document (same partition).
        Typically returns 0-2 items: one legacy + one optimized.
        """
        if self._container is None:
            return []
        try:
            query = (
                "SELECT c.session_id, c.document_id, c.document_name, "
                "c.pipeline_mode, c.status, c.created_at, c.completed_at, "
                "c.metrics, c.findings, c.provisions, c.error_message "
                "FROM c WHERE c.document_id = @doc_id "
                "ORDER BY c.created_at DESC"
            )
            items = list(self._container.query_items(
                query=query,
                parameters=[{"name": "@doc_id", "value": document_id}],
                partition_key=document_id,   # single-partition — cheap
            ))
            return [self._to_list_item(i) for i in items]
        except Exception as exc:
            logger.warning("CosmosDB list_by_document failed: %s", exc)
            return []

    # ─── Delete ──────────────────────────────────────────────────────────────

    async def delete_sessions_by_document(self, document_id: str) -> int:
        """
        Delete ALL sessions (legacy + optimized) for a given document_id.
        Returns the count of items deleted.
        Since the document_id is the partition key we can do a cheap
        single-partition query then delete each item individually.
        """
        if self._container is None:
            return 0
        try:
            # Fetch only id fields — minimal read units consumed
            items = list(self._container.query_items(
                query="SELECT c.id FROM c WHERE c.document_id = @doc_id",
                parameters=[{"name": "@doc_id", "value": document_id}],
                partition_key=document_id,
            ))
            for item in items:
                self._container.delete_item(item=item["id"], partition_key=document_id)
            logger.info(
                "CosmosDB: deleted %d session(s) for document_id=%s",
                len(items), document_id,
            )
            return len(items)
        except Exception as exc:
            logger.error("CosmosDB delete_sessions_by_document failed: %s", exc)
            raise

    # ─── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _to_list_item(item: dict) -> SessionListItem:
        metrics = item.get("metrics") or {}
        findings = item.get("findings") or []
        provisions = item.get("provisions") or []
        high_risk = sum(
            1 for f in findings
            if f.get("risk_level") in ("high", "critical")
        )
        return SessionListItem(
            session_id=item["session_id"],
            document_id=item.get("document_id", ""),
            document_name=item.get("document_name", ""),
            pipeline_mode=item["pipeline_mode"],
            status=item["status"],
            created_at=item["created_at"],
            completed_at=item.get("completed_at"),
            total_duration_seconds=metrics.get("total_duration_seconds"),
            total_llm_calls=metrics.get("total_llm_calls", 0),
            total_tokens_used=metrics.get("total_tokens_used", 0),
            provisions_count=metrics.get("provisions_categorized", len(provisions)),
            relevant_count=metrics.get("provisions_relevant", 0),
            clauses_count=metrics.get("clauses_extracted", 0),
            findings_count=len(findings),
            high_risk_count=high_risk,
            error_message=item.get("error_message"),
        )

