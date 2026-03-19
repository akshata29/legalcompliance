"""
Document Intelligence service — uses prebuilt-layout model to convert
uploaded documents to Markdown, then segments them into Provisions.
Falls back gracefully when Content Understanding key is absent.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential

from config import get_settings
from models.schemas import Provision

logger = logging.getLogger(__name__)

# Paragraph-level chunking: treat each block of ≥50 words as a provision candidate
_MIN_PROVISION_WORDS = 40
_MAX_PROVISION_WORDS = 600


class DocumentService:
    def __init__(self) -> None:
        settings = get_settings()
        self._doc_client = DocumentIntelligenceClient(
            endpoint=settings.document_intelligence_endpoint,
            credential=AzureKeyCredential(settings.document_intelligence_api_key),
        )

    # ─── Public API ──────────────────────────────────────────────────────────

    async def analyse_document_bytes(
        self, data: bytes, content_type: str = "application/pdf"
    ) -> tuple[str, int]:
        """
        Run prebuilt-layout over raw document bytes.
        Returns (markdown_content, page_count).
        """
        poller = self._doc_client.begin_analyze_document(
            "prebuilt-layout",
            body=AnalyzeDocumentRequest(bytes_source=data),
            output_content_format="markdown",
        )
        result = poller.result()
        markdown = result.content or ""
        page_count = len(result.pages) if result.pages else 1
        logger.info("Document Intelligence: %d pages, %d chars markdown", page_count, len(markdown))
        return markdown, page_count

    async def analyse_document_url(self, url: str) -> tuple[str, int]:
        """
        Run prebuilt-layout via a blob URL (avoids re-upload).
        Returns (markdown_content, page_count).
        """
        poller = self._doc_client.begin_analyze_document(
            "prebuilt-layout",
            body=AnalyzeDocumentRequest(url_source=url),
            output_content_format="markdown",
        )
        result = poller.result()
        markdown = result.content or ""
        page_count = len(result.pages) if result.pages else 1
        return markdown, page_count

    def segment_into_provisions(
        self, markdown: str, source_filename: Optional[str] = None
    ) -> list[Provision]:
        """
        Split markdown into legal provisions.

        Strategy:
        1. Split on double-newline (paragraph boundary) or numbered list items.
        2. Filter out paragraphs that are too short (headers, whitespace).
        3. Merge short fragments with the previous provision.
        4. Assign a sequential provision_id + approximate page number.
        """
        # Normalise whitespace
        text = re.sub(r"\r\n", "\n", markdown)
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Split on paragraph boundaries OR numbered provisions like "1." / "(a)"
        raw_blocks = re.split(
            r"\n\n+|(?=\n\s*(?:\d+\.|[A-Z]\.|Article\s+\d+|Section\s+\d+|\(\w+\)))",
            text,
        )

        provisions: list[Provision] = []
        carry = ""

        for block in raw_blocks:
            cleaned = block.strip()
            if not cleaned:
                continue
            combined = (carry + " " + cleaned).strip() if carry else cleaned
            word_count = len(combined.split())

            if word_count < _MIN_PROVISION_WORDS:
                carry = combined          # too short — merge with next
                continue

            if word_count > _MAX_PROVISION_WORDS:
                # Chunk at sentence boundary
                sentences = re.split(r"(?<=[.!?])\s+", combined)
                chunk, chunk_words = "", 0
                for sent in sentences:
                    sent_words = len(sent.split())
                    if chunk_words + sent_words > _MAX_PROVISION_WORDS and chunk:
                        provisions.append(
                            self._make_provision(chunk.strip(), len(provisions) + 1)
                        )
                        chunk, chunk_words = sent, sent_words
                    else:
                        chunk = (chunk + " " + sent).strip()
                        chunk_words += sent_words
                if chunk:
                    carry = chunk          # remainder merges with next block
                continue

            provisions.append(self._make_provision(combined, len(provisions) + 1))
            carry = ""

        # Flush carry
        if carry and len(carry.split()) >= _MIN_PROVISION_WORDS // 2:
            provisions.append(self._make_provision(carry.strip(), len(provisions) + 1))

        logger.info("Segmented document into %d provisions", len(provisions))
        return provisions

    # ─── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _make_provision(text: str, index: int) -> Provision:
        import uuid
        from models.schemas import Provision as P

        # Rough page estimate: assume ~400 words per page
        approx_page = max(1, (index * 3) // 5)
        return P(
            provision_id=str(uuid.uuid4()),
            text=text,
            page_number=approx_page,
            section=DocumentService._detect_section(text),
            token_count=len(text.split()) * 4 // 3,  # rough token estimate
        )

    @staticmethod
    def _detect_section(text: str) -> Optional[str]:
        """Try to infer section heading from first line."""
        first_line = text.split("\n")[0].strip()
        if len(first_line) < 80 and re.match(
            r"^(Article|Section|\d+\.|Clause|Part|Annex|##|#)", first_line
        ):
            return first_line
        return None
