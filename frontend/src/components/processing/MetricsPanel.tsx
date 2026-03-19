import { useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell
} from 'recharts'
import type { PipelineMetrics, CapturedLlmCall, PrefilterSample } from '../../types'
import clsx from 'clsx'

interface MetricsPanelProps {
  metrics: PipelineMetrics
  mode: 'legacy' | 'optimized'
}

function fmt(n?: number) {
  if (n === undefined || n === null) return '—'
  if (n >= 3600) return `${(n / 3600).toFixed(1)}h`
  if (n >= 60)   return `${(n / 60).toFixed(1)}m`
  return `${n.toFixed(1)}s`
}

function fmtK(n: number) {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}

// ─── Captured Prompt Viewer ─────────────────────────────────────────────────

function PromptViewer({ samples, accent }: { samples: CapturedLlmCall[]; accent: string }) {
  const [expandedId, setExpandedId] = useState<string | null>(null)

  // Group by phase
  const grouped = samples.reduce<Record<string, CapturedLlmCall[]>>((acc, s) => {
    (acc[s.phase] ??= []).push(s)
    return acc
  }, {})

  const phaseLabel = (p: string) => p.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

  return (
    <div className="card">
      <p className="section-title">Captured LLM Prompts</p>
      <p className="text-[10px] text-gray-500 mb-3">
        Real prompts & responses recorded during pipeline execution (sampled).
      </p>

      {Object.entries(grouped).map(([phase, calls]) => (
        <div key={phase} className="mb-3">
          <p className="text-[11px] font-semibold text-gray-400 mb-1.5 uppercase tracking-wider">
            {phaseLabel(phase)}
          </p>
          <div className="space-y-2">
            {calls.map((call) => {
              const uid = `${call.phase}-${call.call_index}`
              const open = expandedId === uid
              return (
                <div
                  key={uid}
                  className="border border-border rounded-lg overflow-hidden"
                >
                  {/* Header bar */}
                  <button
                    onClick={() => setExpandedId(open ? null : uid)}
                    className="w-full flex items-center justify-between px-3 py-2 bg-surface-700 hover:bg-surface-600 transition-colors text-left"
                  >
                    <span className="text-xs text-gray-300 font-medium">
                      Call #{call.call_index + 1}
                    </span>
                    <span className="flex items-center gap-2 text-[10px] text-gray-500">
                      <span style={{ color: accent }}>{call.latency_ms}ms</span>
                      <span>{call.input_tokens + call.output_tokens} tok</span>
                      <span className="text-gray-600">{open ? '▲' : '▼'}</span>
                    </span>
                  </button>

                  {open && (
                    <div className="p-3 space-y-2 bg-surface-800">
                      {/* System prompt */}
                      <ChatBubble
                        role="System"
                        text={call.system_prompt}
                        color="purple"
                      />
                      {/* User prompt */}
                      <ChatBubble
                        role="User"
                        text={call.user_prompt}
                        color="blue"
                      />
                      {/* Response */}
                      <ChatBubble
                        role="Assistant"
                        text={call.response_text}
                        color="green"
                      />
                      {/* Token stats */}
                      <div className="flex gap-3 text-[10px] text-gray-500 pt-1 border-t border-border mt-1">
                        <span>Input: <span className="text-gray-400">{call.input_tokens}</span> tok</span>
                        <span>Output: <span className="text-gray-400">{call.output_tokens}</span> tok</span>
                        <span>Latency: <span style={{ color: accent }}>{call.latency_ms}ms</span></span>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

function ChatBubble({ role, text, color }: { role: string; text: string; color: 'purple' | 'blue' | 'green' }) {
  const [expanded, setExpanded] = useState(false)
  const colorMap = {
    purple: { bg: 'bg-purple-900/30', border: 'border-purple-800/40', label: 'text-purple-400' },
    blue: { bg: 'bg-blue-900/30', border: 'border-blue-800/40', label: 'text-blue-400' },
    green: { bg: 'bg-emerald-900/30', border: 'border-emerald-800/40', label: 'text-emerald-400' },
  }
  const c = colorMap[color]
  const truncLen = 300
  const needsTrunc = text.length > truncLen

  return (
    <div className={clsx('rounded-md border p-2', c.bg, c.border)}>
      <p className={clsx('text-[10px] font-semibold mb-1', c.label)}>{role}</p>
      <pre className="text-[11px] text-gray-300 whitespace-pre-wrap break-words font-mono leading-relaxed">
        {needsTrunc && !expanded ? text.slice(0, truncLen) + '…' : text}
      </pre>
      {needsTrunc && (
        <button
          onClick={() => setExpanded(!expanded)}
          className={clsx('text-[10px] mt-1 font-medium', c.label)}
        >
          {expanded ? 'Show less' : 'Show full text'}
        </button>
      )}
    </div>
  )
}

// ─── Pre-filter Viewer ──────────────────────────────────────────────────────

function PrefilterViewer({ samples, total, eliminated }: { samples: PrefilterSample[]; total: number; eliminated: number }) {
  const passed = samples.filter((s) => s.passed)
  const blocked = samples.filter((s) => !s.passed)

  const reasonLabel: Record<string, string> = {
    obligation_marker: 'Obligation marker (shall/must/...)',
    keyword_match: 'Keyword match',
    no_match: 'No keywords matched',
  }

  const pct = total > 0 ? ((eliminated / total) * 100).toFixed(0) : '0'

  return (
    <div className="card">
      <p className="section-title">Keyword Pre-Filter</p>
      <p className="text-[10px] text-gray-500 mb-3">
        Eliminated <span className="text-red-400 font-semibold">{eliminated}</span> of{' '}
        <span className="text-gray-300">{total}</span> provisions ({pct}%) before any LLM call.
      </p>

      {blocked.length > 0 && (
        <div className="mb-3">
          <p className="text-[10px] font-semibold text-red-400 mb-1.5 uppercase tracking-wider">
            Eliminated (sample)
          </p>
          <div className="space-y-1.5">
            {blocked.map((s) => (
              <div
                key={s.provision_id}
                className="rounded-md border border-red-900/30 bg-red-900/10 p-2"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] text-gray-500 font-mono">{s.provision_id}</span>
                  <span className="text-[9px] text-red-400/80 font-medium">{reasonLabel[s.reason] ?? s.reason}</span>
                </div>
                <p className="text-[11px] text-gray-400 leading-relaxed line-clamp-2">{s.text}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {passed.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-emerald-400 mb-1.5 uppercase tracking-wider">
            Passed to LLM (sample)
          </p>
          <div className="space-y-1.5">
            {passed.map((s) => (
              <div
                key={s.provision_id}
                className="rounded-md border border-emerald-900/30 bg-emerald-900/10 p-2"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] text-gray-500 font-mono">{s.provision_id}</span>
                  <span className="text-[9px] text-emerald-400/80 font-medium">{reasonLabel[s.reason] ?? s.reason}</span>
                </div>
                <p className="text-[11px] text-gray-400 leading-relaxed line-clamp-2">{s.text}</p>
                {s.matched_terms.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {s.matched_terms.map((t) => (
                      <span key={t} className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-900/30 text-emerald-300/80 font-mono">
                        {t}
                      </span>
                    ))}
                  </div>
                )}
                {s.matched_categories.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {s.matched_categories.map((c) => (
                      <span key={c} className="text-[9px] px-1.5 py-0.5 rounded bg-blue-900/30 text-blue-300/80">
                        {c.replace(/_/g, ' ')}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main Component ─────────────────────────────────────────────────────────

export default function MetricsPanel({ metrics, mode }: MetricsPanelProps) {
  const isOpt = mode === 'optimized'
  const accent = isOpt ? '#10b981' : '#f59e0b'

  const phaseData = metrics.phases.map((p) => ({
    name: p.phase.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
    seconds: +(p.duration_seconds ?? 0).toFixed(1),
    calls: p.llm_calls,
    pipelined: p.pipelined,
  }))

  // Merge consecutive pipelined phases into a single bar for honest chart display.
  // B+C run concurrently in the optimized pipeline — showing them as separate bars
  // would visually imply sequential execution (41s + 41s = 82s) when the real
  // wall-clock is just max(41s, 41s) = 41s.
  const chartData: typeof phaseData = []
  for (let i = 0; i < phaseData.length; i++) {
    const p = phaseData[i]
    if (
      p.pipelined &&
      i + 1 < phaseData.length &&
      phaseData[i + 1].pipelined
    ) {
      const next = phaseData[i + 1]
      chartData.push({
        name: `${p.name} + ${next.name}`,
        seconds: +Math.max(p.seconds, next.seconds).toFixed(1),
        calls: p.calls + next.calls,
        pipelined: true,
      })
      i++ // skip next — already merged
    } else {
      chartData.push(p)
    }
  }

  const KPI = [
    {
      label: 'Total Time',
      value: fmt(metrics.total_duration_seconds),
      highlight: true,
    },
    { label: 'LLM Calls',      value: String(metrics.total_llm_calls) },
    { label: 'Tokens Used',    value: fmtK(metrics.total_tokens_used) },
    { label: 'Provisions',     value: String(metrics.provisions_categorized) },
    { label: 'Pre-filtered',   value: String(metrics.provisions_prefiltered),
      dimmed: !isOpt },
    { label: 'LLM Rejected',   value: String(metrics.provisions_llm_not_relevant ?? 0),
      tooltip: isOpt
        ? 'Passed keyword pre-filter but LLM batch classified as not-relevant'
        : 'Provisions individually reviewed by LLM and classified as not-relevant' },
    { label: 'Relevant',       value: String(metrics.provisions_relevant) },
    { label: 'Clauses',        value: String(metrics.clauses_extracted) },
    { label: 'Findings',       value: String(metrics.findings_generated) },
  ]

  return (
    <div className="space-y-4">
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-2">
        {KPI.map(({ label, value, highlight, tooltip, dimmed }) => (
          <div
            key={label}
            title={tooltip}
            className={clsx(
              'rounded-xl p-3 text-center',
              dimmed ? 'opacity-30' : '',
              highlight
                ? isOpt
                  ? 'bg-success/10 border border-success/20'
                  : 'bg-warning/10 border border-warning/20'
                : 'bg-surface-700 border border-border',
              tooltip ? 'cursor-help' : '',
            )}
          >
            <p
              className={clsx(
                'text-2xl font-bold tabular-nums',
                highlight ? (isOpt ? 'text-success-400' : 'text-warning-400') : 'text-white'
              )}
            >
              {value}
            </p>
            <p className="text-[10px] text-gray-500 mt-0.5 font-medium">{label}</p>
          </div>
        ))}
      </div>

      {/* Phase duration chart */}
      {phaseData.length > 0 && (
        <div className="card">
          <p className="section-title">Phase Duration (seconds)</p>
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={chartData} barSize={24}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
              <XAxis
                dataKey="name"
                tick={{ fill: '#6b7280', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: '#6b7280', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                width={30}
              />
              <Tooltip
                contentStyle={{
                  background: '#111827',
                  border: '1px solid #1f2937',
                  borderRadius: '8px',
                  fontSize: 12,
                  color: '#f9fafb',
                }}
                cursor={{ fill: '#1f2937' }}
              />
              <Bar dataKey="seconds" radius={[4, 4, 0, 0]}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill={accent} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Phase table */}
      {metrics.phases.length > 0 && (
        <div className="card overflow-x-auto">
          <p className="section-title">Phase Breakdown</p>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 text-left border-b border-border">
                <th className="pb-2 font-medium">Phase</th>
                <th className="pb-2 font-medium text-right">Duration</th>
                <th className="pb-2 font-medium text-right">LLM Calls</th>
                <th className="pb-2 font-medium text-right">Tokens</th>
                <th className="pb-2 font-medium text-right">Items</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {metrics.phases.map((p) => (
                <tr key={p.phase} className="text-gray-300">
                  <td className="py-2 capitalize font-medium">
                    {p.phase.replace(/_/g, ' ')}
                    {p.pipelined && (
                      <span className="ml-1.5 text-[9px] text-success-400 font-normal opacity-70">
                        pipelined
                      </span>
                    )}
                  </td>
                  <td className="py-2 text-right tabular-nums font-mono">
                    {fmt(p.duration_seconds)}
                  </td>
                  <td className="py-2 text-right tabular-nums">{p.llm_calls}</td>
                  <td className="py-2 text-right tabular-nums">{fmtK(p.tokens_used)}</td>
                  <td className="py-2 text-right tabular-nums">{p.items_processed}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {metrics.phases.some((p) => p.pipelined) && (
            <p className="text-[9px] text-gray-500 mt-2 italic">
              Pipelined phases run concurrently — wall-clock time is the max, not the sum.
            </p>
          )}
        </div>
      )}

      {/* Keyword Pre-Filter Samples */}
      {metrics.prefilter_samples && metrics.prefilter_samples.length > 0 && (
        <PrefilterViewer
          samples={metrics.prefilter_samples}
          total={metrics.provisions_categorized}
          eliminated={metrics.provisions_prefiltered}
        />
      )}

      {/* Captured LLM Prompts */}
      {metrics.prompt_samples && metrics.prompt_samples.length > 0 && (
        <PromptViewer samples={metrics.prompt_samples} accent={accent} />
      )}
    </div>
  )
}
