import axios from 'axios'
import type {
  ComparisonMetrics,
  DocumentInfo,
  DocumentUploadResponse,
  PipelineMode,
  ProcessDocumentRequest,
  ProcessingSession,
  ProcessingStatusResponse,
  SessionListItem,
} from '../types'

const api = axios.create({ baseURL: '/api' })

// ─── Documents ───────────────────────────────────────────────────────────────

export async function listDocuments(): Promise<DocumentInfo[]> {
  const { data } = await api.get<DocumentInfo[]>('/documents/')
  return data
}

export async function getSyntheticDocument(): Promise<DocumentInfo> {
  const { data } = await api.get<DocumentInfo>('/documents/synthetic')
  return data
}

export async function uploadDocument(file: File): Promise<DocumentUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<DocumentUploadResponse>('/documents/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

// ─── Processing ───────────────────────────────────────────────────────────────

export async function startProcessing(
  documentId: string,
  mode: PipelineMode,
  documentName?: string,
  enableIndexing = false
): Promise<ProcessingStatusResponse> {
  const body: ProcessDocumentRequest = {
    document_id: documentId,
    pipeline_mode: mode,
    document_name: documentName,
    enable_indexing: enableIndexing,
  }
  const { data } = await api.post<ProcessingStatusResponse>('/processing/start', body)
  return data
}

export async function getProcessingStatus(sessionId: string): Promise<ProcessingStatusResponse> {
  const { data } = await api.get<ProcessingStatusResponse>(`/processing/status/${sessionId}`)
  return data
}

export async function getProcessingResult(sessionId: string): Promise<ProcessingSession> {
  const { data } = await api.get<ProcessingSession>(`/processing/result/${sessionId}`)
  return data
}

export async function getComparisonMetrics(documentId: string): Promise<ComparisonMetrics> {
  const { data } = await api.get<ComparisonMetrics>(`/processing/compare/${documentId}`)
  return data
}

// ─── Sessions ────────────────────────────────────────────────────────────────

export async function listSessions(limit = 50): Promise<SessionListItem[]> {
  const { data } = await api.get<SessionListItem[]>('/sessions/', { params: { limit } })
  return data
}

export async function listSessionsByDocument(documentId: string): Promise<SessionListItem[]> {
  const { data } = await api.get<SessionListItem[]>(`/sessions/by-document/${documentId}`)
  return data
}

export async function getSession(sessionId: string, documentId?: string): Promise<ProcessingSession> {
  const params = documentId ? { document_id: documentId } : undefined
  const { data } = await api.get<ProcessingSession>(`/sessions/${sessionId}`, { params })
  return data
}

export async function deleteDocumentSessions(documentId: string): Promise<{ deleted: number }> {
  const { data } = await api.delete<{ deleted: number }>(`/sessions/by-document/${documentId}`)
  return data
}
