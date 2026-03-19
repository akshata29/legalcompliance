import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell
} from 'recharts'
import type { PipelineMetrics } from '../../types'
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

export default function MetricsPanel({ metrics, mode }: MetricsPanelProps) {
  const isOpt = mode === 'optimized'
  const accent = isOpt ? '#10b981' : '#f59e0b'

  const phaseData = metrics.phases.map((p) => ({
    name: p.phase.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
    seconds: +(p.duration_seconds ?? 0).toFixed(1),
    calls: p.llm_calls,
  }))

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
            <BarChart data={phaseData} barSize={24}>
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
                {phaseData.map((_, i) => (
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
        </div>
      )}
    </div>
  )
}
