import { motion } from 'framer-motion'
import { Zap, Clock, CheckCircle2, Info } from 'lucide-react'
import type { PipelineMode } from '../../types'
import clsx from 'clsx'

interface PipelineToggleProps {
  mode: PipelineMode
  onChange: (mode: PipelineMode) => void
  disabled?: boolean
}

const DETAILS = {
  legacy: {
    label: 'Legacy Pipeline',
    description: 'Original architecture — 1 LLM call per provision, sequential phases, ThreadPoolExecutor concurrency.',
    color: 'warning',
    icon: Clock,
    metrics: [
      { label: 'API Calls', value: 'N × provisions', detail: '~100 calls for 150-page doc' },
      { label: 'Processing', value: 'Sequential phases', detail: 'Phase B waits for all of Phase A' },
      { label: 'Concurrency', value: 'ThreadPool', detail: 'Blocking I/O, prone to 429s' },
      { label: 'Est. Time', value: '~997s (~16 min)', detail: '150-page document baseline' },
    ],
  },
  optimized: {
    label: 'Optimized Pipeline',
    description: 'All 6 priority optimizations: batch prompting, pre-filter, async I/O, caching, pipeline parallelism, bulk writes.',
    color: 'success',
    icon: Zap,
    metrics: [
      { label: 'API Calls', value: 'ceil(N/10) calls', detail: '~10 calls for same document' },
      { label: 'Pre-filter', value: '30–50% eliminated', detail: 'Keyword filter before LLM' },
      { label: 'Concurrency', value: 'AsyncIO + Semaphore', detail: 'No thread overhead, graceful 429 handling' },
      { label: 'Est. Time', value: '~120–160s', detail: '6–8× faster than legacy' },
    ],
  },
}

export default function PipelineToggle({ mode, onChange, disabled }: PipelineToggleProps) {
  const isOptimized = mode === 'optimized'
  const detail = DETAILS[mode]
  const Icon = detail.icon

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-white">Processing Pipeline</p>
          <p className="text-xs text-gray-400 mt-0.5">
            Toggle to compare the original and optimized architectures
          </p>
        </div>

        {/* Toggle Switch */}
        <button
          onClick={() => !disabled && onChange(isOptimized ? 'legacy' : 'optimized')}
          disabled={disabled}
          className={clsx(
            'relative inline-flex items-center w-[220px] h-10 rounded-xl border p-1 transition-all duration-300 focus:outline-none',
            isOptimized
              ? 'bg-success/10 border-success/30'
              : 'bg-warning/10 border-warning/30',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
          aria-label={`Switch to ${isOptimized ? 'Legacy' : 'Optimized'} pipeline`}
        >
          {/* Track labels */}
          <span
            className={clsx(
              'absolute left-3 text-xs font-semibold transition-opacity duration-200',
              !isOptimized ? 'text-warning-400 opacity-100' : 'text-warning-400 opacity-40'
            )}
          >
            Legacy
          </span>
          <span
            className={clsx(
              'absolute right-3 text-xs font-semibold transition-opacity duration-200',
              isOptimized ? 'text-success-400 opacity-100' : 'text-success-400 opacity-40'
            )}
          >
            Optimized
          </span>

          {/* Thumb */}
          <motion.div
            layout
            className={clsx(
              'relative z-10 w-[100px] h-8 rounded-lg flex items-center justify-center gap-1.5 text-xs font-bold shadow-lg',
              isOptimized
                ? 'bg-success-500 text-white'
                : 'bg-warning-500 text-gray-900'
            )}
            animate={{ x: isOptimized ? 112 : 0 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
          >
            <Icon size={13} />
            {isOptimized ? 'ON' : 'OFF'}
          </motion.div>
        </button>
      </div>

      {/* Active mode banner */}
      <motion.div
        key={mode}
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        className={clsx(
          'rounded-xl border p-4',
          isOptimized
            ? 'bg-success/5 border-success/20'
            : 'bg-warning/5 border-warning/20'
        )}
      >
        <div className="flex items-start gap-3">
          <div
            className={clsx(
              'flex items-center justify-center w-9 h-9 rounded-lg shrink-0 mt-0.5',
              isOptimized ? 'bg-success/20 text-success-400' : 'bg-warning/20 text-warning-400'
            )}
          >
            <Icon size={18} />
          </div>
          <div className="flex-1 min-w-0">
            <p className={clsx('text-sm font-semibold', isOptimized ? 'text-success-400' : 'text-warning-400')}>
              {detail.label}
            </p>
            <p className="text-xs text-gray-400 mt-0.5 leading-relaxed">{detail.description}</p>
          </div>
        </div>

        {/* Metrics grid */}
        <div className="grid grid-cols-2 gap-2 mt-3">
          {detail.metrics.map((m) => (
            <div key={m.label} className="bg-surface-800 rounded-lg px-3 py-2">
              <p className="text-[10px] text-gray-500 mb-0.5">{m.label}</p>
              <p
                className={clsx(
                  'text-xs font-semibold font-mono',
                  isOptimized ? 'text-success-400' : 'text-warning-400'
                )}
              >
                {m.value}
              </p>
              <p className="text-[10px] text-gray-500 mt-0.5">{m.detail}</p>
            </div>
          ))}
        </div>
      </motion.div>

      {/* Optimizations active badge */}
      {isOptimized && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex flex-wrap gap-1.5"
        >
          {[
            'P1: Batch Prompting',
            'P2: Keyword Pre-filter',
            'P3: Async I/O',
            'P4: Redis Cache',
            'P5: Pipeline Parallelism',
            'P6: Bulk DB Writes',
          ].map((opt) => (
            <span
              key={opt}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-success/10 text-success-400 text-[10px] font-semibold border border-success/20"
            >
              <CheckCircle2 size={9} />
              {opt}
            </span>
          ))}
        </motion.div>
      )}

      {!isOptimized && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-start gap-2 rounded-lg bg-surface-700 border border-border px-3 py-2.5"
        >
          <Info size={14} className="text-warning-400 shrink-0 mt-0.5" />
          <p className="text-xs text-gray-400">
            The Legacy pipeline replicates the original architecture. Switch to{' '}
            <strong className="text-success-400">Optimized</strong> to activate all 6 performance improvements identified in the architecture analysis.
          </p>
        </motion.div>
      )}
    </div>
  )
}
