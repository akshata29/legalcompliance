import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  FileText, Clock, CheckCircle2, XCircle, Zap, ChevronDown, ChevronRight,
  AlertTriangle, Play, BarChart2, ExternalLink, Trash2,
} from 'lucide-react'
import clsx from 'clsx'
import { listSessions, deleteDocumentSessions } from '../services/api'
import Header from '../components/layout/Header'
import type { ProcessingStatus, PipelineMode, SessionListItem } from '../types'

// ─── helpers ─────────────────────────────────────────────────────────────────

function fmt(n?: number) {
  if (n == null) return '—'
  if (n >= 60) return `${(n / 60).toFixed(1)} m`
  return `${n.toFixed(1)} s`
}
function fmtK(n: number) {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}
function ago(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function StatusBadge({ status }: { status: ProcessingStatus }) {
  if (status === 'complete') return <span className="badge badge-success"><CheckCircle2 size={9} className="mr-0.5" />Complete</span>
  if (status === 'failed')   return <span className="badge badge-danger"><XCircle size={9} className="mr-0.5" />Failed</span>
  return <span className="badge badge-info"><Clock size={9} className="mr-0.5" />Running</span>
}

function ModeBadge({ mode }: { mode: PipelineMode }) {
  return mode === 'optimized'
    ? <span className="badge badge-success"><Zap size={9} className="mr-0.5" />Optimized</span>
    : <span className="badge badge-warning"><Clock size={9} className="mr-0.5" />Legacy</span>
}

// ─── Stat pill ────────────────────────────────────────────────────────────────

function Stat({ label, value, warn }: { label: string; value: string | number; warn?: boolean }) {
  return (
    <div className={clsx('text-center px-3 py-1.5 rounded-lg', warn ? 'bg-danger-500/10' : 'bg-surface-700/60')}>
      <p className={clsx('text-xs font-semibold tabular-nums', warn ? 'text-danger-400' : 'text-white')}>{value}</p>
      <p className="text-[10px] text-gray-500 mt-0.5">{label}</p>
    </div>
  )
}

// ─── Single run card ─────────────────────────────────────────────────────────

function RunCard({ s }: { s: SessionListItem }) {
  const navigate = useNavigate()

  function openInProcessDoc() {
    const params = new URLSearchParams({
      recall: s.session_id,
      document_id: s.document_id,
      mode: s.pipeline_mode,
      doc_name: s.document_name,
    })
    navigate(`/process?${params.toString()}`)
  }

  return (
    <div className={clsx(
      'flex-1 rounded-xl border p-4 space-y-3 min-w-0',
      s.pipeline_mode === 'optimized' ? 'border-success-500/30 bg-success-500/5' : 'border-warning-500/30 bg-warning-500/5',
    )}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <ModeBadge mode={s.pipeline_mode} />
        <StatusBadge status={s.status} />
        <span className="text-xs text-gray-500 ml-auto">{ago(s.created_at)}</span>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Stat label="Duration"   value={fmt(s.total_duration_seconds)} />
        <Stat label="LLM Calls"  value={fmtK(s.total_llm_calls)} />
        <Stat label="Tokens"     value={fmtK(s.total_tokens_used)} />
        <Stat label="Provisions" value={s.provisions_count} />
        <Stat label="Relevant"   value={s.relevant_count} />
        <Stat label="Clauses"    value={s.clauses_count} />
        <Stat label="Findings"   value={s.findings_count} />
        <Stat label="High Risk"  value={s.high_risk_count} warn={s.high_risk_count > 0} />
      </div>

      {s.status === 'complete' && (
        <button
          className="btn-secondary w-full text-xs py-1.5"
          onClick={openInProcessDoc}
        >
          <ExternalLink size={12} /> Open in Process Doc
        </button>
      )}
    </div>
  )
}

// ─── Speedup banner ──────────────────────────────────────────────────────────

function SpeedupBanner({ legacy, optimized }: { legacy: SessionListItem; optimized: SessionListItem }) {
  if (!legacy.total_duration_seconds || !optimized.total_duration_seconds) return null
  const speedup = legacy.total_duration_seconds / optimized.total_duration_seconds
  const callReduction = legacy.total_llm_calls > 0
    ? Math.round(100 * (1 - optimized.total_llm_calls / legacy.total_llm_calls))
    : 0
  return (
    <div className="flex items-center gap-4 px-4 py-2 rounded-lg bg-primary/10 border border-primary/20 text-xs flex-wrap">
      <Zap size={13} className="text-primary-400 shrink-0" />
      <span className="text-primary-300 font-semibold">{speedup.toFixed(1)}× faster</span>
      <span className="text-gray-400">·</span>
      <span className="text-gray-300">{callReduction}% fewer LLM calls</span>
      <span className="text-gray-400">·</span>
      <span className="text-gray-300">
        {fmt(legacy.total_duration_seconds)} → {fmt(optimized.total_duration_seconds)}
      </span>
    </div>
  )
}

// ─── Document group row ───────────────────────────────────────────────────────

interface DocumentGroup {
  document_id: string
  document_name: string
  legacy?: SessionListItem
  optimized?: SessionListItem
  latest: string  // ISO date for sorting
}

function groupByDocument(sessions: SessionListItem[]): DocumentGroup[] {
  const map = new Map<string, DocumentGroup>()
  for (const s of sessions) {
    let g = map.get(s.document_id)
    if (!g) {
      g = { document_id: s.document_id, document_name: s.document_name, latest: s.created_at }
      map.set(s.document_id, g)
    }
    if (s.pipeline_mode === 'legacy') {
      if (!g.legacy || s.created_at > g.legacy.created_at) g.legacy = s
    } else {
      if (!g.optimized || s.created_at > g.optimized.created_at) g.optimized = s
    }
    if (s.created_at > g.latest) g.latest = s.created_at
    g.document_name = s.document_name  // keep most recent name
  }
  return Array.from(map.values()).sort((a, b) => b.latest.localeCompare(a.latest))
}

function DocumentGroupRow({ group }: { group: DocumentGroup }) {
  const [open, setOpen] = useState(true)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const hasBoth = !!group.legacy && !!group.optimized
  const queryClient = useQueryClient()

  const deleteMutation = useMutation({
    mutationFn: () => deleteDocumentSessions(group.document_id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })

  return (
    <div className="card space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <button
          className="flex-1 flex items-center gap-3 text-left min-w-0"
          onClick={() => setOpen(o => !o)}
        >
          {open ? <ChevronDown size={14} className="text-gray-500 shrink-0" /> : <ChevronRight size={14} className="text-gray-500 shrink-0" />}
          <FileText size={15} className="text-gray-400 shrink-0" />
          <span className="text-white font-medium text-sm flex-1 truncate">{group.document_name}</span>
          <div className="flex items-center gap-1.5 shrink-0 flex-wrap">
            {group.legacy    && <ModeBadge mode="legacy" />}
            {group.optimized && <ModeBadge mode="optimized" />}
            {hasBoth && <span className="badge badge-info"><BarChart2 size={9} className="mr-0.5" />Compared</span>}
          </div>
          <span className="text-xs text-gray-500 ml-2 shrink-0">{ago(group.latest)}</span>
        </button>

        {/* Delete controls */}
        {confirmDelete ? (
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="text-xs text-gray-400">Delete all runs?</span>
            <button
              onClick={() => { deleteMutation.mutate(); setConfirmDelete(false) }}
              disabled={deleteMutation.isPending}
              className="text-xs font-semibold text-danger-400 hover:text-danger-300 transition-colors px-2 py-0.5 rounded border border-danger-500/40 hover:border-danger-400"
            >
              {deleteMutation.isPending ? 'Deleting…' : 'Delete'}
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="text-xs text-gray-500 hover:text-gray-300 transition-colors px-2 py-0.5"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            onClick={() => setConfirmDelete(true)}
            className="shrink-0 p-1.5 rounded-lg text-gray-600 hover:text-danger-400 hover:bg-danger-500/10 transition-all"
            title="Delete all sessions for this document"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>

      {open && (
        <div className="space-y-3 pl-6">
          {/* Speedup banner when both exist */}
          {hasBoth && <SpeedupBanner legacy={group.legacy!} optimized={group.optimized!} />}

          {/* Side-by-side run cards */}
          <div className={clsx('flex gap-3', !hasBoth && 'max-w-sm')}>
            {group.legacy    && <RunCard s={group.legacy} />}
            {group.optimized && <RunCard s={group.optimized} />}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Sessions() {
  const navigate = useNavigate()

  const { data: sessions, isLoading, error } = useQuery({
    queryKey: ['sessions'],
    queryFn: () => listSessions(100),
    refetchInterval: 15_000,
  })

  const groups = sessions ? groupByDocument(sessions) : []

  return (
    <div className="flex-1 flex flex-col min-h-screen">
      <Header
        title="Processing Sessions"
        subtitle="Document runs stored in CosmosDB — grouped by document, paired by pipeline."
      />
      <div className="flex-1 p-6 space-y-4">
        {isLoading && (
          <div className="flex items-center justify-center h-40 text-gray-400 text-sm gap-2">
            <div className="w-4 h-4 rounded-full border-2 border-primary-400 border-t-transparent animate-spin" />
            Loading sessions…
          </div>
        )}
        {error && (
          <div className="card text-danger-400 text-sm text-center py-8">
            Failed to load sessions. Ensure the backend is running and CosmosDB is reachable.
          </div>
        )}
        {!isLoading && groups.length === 0 && (
          <div className="card text-center py-16 space-y-4">
            <FileText size={40} className="mx-auto text-gray-600" />
            <p className="text-gray-400 text-sm">No sessions yet. Run the Legacy and Optimized pipelines to see a comparison here.</p>
            <button
              className="btn-primary mx-auto"
              onClick={() => navigate('/process?doc=synthetic')}
            >
              <Play size={14} /> Run your first document
            </button>
          </div>
        )}
        {groups.map((g) => (
          <DocumentGroupRow key={g.document_id} group={g} />
        ))}
      </div>
    </div>
  )
}
