import { motion } from 'framer-motion'
import { Loader2, CheckCircle2, XCircle } from 'lucide-react'
import clsx from 'clsx'
import type { ProcessingStatus, ProcessingStatusResponse } from '../../types'

interface ProcessingStatusCardProps {
  statusData: ProcessingStatusResponse
}

const PHASES: { key: ProcessingStatus; label: string; note?: string }[] = [
  { key: 'extracting',         label: 'Phase 1 — Provision Parsing',         note: 'Document load + chunking' },
  { key: 'categorizing',       label: 'Phase 2a — LLM Categorization',       note: 'Legacy: 1 call/provision · Optimized: batch 10' },
  { key: 'extracting_clauses', label: 'Phase 2b — LLM Clause Extraction',    note: 'Legacy: 1 call/provision×rule · Optimized: async stream' },
  { key: 'analyzing',          label: 'Phase 3a — LLM Clause Analysis',      note: 'Legacy: ADecisionStep loop · Optimized: pipeline parallelism' },
  { key: 'indexing',           label: 'Phase 3b — AI Search Indexing',       note: 'Optimized only: bulk vector index' },
]

const STATUS_ORDER: ProcessingStatus[] = [
  'pending', 'uploading', 'extracting',
  'categorizing', 'extracting_clauses', 'analyzing', 'indexing', 'complete',
]

function phaseState(phaseKey: ProcessingStatus, current: ProcessingStatus): 'done' | 'active' | 'pending' {
  const ci = STATUS_ORDER.indexOf(current)
  const pi = STATUS_ORDER.indexOf(phaseKey)
  if (current === 'complete' || pi < ci) return 'done'
  if (pi === ci) return 'active'
  return 'pending'
}

export default function ProcessingStatusCard({ statusData }: ProcessingStatusCardProps) {
  const { status, progress_pct, pipeline_mode, metrics } = statusData
  const isFailed = status === 'failed'
  const isComplete = status === 'complete'
  const isRunning = !isComplete && !isFailed

  return (
    <div className="card space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isRunning && <Loader2 size={16} className="text-primary-400 animate-spin" />}
          {isComplete && <CheckCircle2 size={16} className="text-success-400" />}
          {isFailed && <XCircle size={16} className="text-danger-400" />}
          <p className="text-sm font-semibold text-white">
            {isRunning ? 'Processing…' : isComplete ? 'Processing Complete' : 'Processing Failed'}
          </p>
        </div>
        <span
          className={clsx(
            'badge',
            pipeline_mode === 'optimized' ? 'badge-success' : 'badge-warning'
          )}
        >
          {pipeline_mode === 'optimized' ? 'Optimized' : 'Legacy'}
        </span>
      </div>

      {/* Progress bar */}
      <div>
        <div className="flex justify-between text-xs text-gray-400 mb-1.5">
          <span className="capitalize">{status.replace(/_/g, ' ')}</span>
          <span>{progress_pct}%</span>
        </div>
        <div className="h-2 bg-surface-700 rounded-full overflow-hidden">
          <motion.div
            className={clsx(
              'h-full rounded-full',
              isFailed ? 'bg-danger-500' : isComplete ? 'bg-success-500' : 'bg-primary-500'
            )}
            initial={{ width: 0 }}
            animate={{ width: `${progress_pct}%` }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
          />
        </div>
      </div>

      {/* Phase steps */}
      <div className="space-y-1.5">
        {PHASES.map(({ key, label, note }) => {
          const state = phaseState(key, status)
          return (
            <div
              key={key}
              className={clsx(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-xs transition-colors',
                state === 'active' && 'bg-primary/10 border border-primary/20',
                state === 'done'   && 'opacity-60',
                state === 'pending' && 'opacity-30',
              )}
            >
              <div
                className={clsx(
                  'w-4 h-4 rounded-full flex items-center justify-center shrink-0',
                  state === 'done'   && 'bg-success/20 text-success-400',
                  state === 'active' && 'bg-primary/20 text-primary-400',
                  state === 'pending' && 'bg-surface-700 text-gray-600',
                )}
              >
                {state === 'done'   && <span className="text-[9px]">✓</span>}
                {state === 'active' && <span className="w-1.5 h-1.5 rounded-full bg-primary-400 animate-pulse" />}
                {state === 'pending' && <span className="w-1 h-1 rounded-full bg-gray-600" />}
              </div>
              <div className="flex-1 min-w-0">
                <span className={state === 'active' ? 'text-primary-300 font-medium' : 'text-gray-400'}>
                  {label}
                </span>
                {note && state === 'active' && (
                  <p className="text-[10px] text-gray-500 mt-0.5 truncate">{note}</p>
                )}
              </div>
              {state === 'active' && (
                <Loader2 size={11} className="ml-auto shrink-0 text-primary-400 animate-spin" />
              )}
            </div>
          )
        })}
      </div>

      {/* Live metrics during processing */}
      {metrics && isRunning && metrics.provisions_categorized > 0 && (
        <div className="grid grid-cols-3 gap-2 pt-2 border-t border-border">
          <div className="text-center">
            <p className="text-lg font-bold tabular-nums text-white">{metrics.provisions_categorized}</p>
            <p className="text-[10px] text-gray-500">Provisions</p>
          </div>
          <div className="text-center">
            <p className="text-lg font-bold tabular-nums text-white">{metrics.total_llm_calls}</p>
            <p className="text-[10px] text-gray-500">LLM Calls</p>
          </div>
          <div className="text-center">
            <p className="text-lg font-bold tabular-nums text-white">{metrics.provisions_prefiltered}</p>
            <p className="text-[10px] text-gray-500">Pre-filtered</p>
          </div>
        </div>
      )}

      {statusData.error_message && (
        <div className="rounded-lg bg-danger/10 border border-danger/20 px-3 py-2.5">
          <p className="text-xs text-danger-400">{statusData.error_message}</p>
        </div>
      )}
    </div>
  )
}
