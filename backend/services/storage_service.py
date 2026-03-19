"""
Azure Blob Storage service — upload, download, list and delete document blobs.
"""
from __future__ import annotations

import io
import logging
from typing import BinaryIO

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient, ContentSettings

from config import get_settings

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self) -> None:
        settings = get_settings()
        account_url = f"https://{settings.azure_blob_storage_name}.blob.core.windows.net"
        self._client = BlobServiceClient(
            account_url=account_url,
            credential=settings.azure_credential,
        )
        self._container = settings.azure_storage_container
        self._ensure_container()

    def _ensure_container(self) -> None:
        try:
            self._client.create_container(self._container)
        except ResourceExistsError:
            pass

    async def upload_document(
        self, file_data: BinaryIO, filename: str, content_type: str = "application/pdf"
    ) -> tuple[str, int]:
        """Upload a file and return (blob_url, size_bytes)."""
        container_client = self._client.get_container_client(self._container)
        blob_client = container_client.get_blob_client(filename)

        data = file_data.read()
        blob_client.upload_blob(
            io.BytesIO(data),
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        url = blob_client.url
        logger.info("Uploaded %s → %s (%d bytes)", filename, url, len(data))
        return url, len(data)

    async def download_document(self, filename: str) -> bytes:
        """Download a blob by name and return raw bytes."""
        blob_client = self._client.get_container_client(self._container).get_blob_client(filename)
        stream = blob_client.download_blob()
        return stream.readall()

    async def upload_text(self, content: str, blob_name: str) -> str:
        """Upload plain-text content and return blob URL."""
        container_client = self._client.get_container_client(self._container)
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(
            content.encode("utf-8"),
            overwrite=True,
            content_settings=ContentSettings(content_type="text/plain"),
        )
        return blob_client.url

    def list_documents(self) -> list[dict]:
        container_client = self._client.get_container_client(self._container)
        return [
            {
                "name": b.name,
                "size": b.size,
                "last_modified": b.last_modified.isoformat() if b.last_modified else None,
                "url": f"{self._client.url}{self._container}/{b.name}",
            }
            for b in container_client.list_blobs()
        ]
