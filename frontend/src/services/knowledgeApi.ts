import axios from 'axios';
import type {
  BatchJob,
  ChatMessage,
  Citation,
  EntityDetail,
  Finding,
  GraphData,
  OverrideProposal,
  Persona,
  Rule,
  RuleEvalResult,
  SMEAmendment,
  TelemetrySummary,
} from '../types/knowledge';

const api = axios.create({ baseURL: '/api' });

// ── Ingested documents ────────────────────────────────────────────────────────

export async function fetchIngestedDocuments(): Promise<string[]> {
  const { data } = await api.get<{ names: string[] }>('/knowledge/ingested-documents');
  return data.names;
}

// ── Chat ──────────────────────────────────────────────────────────────────────

export interface ChatRequest {
  question: string;
  persona?: Persona | null;
  session_history?: { role: string; content: string }[];
  instrument_urn?: string;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  intent: string;
  entity_hint?: string;
  confidence: number;
}

export async function sendChat(req: ChatRequest): Promise<ChatResponse> {
  const { data } = await api.post<ChatResponse>('/knowledge/chat', req);
  return data;
}

/**
 * SSE streaming chat.
 * Calls `onToken` for each streamed token, then `onDone` with final citations.
 */
export function streamChat(
  req: ChatRequest,
  onToken: (token: string) => void,
  onDone: (citations: Citation[]) => void,
  onError?: (err: string) => void,
): () => void {
  const ctrl = new AbortController();

  (async () => {
    try {
      const resp = await fetch('/api/knowledge/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
        signal: ctrl.signal,
      });

      if (!resp.ok || !resp.body) {
        onError?.(`HTTP ${resp.status}`);
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const payload = JSON.parse(line.slice(6));
            if (payload.token) onToken(payload.token);
            if (payload.done) onDone(payload.citations ?? []);
            if (payload.error) onError?.(payload.error);
          } catch {
            // ignore malformed chunk
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== 'AbortError') {
        onError?.(err.message);
      }
    }
  })();

  return () => ctrl.abort();
}

// ── Graph ─────────────────────────────────────────────────────────────────────

export async function fetchGraph(persona?: Persona | null, hint?: string): Promise<GraphData> {
  const params: Record<string, string> = {};
  if (persona) params.persona = persona;
  if (hint) params.hint = hint;
  const { data } = await api.get<GraphData>('/knowledge/graph', { params });
  return data;
}

// ── Entities ──────────────────────────────────────────────────────────────────

export async function searchEntities(q: string): Promise<{ entities: EntityDetail[] }> {
  const { data } = await api.get('/knowledge/entities', { params: { q } });
  return data;
}

export async function getEntity(
  entityId: string,
): Promise<{ detail: EntityDetail[]; findings: Finding[] }> {
  const { data } = await api.get(`/knowledge/entity/${encodeURIComponent(entityId)}`);
  // Map SPARQL field names to frontend Finding shape
  const findings: Finding[] = (data.findings ?? []).map((f: any) => ({
    findingUri: f.finding ?? '',
    ruleRef:    f.ruleId ?? f.ruleRef ?? '',
    verdict:    f.findingType ?? f.verdict ?? 'unknown',
    verbatim:   f.verbatim ?? '',
    page:       Number(f.page) || 0,
    section:    f.section ?? '',
  }));
  return { detail: data.detail ?? [], findings };
}

export async function getNonCompliant(): Promise<{ findings: Finding[] }> {
  const { data } = await api.get('/knowledge/non-compliant');
  return data;
}

// ── Rules ─────────────────────────────────────────────────────────────────────

export async function fetchRules(use_case?: string): Promise<{ rules: Rule[] }> {
  const params: Record<string, string> = {};
  if (use_case) params.use_case = use_case;
  const { data } = await api.get('/knowledge/rules', { params });
  return data;
}

export async function evaluateRule(
  ruleId: string,
  instrumentUrn: string,
): Promise<RuleEvalResult> {
  const { data } = await api.post(`/knowledge/rules/${ruleId}/evaluate`, null, {
    params: { instrument_urn: instrumentUrn },
  });
  return data;
}

// ── Feedback ──────────────────────────────────────────────────────────────────

export interface FeedbackPayload {
  question: string;
  answer_excerpt: string;
  sentiment: 'positive' | 'negative' | 'neutral';
  rule_id?: string;
  instrument_urn?: string;
  persona?: string;
  comment?: string;
}

export async function submitFeedback(payload: FeedbackPayload): Promise<void> {
  await api.post('/knowledge/feedback', payload);
}

// ── SME Queue ─────────────────────────────────────────────────────────────────

export async function fetchSmeQueue(): Promise<{
  proposals: OverrideProposal[];
  amendments: SMEAmendment[];
}> {
  const { data } = await api.get('/knowledge/sme-queue');
  return data;
}

export async function approveAmendment(
  amendmentId: string,
  smeName: string,
  comment: string,
): Promise<void> {
  await api.post(`/knowledge/sme-queue/amendments/${amendmentId}/approve`, {
    sme_name: smeName,
    comment,
  });
}

export async function rejectAmendment(
  amendmentId: string,
  smeName: string,
  reason: string,
): Promise<void> {
  await api.post(`/knowledge/sme-queue/amendments/${amendmentId}/reject`, {
    sme_name: smeName,
    reason,
  });
}

// ── Batch ─────────────────────────────────────────────────────────────────────

export async function submitBatchJob(
  documentId: string,
  priority: 'NORMAL' | 'HIGH' | 'CRITICAL' = 'NORMAL',
): Promise<BatchJob> {
  const { data } = await api.post<BatchJob>('/batch/submit', {
    document_id: documentId,
    priority,
    submitted_by: 'user',
  });
  return data;
}

export async function getBatchJobStatus(jobId: string): Promise<BatchJob> {
  const { data } = await api.get<BatchJob>(`/batch/status/${jobId}`);
  return data;
}

export async function listBatchJobs(status?: string): Promise<BatchJob[]> {
  const params: Record<string, string> = {};
  if (status) params.status = status;
  const { data } = await api.get<BatchJob[]>('/batch/jobs', { params });
  return data;
}

// ── Telemetry ─────────────────────────────────────────────────────────────────

export async function fetchTelemetry(): Promise<TelemetrySummary> {
  const { data } = await api.get<TelemetrySummary>('/knowledge/telemetry');
  return data;
}
