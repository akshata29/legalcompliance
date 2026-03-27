import React from 'react';
import type { EntityDetail, Finding, OntologyNode } from '../../types/knowledge';

interface EntityCardProps {
  node: OntologyNode | null;
  detail: EntityDetail[];
  findings: Finding[];
  loading?: boolean;
}

const VERDICT_BADGE: Record<string, string> = {
  compliant: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400',
  non_compliant: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400',
  insufficient_evidence: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400',
};

export function EntityCard({ node, detail, findings, loading }: EntityCardProps) {
  if (!node && !loading) {
    return (
      <div className="flex h-full items-center justify-center text-gray-400 dark:text-gray-600 text-sm">
        Click a graph node to inspect it
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-gray-400 animate-pulse text-sm">
        Loading…
      </div>
    );
  }

  return (
    <div className="space-y-4 overflow-y-auto h-full p-4">
      {/* Header */}
      <div>
        <span className="rounded-full bg-indigo-100 dark:bg-indigo-900/40 px-2 py-0.5 text-xs text-indigo-700 dark:text-indigo-300">
          {node?.type}
        </span>
        <h3 className="mt-1 text-sm font-semibold break-words">{node?.label || node?.id}</h3>
        <p className="text-[11px] text-gray-400 break-all mt-0.5 select-all">{node?.id}</p>
      </div>

      {/* Properties */}
      {detail.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">
            Properties
          </p>
          <dl className="space-y-1">
            {detail.map((d, i) => (
              <div key={i} className="grid grid-cols-2 gap-1 text-[11px]">
                <dt className="text-gray-500 truncate" title={d.predicate}>{d.predicate}</dt>
                <dd className="font-medium break-words" title={d.value}>{d.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {/* Findings */}
      {findings.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">
            Compliance Findings
          </p>
          <ul className="space-y-2">
            {findings.map((f, i) => (
              <li key={i} className="rounded-lg border border-gray-100 dark:border-gray-700 p-2 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold">{f.ruleRef}</span>
                  <span
                    className={[
                      'rounded-full px-2 py-0.5 text-[10px] font-medium',
                      VERDICT_BADGE[f.verdict] ?? 'bg-gray-100 text-gray-600',
                    ].join(' ')}
                  >
                    {(f.verdict ?? 'unknown').replace('_', ' ')}
                  </span>
                </div>
                {f.verbatim && (
                  <p className="text-[10px] italic text-gray-500">"{f.verbatim.slice(0, 100)}…"</p>
                )}
                <p className="text-[10px] text-gray-400">
                  p.{f.page} § {f.section}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
