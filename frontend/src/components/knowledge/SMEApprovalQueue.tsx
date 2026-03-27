import React, { useEffect, useState } from 'react';
import { CheckCircle, XCircle, AlertTriangle } from 'lucide-react';
import type { OverrideProposal, SMEAmendment } from '../../types/knowledge';
import {
  approveAmendment,
  fetchSmeQueue,
  rejectAmendment,
} from '../../services/knowledgeApi';

export function SMEApprovalQueue() {
  const [proposals, setProposals] = useState<OverrideProposal[]>([]);
  const [amendments, setAmendments] = useState<SMEAmendment[]>([]);
  const [smeName, setSmeName] = useState('');
  const [busy, setBusy] = useState<string | null>(null);

  const load = async () => {
    try {
      const data = await fetchSmeQueue();
      setProposals(data.proposals);
      setAmendments(data.amendments);
    } catch {
      // non-critical
    }
  };

  useEffect(() => {
    load();
  }, []);

  const approve = async (amendmentId: string) => {
    if (!smeName.trim()) return alert('Enter your name first');
    setBusy(amendmentId);
    try {
      await approveAmendment(amendmentId, smeName, '');
      await load();
    } finally {
      setBusy(null);
    }
  };

  const reject = async (amendmentId: string) => {
    if (!smeName.trim()) return alert('Enter your name first');
    const reason = prompt('Rejection reason?') ?? '';
    setBusy(amendmentId);
    try {
      await rejectAmendment(amendmentId, smeName, reason);
      await load();
    } finally {
      setBusy(null);
    }
  };

  const verdictColor = (v: string) =>
    v === 'compliant' ? 'text-green-600' : v === 'non_compliant' ? 'text-red-600' : 'text-yellow-600';

  return (
    <div className="flex h-full flex-col space-y-4 p-4 overflow-y-auto">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">
          SME Identity
        </p>
        <input
          value={smeName}
          onChange={(e) => setSmeName(e.target.value)}
          placeholder="Your name (required to approve/reject)"
          className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>

      {/* Amendments awaiting approval */}
      {amendments.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">
            Pending Amendments ({amendments.length})
          </p>
          <div className="space-y-2">
            {amendments.map((a) => (
              <div
                key={a.amendment_id}
                className="rounded-xl border border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-900/20 p-3 space-y-2"
              >
                <div className="flex items-center gap-2">
                  <AlertTriangle size={13} className="text-yellow-600" />
                  <span className="text-xs font-semibold">{a.rule_id}</span>
                  <span className="ml-auto text-[10px] text-gray-500">
                    v{a.current_version} → v{a.proposed_version}
                  </span>
                </div>
                <div className="text-[11px] text-gray-600 dark:text-gray-400">
                  {Object.entries(a.changes).map(([field, change]) => (
                    <p key={field}>
                      <span className="font-medium">{field}:</span>{' '}
                      <span className="line-through text-red-500">{String(change.old)}</span>
                      {' → '}
                      <span className="text-green-600">{String(change.new)}</span>
                    </p>
                  ))}
                </div>
                <div className="flex items-center gap-2">
                  {a.bdd_passed ? (
                    <span className="text-[10px] text-green-600">✓ BDD passed</span>
                  ) : (
                    <span className="text-[10px] text-red-500">✗ BDD pending</span>
                  )}
                  <div className="ml-auto flex gap-1">
                    <button
                      onClick={() => approve(a.amendment_id)}
                      disabled={!!busy || !a.bdd_passed}
                      className="flex items-center gap-1 rounded-lg bg-green-600 px-2 py-1 text-[11px] text-white disabled:opacity-50 hover:bg-green-700"
                    >
                      <CheckCircle size={11} /> Approve
                    </button>
                    <button
                      onClick={() => reject(a.amendment_id)}
                      disabled={!!busy}
                      className="flex items-center gap-1 rounded-lg bg-red-600 px-2 py-1 text-[11px] text-white disabled:opacity-50 hover:bg-red-700"
                    >
                      <XCircle size={11} /> Reject
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Override proposals */}
      {proposals.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">
            Override Proposals ({proposals.length})
          </p>
          <div className="space-y-2">
            {proposals.map((p) => (
              <div
                key={p.proposal_id}
                className="rounded-xl border border-gray-200 dark:border-gray-700 p-3 space-y-1"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold">{p.rule_id}</span>
                  <span className={`text-[10px] font-semibold ${verdictColor(p.proposed_verdict)}`}>
                    {p.proposed_verdict.replace('_', ' ')}
                  </span>
                </div>
                <p className="text-[11px] text-gray-500 truncate">{p.evidence_summary}</p>
                <p className="text-[10px] text-gray-400">
                  {p.source} · {p.created_at.slice(0, 10)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {proposals.length === 0 && amendments.length === 0 && (
        <div className="flex flex-1 items-center justify-center text-[11px] text-gray-400">
          No pending items
        </div>
      )}

      <button
        onClick={load}
        className="self-end text-[10px] text-gray-400 hover:text-gray-600 transition-colors"
      >
        ↺ Refresh queue
      </button>
    </div>
  );
}
