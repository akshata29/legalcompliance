import React, { useEffect, useState } from 'react';
import { Clock, CheckCircle, XCircle, Loader } from 'lucide-react';
import type { BatchJob } from '../../types/knowledge';
import { getBatchJobStatus, listBatchJobs, submitBatchJob } from '../../services/knowledgeApi';

const STATUS_ICON = {
  queued: <Clock size={13} className="text-gray-400" />,
  running: <Loader size={13} className="text-blue-500 animate-spin" />,
  done: <CheckCircle size={13} className="text-green-500" />,
  failed: <XCircle size={13} className="text-red-500" />,
};

export function BatchMonitor() {
  const [jobs, setJobs] = useState<BatchJob[]>([]);
  const [docId, setDocId] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const refresh = async () => {
    try {
      const data = await listBatchJobs();
      setJobs(data);
    } catch {
      // non-critical
    }
  };

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, []);

  const submit = async () => {
    if (!docId.trim()) return;
    setSubmitting(true);
    try {
      await submitBatchJob(docId.trim());
      setDocId('');
      await refresh();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex h-full flex-col space-y-3 p-4">
      <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
        Batch Enrichment
      </p>

      {/* Submit form */}
      <div className="flex gap-2">
        <input
          value={docId}
          onChange={(e) => setDocId(e.target.value)}
          placeholder="Document ID or URL"
          className="flex-1 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
        <button
          onClick={submit}
          disabled={!docId.trim() || submitting}
          className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs text-white disabled:opacity-50 hover:bg-indigo-700 transition-colors"
        >
          {submitting ? '…' : 'Enqueue'}
        </button>
      </div>

      {/* Job list */}
      <div className="flex-1 overflow-y-auto space-y-1">
        {jobs.length === 0 && (
          <p className="text-center text-[11px] text-gray-400 py-4">No batch jobs</p>
        )}
        {jobs.map((job) => (
          <div
            key={job.job_id}
            className="flex items-center gap-2 rounded-lg border border-gray-100 dark:border-gray-800 px-3 py-2"
          >
            {STATUS_ICON[job.status]}
            <div className="flex-1 min-w-0">
              <p className="text-[11px] font-medium truncate">{job.document_id}</p>
              <p className="text-[10px] text-gray-400">{job.submitted_by}</p>
            </div>
            <div className="text-right flex-shrink-0">
              {job.status === 'running' && (
                <div className="w-16 bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                  <div
                    className="bg-indigo-500 h-1.5 rounded-full transition-all"
                    style={{ width: `${job.progress}%` }}
                  />
                </div>
              )}
              {job.status === 'done' && job.result_summary && (
                <span className="text-[10px] text-green-600">
                  +{job.result_summary.triples_added} triples
                </span>
              )}
              {job.status === 'failed' && (
                <span className="text-[10px] text-red-500 truncate max-w-[80px]" title={job.error}>
                  {job.error?.slice(0, 30)}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      <button
        onClick={refresh}
        className="self-end text-[10px] text-gray-400 hover:text-gray-600 transition-colors"
      >
        ↺ Refresh
      </button>
    </div>
  );
}
