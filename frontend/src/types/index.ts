// ─── Enums ────────────────────────────────────────────────────────────────────

export type PipelineMode = 'legacy' | 'optimized'

export type ProcessingStatus =
  | 'pending'
  | 'uploading'
  | 'extracting'
  | 'chunking'
  | 'indexing'
  | 'categorizing'
  | 'extracting_clauses'
  | 'analyzing'
  | 'complete'
  | 'failed'

export type FindingType =
  | 'compliant'
  | 'non_compliant'
  | 'needs_review'
  | 'not_applicable'

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

// ─── Document ─────────────────────────────────────────────────────────────────

export interface DocumentInfo {
  document_id: string
  filename: string
  blob_url: string
  page_count?: number
  provision_count?: number
  uploaded_at: string
  processed_at?: string
  status: ProcessingStatus
}

export interface DocumentUploadResponse {
  document_id: string
  filename: string
  blob_url: string
  size_bytes: number
  uploaded_at: string
}

// ─── Provisions & Clauses ─────────────────────────────────────────────────────

export interface CategorizedProvision {
  provision_id: string
  provision_text: string
  relevant: boolean
  categories: string[]
  confidence: number
  llm_call_index?: number
  prefiltered: boolean
}

export interface ExtractedClause {
  clause_id: string
  provision_id: string
  clause_text: string
  rule_category: string
  obligation_type: string
}

export interface ClauseFinding {
  clause_id: string
  provision_id: string
  rule_category: string
  finding: FindingType
  justification: string
  risk_level: RiskLevel
  recommendation?: string
}

// ─── Metrics ──────────────────────────────────────────────────────────────────

export interface CapturedLlmCall {
  phase: string
  call_index: number
  system_prompt: string
  user_prompt: string
  response_text: string
  input_tokens: number
  output_tokens: number
  latency_ms: number
}

export interface PrefilterSample {
  provision_id: string
  text: string
  passed: boolean
  reason: string
  matched_categories: string[]
  matched_terms: string[]
}

export interface PhaseMetrics {
  phase: string
  started_at?: string
  completed_at?: string
  duration_seconds?: number
  llm_calls: number
  items_processed: number
  tokens_used: number
  api_errors: number
  pipelined: boolean
}

export interface PipelineMetrics {
  total_duration_seconds?: number
  phases: PhaseMetrics[]
  total_llm_calls: number
  total_tokens_used: number
  provisions_prefiltered: number
  provisions_categorized: number
  provisions_relevant: number
  provisions_llm_not_relevant: number  // reached LLM but classified as not-relevant
  clauses_extracted: number
  findings_generated: number
  prompt_samples: CapturedLlmCall[]
  prefilter_samples: PrefilterSample[]
}

// ─── Session ──────────────────────────────────────────────────────────────────

export interface ProcessingSession {
  session_id: string
  document_id: string
  document_name: string
  pipeline_mode: PipelineMode
  status: ProcessingStatus
  created_at: string
  updated_at: string
  completed_at?: string
  metrics: PipelineMetrics
  provisions: CategorizedProvision[]
  clauses: ExtractedClause[]
  findings: ClauseFinding[]
  error_message?: string
}

export interface ProcessingStatusResponse {
  session_id: string
  status: ProcessingStatus
  pipeline_mode: PipelineMode
  current_phase?: string
  progress_pct: number
  metrics: PipelineMetrics
  error_message?: string
}

export interface SessionListItem {
  session_id: string
  document_id: string
  document_name: string
  pipeline_mode: PipelineMode
  status: ProcessingStatus
  created_at: string
  completed_at?: string
  total_duration_seconds?: number
  total_llm_calls: number
  total_tokens_used: number
  provisions_count: number
  relevant_count: number
  clauses_count: number
  findings_count: number
  high_risk_count: number
  error_message?: string
}

// ─── Comparison ───────────────────────────────────────────────────────────────

export interface ComparisonMetrics {
  document_id: string
  legacy_session_id?: string
  optimized_session_id?: string
  legacy_metrics?: PipelineMetrics
  optimized_metrics?: PipelineMetrics
  speedup_factor?: number
  llm_call_reduction_pct?: number
  token_reduction_pct?: number
}

// ─── Requests ─────────────────────────────────────────────────────────────────

export interface ProcessDocumentRequest {
  document_id: string
  pipeline_mode: PipelineMode
  document_name?: string
  enable_indexing?: boolean
}
