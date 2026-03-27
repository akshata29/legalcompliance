// Knowledge Graph — TypeScript type definitions

// ── Graph visualisation ───────────────────────────────────────────────────────

export interface OntologyNode {
  id: string;           // URN
  label: string;
  type: string;         // CLO | ABS | RMBS | Originator | Finding | …
  properties?: Record<string, string | number | boolean>;
  persona_visible?: string[];
}

export interface Relation {
  id: string;
  source: string;
  target: string;
  relation: string;     // predicate label
  weight?: number;
}

export interface GraphData {
  nodes: OntologyNode[];
  edges: Relation[];
}

// ── Chat / conversation ───────────────────────────────────────────────────────

export type Persona = 'trader' | 'compliance' | 'legal' | 'data_mgmt';

export interface Citation {
  document_id: string;
  page: number | null;
  section: string | null;
  verbatim: string | null;
  rule_id: string | null;
  confidence: number;
  provision_urn: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  intent?: string;
  timestamp: string;
  loading?: boolean;
}

// ── Rules ─────────────────────────────────────────────────────────────────────

export interface Rule {
  rule_id: string;
  name: string;
  use_case: string;
  regulation: string;
  description: string;
  version: string;
  confidence_threshold: number;
}

export interface RuleEvalResult {
  rule_id: string;
  instrument_urn: string;
  verdict: 'compliant' | 'non_compliant' | 'insufficient_evidence';
  confidence: number;
  explanation: string;
  evidence: string[];
  human_review_required: boolean;
  sparql_trace?: string;
}

// ── Batch jobs ────────────────────────────────────────────────────────────────

export interface BatchJob {
  job_id: string;
  created_at: string;
  document_id: string;
  document_url?: string;
  priority: number;
  status: 'queued' | 'running' | 'done' | 'failed';
  progress: number;
  started_at?: string;
  completed_at?: string;
  error?: string;
  result_summary?: {
    triples_added: number;
    instruments_found: number;
    findings_recorded: number;
  };
  submitted_by: string;
}

// ── SME Queue ─────────────────────────────────────────────────────────────────

export interface OverrideProposal {
  proposal_id: string;
  created_at: string;
  rule_id: string;
  instrument_urn: string;
  proposed_verdict: string;
  confidence: number;
  evidence_summary: string;
  source: string;
  status: string;
  reviewed_by?: string;
  reviewer_comment?: string;
}

export interface SMEAmendment {
  amendment_id: string;
  rule_id: string;
  current_version: string;
  proposed_version: string;
  changes: Record<string, { old: unknown; new: unknown }>;
  supporting_proposals: string[];
  bdd_passed: boolean;
  created_at: string;
  status: string;
}

// ── Telemetry ─────────────────────────────────────────────────────────────────

export interface TelemetrySummary {
  total_queries: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  sla_breach_count: number;
  sla_breach_rate: number;
  intent_distribution: Record<string, number>;
  recent_errors: string[];
}

// ── Entity detail ─────────────────────────────────────────────────────────────

export interface EntityDetail {
  uri: string;
  predicate: string;
  value: string;
}

export interface Finding {
  findingUri: string;
  ruleRef: string;
  verdict: string;
  verbatim: string;
  page: number;
  section: string;
}
