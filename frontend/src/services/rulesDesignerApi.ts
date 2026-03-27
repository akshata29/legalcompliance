import axios from 'axios';

const api = axios.create({ baseURL: '/api' });

export interface RulePayload {
  id: string;
  version: string;
  name: string;
  regulation: string;
  use_case: string;
  condition: string;
  obligation: string;
  evidence_fields: string[];
  confidence_threshold: number;
  human_review_trigger: string;
  effective_from: string;
  effective_until?: string | null;
  supersedes?: string | null;
  keywords: string[];
  description: string;
}

export interface RulesListResponse {
  rules: RulePayload[];
  grouped: Record<string, RulePayload[]>;
  total: number;
}

export async function listAllRules(): Promise<RulesListResponse> {
  const { data } = await api.get<RulesListResponse>('/rules-designer/');
  return data;
}

export async function getRuleById(ruleId: string): Promise<RulePayload> {
  const { data } = await api.get<RulePayload>(`/rules-designer/${encodeURIComponent(ruleId)}`);
  return data;
}

export async function createRule(payload: RulePayload): Promise<RulePayload> {
  const { data } = await api.post<RulePayload>('/rules-designer/', payload);
  return data;
}

export async function updateRule(ruleId: string, payload: RulePayload): Promise<RulePayload> {
  const { data } = await api.put<RulePayload>(`/rules-designer/${encodeURIComponent(ruleId)}`, payload);
  return data;
}

export async function deleteRule(ruleId: string): Promise<void> {
  await api.delete(`/rules-designer/${encodeURIComponent(ruleId)}`);
}

export async function reloadRules(): Promise<{ reloaded: boolean; rule_count: number }> {
  const { data } = await api.post('/rules-designer/reload');
  return data;
}
