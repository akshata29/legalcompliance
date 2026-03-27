"""
Azure AI Search service — index and query document chunks + provision vectors.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
    SearchableField,
)
from azure.search.documents.models import VectorizedQuery
from openai import AzureOpenAI

from config import get_settings

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings

        # Use credential-based auth for search (key is stored as a secret name in .env)
        # If SEARCH_API_KEY_SECRET_NAME is the actual key value (common in dev), use it directly
        self._credential = AzureKeyCredential(settings.search_api_key_secret_name)
        self._endpoint = settings.search_endpoint
        self._index_name = settings.search_index

        self._index_client = SearchIndexClient(
            endpoint=self._endpoint, credential=self._credential
        )
        self._search_client = SearchClient(
            endpoint=self._endpoint,
            index_name=self._index_name,
            credential=self._credential,
        )
        self._openai = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        self._embedding_model = settings.azure_openai_embedding_deployment_name
        self._ensure_index()

    def _ensure_index(self) -> None:
        """Create the search index if it doesn't exist."""
        try:
            existing = [idx.name for idx in self._index_client.list_indexes()]
            if self._index_name in existing:
                return

            fields = [
                SimpleField(name="id", type=SearchFieldDataType.String, key=True),
                SimpleField(name="document_id", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="session_id", type=SearchFieldDataType.String, filterable=True),
                SearchableField(name="text", type=SearchFieldDataType.String),
                SearchableField(name="section", type=SearchFieldDataType.String),
                SimpleField(name="page_number", type=SearchFieldDataType.Int32, filterable=True),
                SearchField(
                    name="text_vector",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=1536,
                    vector_search_profile_name="hnsw-profile",
                ),
            ]
            vector_search = VectorSearch(
                algorithms=[HnswAlgorithmConfiguration(name="hnsw-algo")],
                profiles=[
                    VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw-algo")
                ],
            )
            index = SearchIndex(name=self._index_name, fields=fields, vector_search=vector_search)
            self._index_client.create_index(index)
            logger.info("Created AI Search index: %s", self._index_name)
        except Exception as exc:
            logger.warning("AI Search index setup failed: %s", exc)

    def _embed(self, text: str) -> list[float]:
        response = self._openai.embeddings.create(
            input=text, model=self._embedding_model
        )
        return response.data[0].embedding

    def index_provisions(
        self, document_id: str, session_id: str, provisions: list[dict]
    ) -> int:
        """Embed and index all provisions. Returns count indexed.
        Synchronous — call via asyncio.to_thread() from async contexts to avoid blocking."""
        docs = []
        for p in provisions:
            try:
                vector = self._embed(p["text"][:8000])
            except Exception as exc:
                logger.warning("Embedding failed for provision %s: %s", p["provision_id"], exc)
                vector = [0.0] * 1536
            docs.append(
                {
                    "id": p["provision_id"],
                    "document_id": document_id,
                    "session_id": session_id,
                    "text": p["text"],
                    "section": p.get("section", ""),
                    "page_number": p.get("page_number", 1),
                    "text_vector": vector,
                }
            )
        try:
            result = self._search_client.upload_documents(docs)
            succeeded = sum(1 for r in result if r.succeeded)
            logger.info("Indexed %d/%d provisions", succeeded, len(docs))
            return succeeded
        except Exception as exc:
            logger.warning("AI Search upload failed: %s", exc)
            return 0

    async def semantic_search(
        self, query: str, document_id: Optional[str] = None, top: int = 5
    ) -> list[dict]:
        """Async wrapper — runs sync search in a thread so the event loop is never blocked."""
        import asyncio
        return await asyncio.to_thread(self._sync_semantic_search, query, document_id, top)

    def _sync_semantic_search(
        self, query: str, document_id: Optional[str] = None, top: int = 5
    ) -> list[dict]:
        """Synchronous vector similarity search over indexed provisions."""
        try:
            query_vector = self._embed(query)
            vector_query = VectorizedQuery(
                vector=query_vector,
                k_nearest_neighbors=top,
                fields="text_vector",
            )
            filter_expr = f"document_id eq '{document_id}'" if document_id else None
            results = self._search_client.search(
                search_text=None,
                vector_queries=[vector_query],
                filter=filter_expr,
                top=top,
            )
            return [
                {
                    "provision_id": r["id"],
                    "text": r["text"],
                    "score": r["@search.score"],
                    "section": r.get("section"),
                }
                for r in results
            ]
        except Exception as exc:
            logger.warning("AI Search query failed: %s", exc)
            return []

    def delete_document(self, document_id: str) -> int:
        """Delete all indexed provisions for a document. Returns count deleted.
        Synchronous — call via asyncio.to_thread() from async contexts."""
        try:
            # Fetch all IDs for this document first (Search SDK requires IDs to delete)
            results = self._search_client.search(
                search_text="*",
                filter=f"document_id eq '{document_id}'",
                select=["id"],
                top=1000,
            )
            ids = [{"id": r["id"]} for r in results]
            if not ids:
                return 0
            self._search_client.delete_documents(ids)
            logger.info("Deleted %d AI Search docs for document_id=%s", len(ids), document_id)
            return len(ids)
        except Exception as exc:
            logger.warning("AI Search delete failed for %s: %s", document_id, exc)
            return 0
