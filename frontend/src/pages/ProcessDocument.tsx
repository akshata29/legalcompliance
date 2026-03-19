import { useState, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Play, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import Header from '../components/layout/Header'
import PipelineToggle from '../components/processing/PipelineToggle'
import DocumentUploader from '../components/document/DocumentUploader'
import ProcessingStatusCard from '../components/processing/ProcessingStatusCard'
import MetricsPanel from '../components/processing/MetricsPanel'
import FindingsPanel from '../components/results/FindingsPanel'
import ComparisonChart from '../components/results/ComparisonChart'
import {
  startProcessing,
  getProcessingStatus,
  getProcessingResult,
  getComparisonMetrics,
  getSession,
} from '../services/api'
import type {
  ComparisonMetrics,
  DocumentUploadResponse,
  PipelineMode,
  ProcessingSession,
  ProcessingStatusResponse,
} from '../types'

const POLL_INTERVAL = 2000

export default function ProcessDocument() {
  const [searchParams] = useSearchParams()

  const [mode, setMode] = useState<PipelineMode>('legacy')
  const [docId, setDocId] = useState<string | null>(null)
  const [docName, setDocName] = useState<string>('eu_sec_prospectus_sample.txt')
  const [enableIndexing, setEnableIndexing] = useState(false)

  // Per-mode state so toggling restores the previous run's data
  const [sessionIds, setSessionIds] = useState<Partial<Record<PipelineMode, string>>>({})
  const [statuses, setStatuses] = useState<Partial<Record<PipelineMode, ProcessingStatusResponse>>>({})
  const [results, setResults] = useState<Partial<Record<PipelineMode, ProcessingSession>>>({})
  const [comparison, setComparison] = useState<ComparisonMetrics | null>(null)
  const [running, setRunning] = useState(false)

  // Convenience: data for the currently-selected mode
  const sessionId = sessionIds[mode] ?? null
  const statusData = statuses[mode] ?? null
  const result = results[mode] ?? null

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // Track which mode is currently polling so the closure stays correct
  const activeMode = useRef<PipelineMode>(mode)

  // Auto-select synthetic document if query param present
  useEffect(() => {
    if (searchParams.get('doc') === 'synthetic') {
      setDocId('synthetic-001')
    }
  }, [searchParams])

  // Recall a completed session from CosmosDB when navigated from the Sessions page
  useEffect(() => {
    const recallId = searchParams.get('recall')
    const recallDocId = searchParams.get('document_id')
    const recallMode = searchParams.get('mode') as PipelineMode | null
    const recallDocName = searchParams.get('doc_name')
    if (!recallId || !recallMode) return

    if (recallDocName) setDocName(recallDocName)
    if (recallDocId)   setDocId(recallDocId)
    setMode(recallMode)

    ;(async () => {
      try {
        const session = await getSession(recallId, recallDocId ?? undefined)
        // Synthesise a completed status response from the session
        const fakeStatus = {
          session_id: session.session_id,
          status: session.status,
          pipeline_mode: session.pipeline_mode,
          current_phase: undefined,
          progress_pct: 100,
          metrics: session.metrics,
          error_message: session.error_message,
        }
        setSessionIds(prev => ({ ...prev, [recallMode]: recallId }))
        setStatuses(prev  => ({ ...prev, [recallMode]: fakeStatus }))
        setResults(prev   => ({ ...prev, [recallMode]: session }))
        // Also try to load the comparison chart
        if (recallDocId) {
          try {
            const cmp = await getComparisonMetrics(recallDocId)
            setComparison(cmp)
          } catch { /* comparison not available yet */ }
        }
        toast.success(`Recalled ${recallMode} session from CosmosDB`)
      } catch {
        toast.error('Failed to recall session from CosmosDB')
      }
    })()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // run once on mount only

  // Poll for status while running
  useEffect(() => {
    if (!sessionId || !running) return
    const pollingMode = activeMode.current
    pollRef.current = setInterval(async () => {
      try {
        const s = await getProcessingStatus(sessionId)
        setStatuses(prev => ({ ...prev, [pollingMode]: s }))
        if (s.status === 'complete' || s.status === 'failed') {
          clearInterval(pollRef.current!)
          setRunning(false)
          if (s.status === 'complete') {
            const res = await getProcessingResult(sessionId)
            setResults(prev => ({ ...prev, [pollingMode]: res }))
            if (docId) {
              try {
                const cmp = await getComparisonMetrics(docId)
                setComparison(cmp)
              } catch {
                /* comparison not yet available */
              }
            }
            toast.success(`Processing complete — ${res.findings.length} findings`)
          } else {
            toast.error(`Processing failed: ${s.error_message}`)
          }
        }
      } catch (err) {
        console.error('Poll error', err)
      }
    }, POLL_INTERVAL)
    return () => clearInterval(pollRef.current!)
  }, [sessionId, running, docId])

  function handleUploaded(doc: DocumentUploadResponse) {
    setDocId(doc.document_id)
    setDocName(doc.filename)
    setResults({})
    setStatuses({})
    setSessionIds({})
    setComparison(null)
  }

  function handleUseSynthetic() {
    setDocId('synthetic-001')
    setDocName('eu_sec_150page.txt')
    setResults({})
    setStatuses({})
    setSessionIds({})
    setComparison(null)
  }

  async function handleStart() {
    if (!docId) {
      toast.error('Please upload a document or select the synthetic demo.')
      return
    }
    // Clear only this mode's previous run
    setResults(prev => ({ ...prev, [mode]: undefined }))
    setStatuses(prev => ({ ...prev, [mode]: undefined }))
    setSessionIds(prev => ({ ...prev, [mode]: undefined }))
    setRunning(true)
    activeMode.current = mode

    try {
      const resp = await startProcessing(docId, mode, docName, enableIndexing)
      setSessionIds(prev => ({ ...prev, [mode]: resp.session_id }))
      setStatuses(prev => ({ ...prev, [mode]: resp }))
      toast(`Started ${mode} pipeline…`, { icon: mode === 'optimized' ? '⚡' : '🕐' })
    } catch {
      toast.error('Failed to start processing. Is the backend running?')
      setRunning(false)
    }
  }

  function handleReset() {
    clearInterval(pollRef.current!)
    setSessionIds(prev => ({ ...prev, [mode]: undefined }))
    setStatuses(prev => ({ ...prev, [mode]: undefined }))
    setResults(prev => ({ ...prev, [mode]: undefined }))
    setRunning(false)
  }

  function handleModeChange(newMode: PipelineMode) {
    setMode(newMode)
  }

  const canStart = !!docId && !running

  return (
    <div className="flex-1 flex flex-col min-h-screen">
      <Header
        title="Process Document"
        subtitle="Upload an EU Securities document and run it through the compliance processing pipeline."
      />

      <div className="flex-1 p-6 space-y-6">
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          {/* Left column */}
          <div className="xl:col-span-1 space-y-4">
            <DocumentUploader onUploaded={handleUploaded} onUseSynthetic={handleUseSynthetic} />
            <PipelineToggle mode={mode} onChange={handleModeChange} disabled={running} />

            {/* Start / Reset button */}
            <div className="flex gap-2">
              <button
                onClick={handleStart}
                disabled={!canStart}
                className="btn-primary flex-1 justify-center py-3"
              >
                <Play size={15} />
                Run {mode === 'optimized' ? 'Optimized' : 'Legacy'} Pipeline
              </button>
              {(statusData || result) && (
                <button onClick={handleReset} className="btn-secondary px-3" title="Reset">
                  <RefreshCw size={15} />
                </button>
              )}
            </div>

            {/* Indexing option */}
            <label className="flex items-center gap-2.5 cursor-pointer select-none group">
              <input
                type="checkbox"
                checked={enableIndexing}
                onChange={e => setEnableIndexing(e.target.checked)}
                disabled={running}
                className="w-4 h-4 rounded border-border bg-surface-700 text-primary-500 accent-primary-500 cursor-pointer disabled:opacity-50"
              />
              <span className="text-xs text-gray-400 group-hover:text-gray-300 transition-colors">
                Enable AI Search indexing
                <span className="ml-1 text-gray-500">(slow — skip for testing)</span>
              </span>
            </label>
          </div>

          {/* Right column — status + results */}
          <div className="xl:col-span-2 space-y-6">
            {/* Processing status */}
            {statusData && <ProcessingStatusCard statusData={statusData} />}

            {/* Comparison */}
            {comparison && (comparison.legacy_metrics || comparison.optimized_metrics) && (
              <div className="card">
                <p className="text-sm font-semibold text-white mb-4">
                  Pipeline Comparison — Same Document
                </p>
                <ComparisonChart comparison={comparison} />
              </div>
            )}

            {/* Results */}
            {result && (
              <>
                <div className="card">
                  <p className="text-sm font-semibold text-white mb-4">
                    Performance Metrics — {mode === 'optimized' ? '⚡ Optimized' : '🕐 Legacy'} Pipeline
                  </p>
                  <MetricsPanel metrics={result.metrics} mode={result.pipeline_mode} />
                </div>

                <div className="card">
                  <p className="text-sm font-semibold text-white mb-4">
                    Compliance Findings ({result.findings.length})
                  </p>
                  <FindingsPanel
                    findings={result.findings}
                    provisions={result.provisions}
                    clauses={result.clauses}
                  />
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
