import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Upload, RefreshCw, CheckCircle, XCircle, Loader2, GitBranch } from 'lucide-react';
import type { DocumentInfo } from '../../types';
import type { BatchJob } from '../../types/knowledge';
import { listDocuments, uploadDocument } from '../../services/api';
import { submitBatchJob, getBatchJobStatus, fetchIngestedDocuments } from '../../services/knowledgeApi';

interface JobState {
  status: BatchJob['status'];
  progress: number;
  docName: string;
  jobId: string;
}

interface Props {
  onGraphUpdated?: () => void;
  onViewInGraph?: (docName: string) => void;
}

/** One row per unique filename — newest upload (latest uploaded_at) wins. */
function deduplicateByFilename(docs: DocumentInfo[]): DocumentInfo[] {
  const map = new Map<string, DocumentInfo>();
  for (const doc of docs) {
    const existing = map.get(doc.filename);
    if (!existing || doc.uploaded_at > existing.uploaded_at) {
      map.set(doc.filename, doc);
    }
  }
  return Array.from(map.values()).sort((a, b) => a.filename.localeCompare(b.filename));
}

const STATUS_ICON: Record<string, React.ReactNode> = {
  queued:  <Loader2 size={13} className="animate-spin text-yellow-500" />,
  running: <Loader2 size={13} className="animate-spin text-indigo-500" />,
  done:    <CheckCircle size={13} className="text-green-500" />,
  failed:  <XCircle size={13} className="text-red-500" />,
};

export function DocumentIngest({ onGraphUpdated, onViewInGraph }: Props) {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [ingestedNames, setIngestedNames] = useState<Set<string>>(new Set());
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [jobs, setJobs] = useState<Record<string, JobState>>({});
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadAll = useCallback(async () => {
    setLoadingDocs(true);
    try {
      const [rawDocs, names] = await Promise.all([
        listDocuments(),
        fetchIngestedDocuments(),
      ]);
      setDocs(deduplicateByFilename(rawDocs));
      setIngestedNames(new Set(names.map(n => n.toLowerCase())));
    } catch { /* non-fatal */ }
    setLoadingDocs(false);
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  // Poll running/queued jobs every 2.5 s
  useEffect(() => {
    const activeJobs = Object.values(jobs).filter(
      j => j.status === 'queued' || j.status === 'running',
    );
    if (activeJobs.length === 0) {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }
    pollRef.current = setInterval(async () => {
      const updates: Record<string, JobState> = {};
      for (const j of activeJobs) {
        try {
          const fresh = await getBatchJobStatus(j.jobId);
          updates[j.jobId] = { ...j, status: fresh.status, progress: fresh.progress };
          if (fresh.status === 'done') {
            onGraphUpdated?.();
            // Refresh ingested list immediately so badge updates
            fetchIngestedDocuments().then(names =>
              setIngestedNames(new Set(names.map(n => n.toLowerCase())))
            );
          }
        } catch { /* keep old state */ }
      }
      setJobs(prev => ({ ...prev, ...updates }));
    }, 2500);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [jobs, onGraphUpdated]);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setUploading(true);
    for (const file of Array.from(files)) {
      try {
        const uploaded = await uploadDocument(file);
        await loadAll();
        await startIngest(uploaded.document_id, file.name);
      } catch (e) {
        console.error('Upload failed', e);
      }
    }
    setUploading(false);
  }

  async function startIngest(docId: string, docName: string) {
    try {
      const job = await submitBatchJob(docId, 'HIGH');
      setJobs(prev => ({
        ...prev,
        [job.job_id]: { status: job.status as BatchJob['status'], progress: 0, docName, jobId: job.job_id },
      }));
    } catch (e) {
      console.error('Batch submit failed', e);
    }
  }

  const activeCount = Object.values(jobs).filter(
    j => j.status === 'queued' || j.status === 'running',
  ).length;

  const enrichedCount = docs.filter(d => ingestedNames.has(d.filename.toLowerCase())).length;

  return (
    <div className="space-y-3">
      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files); }}
        onClick={() => fileRef.current?.click()}
        className={[
          'flex flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed cursor-pointer py-4 transition-colors',
          dragging
            ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20'
            : 'border-gray-200 dark:border-gray-700 hover:border-indigo-400',
        ].join(' ')}
      >
        <input ref={fileRef} type="file" accept=".pdf,.txt,.docx,.md" multiple className="hidden"
          onChange={e => handleFiles(e.target.files)} />
        {uploading
          ? <Loader2 size={20} className="animate-spin text-indigo-500" />
          : <Upload size={20} className="text-gray-400" />}
        <span className="text-[11px] text-gray-500">
          {uploading ? 'Uploading…' : 'Drop PDF/TXT or click to upload'}
        </span>
      </div>

      {/* Header with counts */}
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">
          Uploaded Documents
          {docs.length > 0 && (
            <span className="ml-1.5 normal-case font-normal">
              ({enrichedCount}/{docs.length} in graph)
            </span>
          )}
        </span>
        <button onClick={loadAll} title="Refresh list" className="text-gray-400 hover:text-gray-600">
          <RefreshCw size={11} className={loadingDocs ? 'animate-spin' : ''} />
        </button>
      </div>

      {docs.length === 0 && !loadingDocs && (
        <p className="text-[11px] text-gray-400 italic">No documents uploaded yet</p>
      )}

      <ul className="space-y-1">
        {docs.map(doc => {
          const isIngested = ingestedNames.has(doc.filename.toLowerCase());
          const jobForDoc = Object.values(jobs).find(j => j.docName === doc.filename);
          const isActive = jobForDoc && (jobForDoc.status === 'queued' || jobForDoc.status === 'running');

          return (
            <li key={doc.document_id}
              className={[
                'flex items-center justify-between rounded border px-2 py-1.5 text-[11px]',
                isIngested
                  ? 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/10'
                  : 'border-gray-100 dark:border-gray-800',
              ].join(' ')}>
              <span className="truncate text-gray-700 dark:text-gray-300 max-w-[200px]" title={doc.filename}>
                {doc.filename}
              </span>

              <div className="flex items-center gap-1.5 shrink-0 ml-2">
                {jobForDoc ? (
                  <div className="flex items-center gap-1">
                    {STATUS_ICON[jobForDoc.status]}
                    {isActive && (
                      <span className="text-gray-400">{jobForDoc.progress}%</span>
                    )}
                  </div>
                ) : isIngested ? (
                  <>
                    <button
                      onClick={() => onViewInGraph?.(doc.filename)}
                      className="flex items-center gap-0.5 text-green-600 dark:text-green-400 hover:text-indigo-500"
                      title="Show this document's nodes in the graph"
                    >
                      <CheckCircle size={12} />
                      <span>View graph</span>
                    </button>
                    <button
                      onClick={() => startIngest(doc.document_id, doc.filename)}
                      className="text-gray-300 hover:text-indigo-500 ml-1"
                      title="Re-enrich (refresh graph data)"
                    >
                      <RefreshCw size={10} />
                    </button>
                  </>
                ) : (
                  <button
                    onClick={() => startIngest(doc.document_id, doc.filename)}
                    className="flex items-center gap-1 text-indigo-600 hover:text-indigo-800"
                    title="Enrich into Knowledge Graph"
                  >
                    <GitBranch size={11} />
                    <span>Enrich</span>
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      {activeCount > 0 && (
        <div className="rounded bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-700 px-3 py-2 text-[11px] text-indigo-700 dark:text-indigo-300">
          <Loader2 size={11} className="inline animate-spin mr-1" />
          {activeCount} enrichment job{activeCount > 1 ? 's' : ''} running — graph will refresh on completion
        </div>
      )}
    </div>
  );
}
