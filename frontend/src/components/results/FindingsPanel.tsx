import { useState } from 'react'
import { ChevronDown, ChevronUp, ShieldCheck, ShieldAlert, AlertTriangle, MinusCircle } from 'lucide-react'
import clsx from 'clsx'
import type { ClauseFinding, CategorizedProvision, ExtractedClause, FindingType } from '../../types'

interface FindingsPanelProps {
  findings: ClauseFinding[]
  provisions: CategorizedProvision[]
  clauses: ExtractedClause[]
}

const FINDING_META: Record<
  FindingType,
  { label: string; icon: typeof ShieldCheck; color: string }
> = {
  compliant:        { label: 'Compliant',       icon: ShieldCheck,  color: 'text-success-400 bg-success/10' },
  non_compliant:    { label: 'Non-Compliant',    icon: ShieldAlert,  color: 'text-danger-400 bg-danger/10' },
  needs_review:     { label: 'Needs Review',     icon: AlertTriangle,color: 'text-warning-400 bg-warning/10' },
  not_applicable:   { label: 'Not Applicable',   icon: MinusCircle,  color: 'text-gray-400 bg-gray-700' },
}

const RISK_COLORS: Record<string, string> = {
  low:      'badge-success',
  medium:   'badge-warning',
  high:     'text-orange-400 bg-orange-400/10',
  critical: 'badge-danger',
}

function Summary({ findings }: { findings: ClauseFinding[] }) {
  const counts = findings.reduce(
    (acc, f) => ({ ...acc, [f.finding]: (acc[f.finding] || 0) + 1 }),
    {} as Record<FindingType, number>
  )
  const total = findings.length

  return (
    <div className="grid grid-cols-4 gap-2 mb-4">
      {(Object.keys(FINDING_META) as FindingType[]).map((key) => {
        const { label, icon: Icon, color } = FINDING_META[key]
        const count = counts[key] || 0
        return (
          <div key={key} className={clsx('card-sm flex flex-col items-center gap-1', !count && 'opacity-40')}>
            <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center', color)}>
              <Icon size={15} />
            </div>
            <p className="text-xl font-bold tabular-nums text-white">{count}</p>
            <p className="text-[10px] text-gray-500 text-center">{label}</p>
          </div>
        )
      })}
    </div>
  )
}

function FindingRow({ finding, clause }: { finding: ClauseFinding; clause?: ExtractedClause }) {
  const [open, setOpen] = useState(false)
  const meta = FINDING_META[finding.finding]
  const Icon = meta.icon

  return (
    <div className="border border-border rounded-xl overflow-hidden">
      <button
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-surface-700/50 transition-colors text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <div className={clsx('w-7 h-7 rounded-lg flex items-center justify-center shrink-0', meta.color)}>
          <Icon size={14} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-medium text-white truncate">
              {finding.rule_category.replace(/_/g, ' ')}
            </span>
            <span className={clsx('badge', RISK_COLORS[finding.risk_level] ?? 'badge-warning')}>
              {finding.risk_level}
            </span>
          </div>
          <p className="text-[11px] text-gray-400 mt-0.5 truncate">
            {clause?.clause_text?.substring(0, 90) ?? finding.clause_id}…
          </p>
        </div>
        {open ? <ChevronUp size={15} className="text-gray-500 shrink-0" /> : <ChevronDown size={15} className="text-gray-500 shrink-0" />}
      </button>

      {open && (
        <div className="px-4 pb-4 pt-0 space-y-3 border-t border-border bg-surface-800/30">
          {clause && (
            <div>
              <p className="text-[10px] text-gray-500 font-medium mb-1">CLAUSE TEXT</p>
              <p className="text-xs text-gray-300 leading-relaxed">{clause.clause_text}</p>
              {clause.obligation_type && (
                <span className="mt-1 inline-block badge badge-info">{clause.obligation_type}</span>
              )}
            </div>
          )}
          <div>
            <p className="text-[10px] text-gray-500 font-medium mb-1">JUSTIFICATION</p>
            <p className="text-xs text-gray-300 leading-relaxed">{finding.justification}</p>
          </div>
          {finding.recommendation && (
            <div className="rounded-lg bg-primary/5 border border-primary/10 px-3 py-2">
              <p className="text-[10px] text-primary-400 font-medium mb-1">RECOMMENDATION</p>
              <p className="text-xs text-gray-300 leading-relaxed">{finding.recommendation}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function FindingsPanel({ findings, provisions, clauses }: FindingsPanelProps) {
  const clauseMap = Object.fromEntries(clauses.map((c) => [c.clause_id, c]))

  if (findings.length === 0) {
    return (
      <div className="card text-center py-8 text-gray-500 text-sm">
        No findings generated yet.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <Summary findings={findings} />
      <div className="space-y-2">
        {findings.map((f) => (
          <FindingRow key={f.clause_id} finding={f} clause={clauseMap[f.clause_id]} />
        ))}
      </div>
    </div>
  )
}
