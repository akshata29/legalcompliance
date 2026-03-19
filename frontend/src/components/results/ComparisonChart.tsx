import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer,
  Tooltip, BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell,
} from 'recharts'
import type { ComparisonMetrics } from '../../types'
import { TrendingDown, Zap, DollarSign } from 'lucide-react'

interface ComparisonChartProps {
  comparison: ComparisonMetrics
}

function fmt(n?: number) {
  if (n === undefined || n === null) return '—'
  if (n >= 60) return `${(n / 60).toFixed(1)}m`
  return `${n.toFixed(1)}s`
}

export default function ComparisonChart({ comparison }: ComparisonChartProps) {
  const { legacy_metrics: leg, optimized_metrics: opt } = comparison

  if (!leg || !opt) {
    return (
      <div className="card text-center py-6 text-sm text-gray-500">
        Run both Legacy and Optimized pipelines to see a side-by-side comparison.
      </div>
    )
  }

  const durationData = [
    { name: 'Legacy',    value: +(leg.total_duration_seconds ?? 0).toFixed(1), fill: '#f59e0b' },
    { name: 'Optimized', value: +(opt.total_duration_seconds ?? 0).toFixed(1), fill: '#10b981' },
  ]

  const callData = [
    { name: 'Legacy',    value: leg.total_llm_calls,  fill: '#f59e0b' },
    { name: 'Optimized', value: opt.total_llm_calls,  fill: '#10b981' },
  ]

  const tokenData = [
    { name: 'Legacy',    value: leg.total_tokens_used,  fill: '#f59e0b' },
    { name: 'Optimized', value: opt.total_tokens_used,  fill: '#10b981' },
  ]

  const BENEFITS = [
    {
      icon: Zap,
      label: 'Speed-up',
      value: comparison.speedup_factor ? `${comparison.speedup_factor}×` : '—',
      sub: `${fmt(leg.total_duration_seconds)} → ${fmt(opt.total_duration_seconds)}`,
      color: 'text-success-400 bg-success/10',
    },
    {
      icon: TrendingDown,
      label: 'Fewer LLM Calls',
      value: comparison.llm_call_reduction_pct ? `${comparison.llm_call_reduction_pct}%` : '—',
      sub: `${leg.total_llm_calls} → ${opt.total_llm_calls} calls`,
      color: 'text-primary-400 bg-primary/10',
    },
    {
      icon: DollarSign,
      label: 'Token Savings',
      value: comparison.token_reduction_pct ? `${comparison.token_reduction_pct}%` : '—',
      sub: `${(leg.total_tokens_used / 1000).toFixed(1)}k → ${(opt.total_tokens_used / 1000).toFixed(1)}k`,
      color: 'text-warning-400 bg-warning/10',
    },
  ]

  return (
    <div className="space-y-4">
      {/* Headline benefits */}
      <div className="grid grid-cols-3 gap-3">
        {BENEFITS.map(({ icon: Icon, label, value, sub, color }) => (
          <div key={label} className="card-sm space-y-1">
            <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${color}`}>
              <Icon size={14} />
            </div>
            <p className="text-xl font-bold text-white tabular-nums">{value}</p>
            <p className="text-[10px] font-semibold text-gray-400">{label}</p>
            <p className="text-[10px] text-gray-500 font-mono">{sub}</p>
          </div>
        ))}
      </div>

      {/* Side-by-side bar charts */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { title: 'Duration (seconds)', data: durationData },
          { title: 'LLM API Calls',      data: callData },
          { title: 'Tokens Consumed',    data: tokenData },
        ].map(({ title, data }) => (
          <div key={title} className="card">
            <p className="text-[10px] text-gray-500 font-semibold mb-2 uppercase tracking-wide">{title}</p>
            <ResponsiveContainer width="100%" height={90}>
              <BarChart data={data} barSize={28}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
                <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 9 }} axisLine={false} tickLine={false} />
                <YAxis tick={false} axisLine={false} tickLine={false} width={0} />
                <Tooltip
                  contentStyle={{ background: '#111827', border: '1px solid #1f2937', borderRadius: '6px', fontSize: 11, color: '#f9fafb' }}
                  cursor={{ fill: '#1f2937' }}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {data.map((d, i) => <Cell key={i} fill={d.fill} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ))}
      </div>

      {/* Pre-filter savings callout */}
      {opt.provisions_prefiltered > 0 && (
        <div className="rounded-xl bg-success/5 border border-success/20 px-4 py-3 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-success/20 text-success-400 flex items-center justify-center shrink-0">
            <TrendingDown size={16} />
          </div>
          <div>
            <p className="text-xs font-semibold text-success-400">
              Keyword Pre-filter saved {opt.provisions_prefiltered} LLM calls
            </p>
            <p className="text-[11px] text-gray-400 mt-0.5">
              {opt.provisions_prefiltered} of {opt.provisions_categorized} provisions were eliminated before any API call was made (Priority 2 optimization).
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
