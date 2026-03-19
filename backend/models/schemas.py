"""Pydantic schemas shared across the application."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ────────────────────────────────────────────────────────────────────────────
# Enums
# ────────────────────────────────────────────────────────────────────────────

class PipelineMode(str, Enum):
    LEGACY = "legacy"
    OPTIMIZED = "optimized"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    EXTRACTING = "extracting"        # Document Intelligence
    CHUNKING = "chunking"
    INDEXING = "indexing"            # AI Search
    CATEGORIZING = "categorizing"    # LLM phase A
    EXTRACTING_CLAUSES = "extracting_clauses"  # LLM phase B
    ANALYZING = "analyzing"          # LLM phase C
    COMPLETE = "complete"
    FAILED = "failed"


class FindingType(str, Enum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    NEEDS_REVIEW = "needs_review"
    NOT_APPLICABLE = "not_applicable"


# ────────────────────────────────────────────────────────────────────────────
# Document Models
# ────────────────────────────────────────────────────────────────────────────

class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    blob_url: str
    size_bytes: int
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentInfo(BaseModel):
    document_id: str
    filename: str
    blob_url: str
    page_count: Optional[int] = None
    provision_count: Optional[int] = None
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    status: ProcessingStatus = ProcessingStatus.PENDING


# ────────────────────────────────────────────────────────────────────────────
# Provision Models
# ────────────────────────────────────────────────────────────────────────────

class Provision(BaseModel):
    provision_id: str = Field(default_factory=lambda: str(uuid4()))
    text: str
    page_number: Optional[int] = None
    section: Optional[str] = None
    token_count: Optional[int] = None


class CategorizedProvision(BaseModel):
    provision_id: str
    provision_text: str
    relevant: bool
    categories: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    llm_call_index: Optional[int] = None      # Which LLM call produced this
    prefiltered: bool = False                   # Was it removed by the pre-filter?


class ExtractedClause(BaseModel):
    clause_id: str = Field(default_factory=lambda: str(uuid4()))
    provision_id: str
    clause_text: str
    rule_category: str
    obligation_type: str = ""                  # "shall", "must", "may", etc.


class ClauseFinding(BaseModel):
    clause_id: str
    provision_id: str
    rule_category: str
    finding: FindingType
    justification: str
    risk_level: str = "medium"                 # low / medium / high / critical
    recommendation: Optional[str] = None


# ────────────────────────────────────────────────────────────────────────────
# Processing Session Models
# ────────────────────────────────────────────────────────────────────────────

class PhaseMetrics(BaseModel):
    phase: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    llm_calls: int = 0
    items_processed: int = 0
    tokens_used: int = 0
    api_errors: int = 0


class PipelineMetrics(BaseModel):
    total_duration_seconds: Optional[float] = None
    phases: list[PhaseMetrics] = Field(default_factory=list)
    total_llm_calls: int = 0
    total_tokens_used: int = 0
    provisions_prefiltered: int = 0       # Eliminated by keyword pre-filter (Optimized only)
    provisions_categorized: int = 0       # Total provisions fed into the pipeline
    provisions_relevant: int = 0          # LLM (or pre-filter) said relevant
    provisions_llm_not_relevant: int = 0  # Reached LLM but classified as not-relevant
    clauses_extracted: int = 0
    findings_generated: int = 0


class ProcessingSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str
    document_name: str
    pipeline_mode: PipelineMode
    status: ProcessingStatus = ProcessingStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    metrics: PipelineMetrics = Field(default_factory=PipelineMetrics)
    provisions: list[CategorizedProvision] = Field(default_factory=list)
    clauses: list[ExtractedClause] = Field(default_factory=list)
    findings: list[ClauseFinding] = Field(default_factory=list)
    error_message: Optional[str] = None


# ────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ────────────────────────────────────────────────────────────────────────────

class ProcessDocumentRequest(BaseModel):
    document_id: str
    pipeline_mode: PipelineMode = PipelineMode.LEGACY
    document_name: Optional[str] = None
    enable_indexing: bool = False   # when False the AI Search indexing step is skipped


class ProcessingStatusResponse(BaseModel):
    session_id: str
    status: ProcessingStatus
    pipeline_mode: PipelineMode
    current_phase: Optional[str] = None
    progress_pct: int = 0
    metrics: PipelineMetrics
    error_message: Optional[str] = None


class ComparisonMetrics(BaseModel):
    """Side-by-side metrics for legacy vs optimised runs on the same document."""
    document_id: str
    legacy_session_id: Optional[str] = None
    optimized_session_id: Optional[str] = None
    legacy_metrics: Optional[PipelineMetrics] = None
    optimized_metrics: Optional[PipelineMetrics] = None
    speedup_factor: Optional[float] = None
    llm_call_reduction_pct: Optional[float] = None
    token_reduction_pct: Optional[float] = None


class SessionListItem(BaseModel):
    session_id: str
    document_id: str
    document_name: str
    pipeline_mode: PipelineMode
    status: ProcessingStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    total_duration_seconds: Optional[float] = None
    total_llm_calls: int = 0
    total_tokens_used: int = 0
    provisions_count: int = 0
    relevant_count: int = 0
    clauses_count: int = 0
    findings_count: int = 0
    high_risk_count: int = 0    # findings with risk_level high|critical
    error_message: Optional[str] = None


class SyntheticDocumentInfo(BaseModel):
    document_id: str = "synthetic-001"
    filename: str = "eu_sec_150page.txt"
    description: str = "Synthetic EU Securitisation CLO Offering Circular (150 pages, ~1765 provisions)"
    provision_count: int = 1765
