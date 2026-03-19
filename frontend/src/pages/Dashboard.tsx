import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  FileText, Zap, Clock, AlertTriangle, TrendingDown, Play,
  Activity, CheckCircle2, XCircle, ArrowRight, X, ChevronDown,
} from 'lucide-react'
import Header from '../components/layout/Header'
import { listSessions } from '../services/api'
import clsx from 'clsx'

// ─── Optimization detail data ────────────────────────────────────────────────

interface LlmExample {
  label: string
  system: string
  user: string
  response: string
  stats: { input_tokens: number; output_tokens: number; provisions: number; latency: string }
  legacyComparison: { calls: number; total_tokens: number; total_latency: string }
}

const OPT_DETAILS = [
  {
    priority: 'P1',
    title: 'Prompt-Level Batching → Async Per-Batch',
    desc: '10 provisions per LLM call → ~10× fewer categorization calls',
    impact: '~70% time reduction',
    color: 'success',
    why: 'Legacy fires one synchronous LLM call per provision. The Optimized pipeline packs up to 10 provisions into a single async call, fires all batch calls concurrently via AsyncAzureOpenAI, and caches each per-provision result in Redis so repeat runs skip the LLM entirely.',
    llmExample: {
      label: 'Batch Categorization — 3 Provisions in 1 Call',
      system: `You are a legal compliance analyst. Classify each numbered provision against the EU Securities rule categories below.
Return ONLY JSON: {"results": [{"provision_id": "...", "relevant": bool, "categories": ["RULE_ID", ...], "confidence": float}, ...]}.
Include one entry per provision in the same order.`,
      user: `RULE CATEGORIES:
- RISK_RETENTION: Risk Retention Requirements — Article 6 compliance
- TRANSPARENCY: Transparency Requirements — Article 7 disclosure obligations
- DUE_DILIGENCE: Due Diligence — Article 5 investor verification

PROVISIONS:

[0] ID=PROV_042
The Issuer shall retain a material net economic interest of not less than 5% in the securitisation in accordance with Article 6 of the Securitisation Regulation.

[1] ID=PROV_043
Yield: 5.0%

[2] ID=PROV_044
The Servicer shall provide quarterly investor reports detailing the performance of the underlying assets, including default rates, recovery values, and prepayment speeds.`,
      response: `{
  "results": [
    {
      "provision_id": "PROV_042",
      "relevant": true,
      "categories": ["RISK_RETENTION"],
      "confidence": 0.96
    },
    {
      "provision_id": "PROV_043",
      "relevant": false,
      "categories": [],
      "confidence": 0.99
    },
    {
      "provision_id": "PROV_044",
      "relevant": true,
      "categories": ["TRANSPARENCY"],
      "confidence": 0.93
    }
  ]
}`,
      stats: { input_tokens: 380, output_tokens: 145, provisions: 3, latency: '0.9s' },
      legacyComparison: { calls: 3, total_tokens: 1620, total_latency: '2.7s' },
    } as LlmExample,
    legacy: `# 1 blocking call per provision (ThreadPoolExecutor)
def _call_one(prov):
    result, tokens = self._llm.categorize_single(
        prov.text, rules   # one HTTP round-trip per provision
    )
    return CategorizedProvision(...)

# 31 provisions → 31 API calls
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(_call_one, p) for p in provisions]`,
    optimized: `# 10 provisions packed into ONE async call (batch_size=10)
async def _call_batch(batch: list[dict]) -> None:
    items_text = "\\n\\n".join(
        f"[{i}] ID={p['provision_id']}\\n{p['text']}"
        for i, p in enumerate(batch)
    )
    # Token budget scales with batch size — full text, no truncation
    batch_max_tokens = len(batch) * 120 + 50

    async with self._semaphore:
        response = await self._client.chat.completions.create(
            messages=[system, user], max_tokens=batch_max_tokens
        )  # returns ALL 10 results in one response

# 31 provisions → ceil(31/10) = 4 batch calls concurrently
batches = [candidates[i:i+10] for i in range(0, len(candidates), 10)]
await asyncio.gather(*[_call_batch(b) for b in batches])`,
  },
  {
    priority: 'P2',
    title: 'Keyword Pre-filter',
    desc: 'Eliminates 30–50% of provisions before any LLM call',
    impact: '~40% call reduction',
    color: 'success',
    why: 'Provisions that contain zero compliance keywords (data retention, consent, reporting, etc.) cannot possibly match any rule. Eliminating them before the LLM saves 30–50% of API calls with zero accuracy loss.',
    legacy: `# NO pre-filter — every provision goes to the LLM
for prov in provisions:
    result = llm.categorize_single(prov.text, rules)
    # Even "The Company was founded in 1998" is sent
    # Result: relevant=False after paying for the API call`,
    optimized: `# Regex keyword scan — zero LLM cost for non-matches
from processing.prefilter import batch_prefilter

candidates, eliminated = batch_prefilter(prov_dicts)
# eliminated → marked relevant=False immediately, no LLM call
# candidates → ~50-70% of original set, all proceed to LLM

# prefilter.py: word-boundary regex per rule category
RULE_KEYWORDS = {
  "DATA_RETENTION": ["retain","record","archive","purge",...],
  "CONSENT": ["consent","opt-in","authorisation",...],
  ...
}`,
  },
  {
    priority: 'P3',
    title: 'Async I/O + Semaphore',
    desc: 'AsyncAzureOpenAI with token-bucket rate limiter — no 429 cascades',
    impact: '–30–50s latency',
    color: 'primary',
    why: 'ThreadPoolExecutor uses blocking HTTP under the hood. When 5 threads all hit 429 simultaneously they all retry, creating a thundering-herd. asyncio + semaphore gracefully queues excess calls, never exceeding the rate limit.',
    legacy: `# Sync SDK + ThreadPoolExecutor = blocking I/O
from openai import AzureOpenAI       # synchronous client
client = AzureOpenAI(...)

def categorize_single(text, rules):
    # Blocks the thread until HTTP response arrives
    resp = client.chat.completions.create(...)
    return resp

# 5 threads × blocking HTTP = GIL contention + 429 storms
with ThreadPoolExecutor(max_workers=5) as executor:
    ...`,
    optimized: `# Async SDK + semaphore = fully non-blocking
from openai import AsyncAzureOpenAI  # async client
client = AsyncAzureOpenAI(...)
semaphore = asyncio.Semaphore(5)     # max 5 in-flight

async def call_llm(prompt):
    async with semaphore:            # queue, don't crash
        return await client.chat.completions.create(...)

# Event loop handles all I/O — no threads, no GIL
await asyncio.gather(*[call_llm(p) for p in provisions])`,
  },
  {
    priority: 'P4',
    title: 'Redis Result Cache',
    desc: 'SHA-256 keyed cache with 7-day TTL for repeated provisions',
    impact: 'Dormant — no Redis server',
    color: 'primary',
    why: 'The code exists but Redis is not running locally — all calls go to the LLM. When a Redis server is available, running the same document twice skips the LLM entirely via SHA-256(provision_text + rules_summary) cache keys with 7-day TTL. Graceful fallback: if Redis is unavailable the pipeline works normally, just without caching.',
    legacy: `# No caching — every run pays full LLM cost
def categorize_single(text, rules):
    # Provision seen 10 times? 10 API calls.
    return llm.chat.completions.create(
        messages=[...text, ...rules...]
    )`,
    optimized: `# SHA-256 cache key → Redis with 7-day TTL
def _cache_key(self, prefix, data, suffix=""):
    raw = json.dumps(data, sort_keys=True) + suffix
    return f"lc:{prefix}:{hashlib.sha256(raw.encode()).hexdigest()}"

async def _call_one(p):
    key = self._cache_key("cat1", {"id": p["id"], "text": p["text"][:400]})
    cached = self._cache_get(key)
    if cached:
        return CategorizedProvision(**cached)  # zero API cost

    result = await self._client.chat.completions.create(...)
    self._cache_set(key, result)               # cache for next run
    return CategorizedProvision(**result)`,
  },
  {
    priority: 'P5',
    title: 'Pipeline Parallelism',
    desc: 'Analysis starts on completed clauses while extraction continues',
    impact: 'B+C overlap saves time',
    color: 'primary',
    why: 'Legacy runs Phase B fully before starting Phase C — all extraction must finish before any analysis begins. The Optimized pipeline uses a producer-consumer pattern: each provision\'s clauses are analyzed immediately after extraction, overlapping the two phases.',
    legacy: `# Phase B fully completes before Phase C starts
session, ext_metrics = await self._phase_extract(session, relevant)
# ← ALL provisions extracted; only then:
session, ana_metrics = await self._phase_analyze(session)
# Total time = B_duration + C_duration (sequential)`,
    optimized: `# Producer-consumer: analyze immediately after each extraction
async def _extract_then_analyze(cp: CategorizedProvision):
    clauses = await _extract_one(cp)         # Phase B for this provision
    all_clauses.extend(clauses)
    findings = await asyncio.gather(         # Phase C starts immediately
        *[_analyze_one(c) for c in clauses]
    )
    all_findings.extend(findings)

# All provisions run extract→analyze in parallel
await asyncio.gather(
    *[_extract_then_analyze(cp) for cp in relevant]
)
# Total time ≈ max(B+C per provision), not sum(B) + sum(C)`,
  },
  {
    priority: 'P6',
    title: 'Bulk DB Writes',
    desc: 'All results buffered then written to CosmosDB in one batch',
    impact: '–5–15s DB overhead',
    color: 'primary',
    why: 'Legacy writes to CosmosDB after every single LLM response (N individual upserts). The Optimized pipeline writes only twice: one intermediate status update and one final bulk write with all provisions, clauses, and findings.',
    legacy: `# N individual CosmosDB upserts — one per LLM response
async def _status_cb(sess, pct):
    _sessions[sess.session_id] = sess
    await _persist(sess)   # ← upsert after EVERY phase step
    # For 150 provisions = 150+ upserts during processing`,
    optimized: `# One guaranteed final write with full payload
async def _run_pipeline(session, provisions, rules):
    ...
    try:
        session = await pipeline.run(session, provisions, rules,
            status_callback=_status_cb  # only writes on phase transitions
        )
    finally:
        # Single authoritative write: all provisions + clauses + findings
        await asyncio.to_thread(cosmos.upsert_item_sync, session)
        # P6: intermediate writes are best-effort; final write is guaranteed`,
  },
]

// ─── Optimization detail modal ───────────────────────────────────────────────

function OptDetailModal({ opt, onClose }: { opt: typeof OPT_DETAILS[0]; onClose: () => void }) {
  const [showResponse, setShowResponse] = useState(false)
  const llm = opt.llmExample as LlmExample | undefined

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-4xl max-h-[90vh] flex flex-col rounded-2xl border border-border bg-surface-900 shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 px-6 py-4 border-b border-border shrink-0">
          <div className="flex items-center gap-3">
            <span className={clsx(
              'text-xs font-bold px-2 py-1 rounded-lg',
              opt.color === 'success' ? 'bg-success/20 text-success-400' : 'bg-primary/20 text-primary-400'
            )}>
              {opt.priority}
            </span>
            <div>
              <p className="text-white font-semibold text-sm">{opt.title}</p>
              <p className={clsx('text-xs font-semibold mt-0.5', opt.color === 'success' ? 'text-success-400' : 'text-primary-400')}>
                {opt.impact}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors shrink-0">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {/* Why this optimization */}
          <div className="px-6 py-4 border-b border-border bg-primary/5">
            <p className="text-xs font-semibold text-primary-400 mb-1.5 uppercase tracking-wide">Why this optimization</p>
            <p className="text-sm text-gray-300 leading-relaxed">{opt.why}</p>
          </div>

          {/* Code comparison */}
          <div className="grid grid-cols-2 divide-x divide-border">
            <div className="p-4 space-y-2">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-warning-400 shrink-0" />
                <p className="text-xs font-semibold text-warning-400 uppercase tracking-wide">Legacy Pipeline</p>
              </div>
              <pre className="text-[11px] text-gray-300 leading-relaxed bg-surface-800 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap font-mono border border-border">
                {opt.legacy}
              </pre>
            </div>
            <div className="p-4 space-y-2">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-success-400 shrink-0" />
                <p className="text-xs font-semibold text-success-400 uppercase tracking-wide">Optimized Pipeline</p>
              </div>
              <pre className="text-[11px] text-gray-300 leading-relaxed bg-surface-800 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap font-mono border border-border">
                {opt.optimized}
              </pre>
            </div>
          </div>

          {/* LLM I/O Example — visualize what the actual API call looks like */}
          {llm && (
            <div className="border-t border-border">
              <div className="px-6 py-4 bg-surface-800/50">
                <div className="flex items-center justify-between gap-3 mb-4">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-success-400 animate-pulse" />
                    <p className="text-xs font-semibold text-success-400 uppercase tracking-wide">
                      {llm.label}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-surface-700 text-gray-400 font-mono border border-border">
                      POST /openai/deployments/gpt-4o/chat/completions
                    </span>
                  </div>
                </div>

                {/* Chat messages */}
                <div className="space-y-3">
                  {/* System */}
                  <div className="rounded-lg border border-purple-500/20 bg-purple-500/5 overflow-hidden">
                    <div className="flex items-center gap-2 px-3 py-1.5 bg-purple-500/10 border-b border-purple-500/20">
                      <span className="text-[10px] font-bold text-purple-400 uppercase">System</span>
                    </div>
                    <pre className="text-[10px] text-gray-400 leading-relaxed p-3 whitespace-pre-wrap font-mono">
                      {llm.system}
                    </pre>
                  </div>

                  {/* User */}
                  <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 overflow-hidden">
                    <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-500/10 border-b border-blue-500/20">
                      <span className="text-[10px] font-bold text-blue-400 uppercase">User</span>
                      <span className="text-[9px] text-gray-500">{llm.stats.provisions} provisions in one prompt</span>
                    </div>
                    <pre className="text-[10px] text-gray-400 leading-relaxed p-3 whitespace-pre-wrap font-mono">
                      {llm.user}
                    </pre>
                  </div>

                  {/* Assistant response — expandable */}
                  <div className="rounded-lg border border-success/20 bg-success/5 overflow-hidden">
                    <button
                      onClick={() => setShowResponse(!showResponse)}
                      className="w-full flex items-center justify-between gap-2 px-3 py-1.5 bg-success/10 border-b border-success/20 hover:bg-success/15 transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-bold text-success-400 uppercase">Assistant</span>
                        <span className="text-[9px] text-gray-500">JSON response</span>
                      </div>
                      <ChevronDown size={12} className={clsx(
                        'text-gray-500 transition-transform',
                        showResponse && 'rotate-180'
                      )} />
                    </button>
                    {showResponse && (
                      <pre className="text-[10px] text-success-300 leading-relaxed p-3 whitespace-pre-wrap font-mono">
                        {llm.response}
                      </pre>
                    )}
                  </div>
                </div>

                {/* Stats comparison bar */}
                <div className="mt-4 rounded-lg border border-border bg-surface-900 p-3">
                  <div className="grid grid-cols-2 gap-3">
                    {/* Legacy column */}
                    <div className="space-y-2">
                      <div className="flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-warning-400" />
                        <span className="text-[10px] font-semibold text-warning-400 uppercase">Legacy ({llm.legacyComparison.calls} calls)</span>
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        <div className="text-center">
                          <p className="text-sm font-bold text-warning-400 tabular-nums">{llm.legacyComparison.calls}</p>
                          <p className="text-[9px] text-gray-500">API calls</p>
                        </div>
                        <div className="text-center">
                          <p className="text-sm font-bold text-warning-400 tabular-nums">{(llm.legacyComparison.total_tokens / 1000).toFixed(1)}k</p>
                          <p className="text-[9px] text-gray-500">tokens</p>
                        </div>
                        <div className="text-center">
                          <p className="text-sm font-bold text-warning-400 tabular-nums">{llm.legacyComparison.total_latency}</p>
                          <p className="text-[9px] text-gray-500">latency</p>
                        </div>
                      </div>
                    </div>
                    {/* Optimized column */}
                    <div className="space-y-2">
                      <div className="flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-success-400" />
                        <span className="text-[10px] font-semibold text-success-400 uppercase">Optimized (1 batch call)</span>
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        <div className="text-center">
                          <p className="text-sm font-bold text-success-400 tabular-nums">1</p>
                          <p className="text-[9px] text-gray-500">API call</p>
                        </div>
                        <div className="text-center">
                          <p className="text-sm font-bold text-success-400 tabular-nums">{((llm.stats.input_tokens + llm.stats.output_tokens) / 1000).toFixed(1)}k</p>
                          <p className="text-[9px] text-gray-500">tokens</p>
                        </div>
                        <div className="text-center">
                          <p className="text-sm font-bold text-success-400 tabular-nums">{llm.stats.latency}</p>
                          <p className="text-[9px] text-gray-500">latency</p>
                        </div>
                      </div>
                    </div>
                  </div>
                  {/* Savings row */}
                  <div className="mt-3 pt-2 border-t border-border flex items-center justify-center gap-6">
                    <span className="text-[10px] text-gray-400">
                      <span className="text-success-400 font-bold">{Math.round((1 - 1 / llm.legacyComparison.calls) * 100)}%</span> fewer API calls
                    </span>
                    <span className="text-[10px] text-gray-400">
                      <span className="text-success-400 font-bold">
                        {Math.round((1 - (llm.stats.input_tokens + llm.stats.output_tokens) / llm.legacyComparison.total_tokens) * 100)}%
                      </span> fewer tokens
                    </span>
                    <span className="text-[10px] text-gray-400">
                      System prompt sent <span className="text-success-400 font-bold">once</span> vs {llm.legacyComparison.calls}x
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}


function StatCard({
  label, value, sub, icon: Icon, color,
}: {
  label: string; value: string | number; sub?: string; icon: typeof Activity; color: string
}) {
  return (
    <div className="card flex items-start gap-4">
      <div className={clsx('w-10 h-10 rounded-xl flex items-center justify-center shrink-0', color)}>
        <Icon size={18} />
      </div>
      <div>
        <p className="text-2xl font-bold text-white tabular-nums">{value}</p>
        <p className="text-xs font-medium text-gray-400">{label}</p>
        {sub && <p className="text-[11px] text-gray-500 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [activeOpt, setActiveOpt] = useState<string | null>(null)
  const activeOptData = OPT_DETAILS.find((o) => o.priority === activeOpt) ?? null

  const { data: sessions = [] } = useQuery({
    queryKey: ['sessions'],
    queryFn: () => listSessions(100),
  })

  const complete = sessions.filter((s) => s.status === 'complete')
  const legacyRuns = complete.filter((s) => s.pipeline_mode === 'legacy')
  const optRuns    = complete.filter((s) => s.pipeline_mode === 'optimized')

  const avgLegacy = legacyRuns.length
    ? legacyRuns.reduce((a, s) => a + (s.total_duration_seconds ?? 0), 0) / legacyRuns.length
    : null

  const avgOpt = optRuns.length
    ? optRuns.reduce((a, s) => a + (s.total_duration_seconds ?? 0), 0) / optRuns.length
    : null

  const speedup = avgLegacy && avgOpt ? (avgLegacy / avgOpt).toFixed(1) : null

  function fmt(n: number | null) {
    if (n === null) return '—'
    if (n >= 60) return `${(n / 60).toFixed(1)}m`
    return `${n.toFixed(0)}s`
  }

  const recentSessions = [...sessions]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 5)

  return (
    <div className="flex-1 flex flex-col min-h-screen">
      <Header
        title="Dashboard"
        subtitle="EU Securities Legal Compliance Document Processing"
      />

      <div className="flex-1 p-6 space-y-6">
        {/* Hero quick-start */}
        <div className="rounded-2xl bg-gradient-to-r from-surface-700 via-surface-600 to-primary/10 border border-border p-6 flex items-center justify-between gap-6">
          <div className="space-y-2">
            <h2 className="text-xl font-bold text-white">
              Compare Legacy vs Optimized Pipeline
            </h2>
            <p className="text-sm text-gray-400 max-w-xl">
              Upload an EU Securities document or use the built-in synthetic prospectus.
              Toggle between the original architecture and the optimized pipeline to see
              up to <span className="text-success-400 font-semibold">8× speed improvement</span> and{' '}
              <span className="text-success-400 font-semibold">90% fewer LLM calls</span>.
            </p>
            <button
              onClick={() => navigate('/process?doc=synthetic')}
              className="btn-primary mt-1"
            >
              <Play size={14} />
              Start with Synthetic Document
              <ArrowRight size={14} />
            </button>
          </div>
          <div className="hidden lg:flex flex-col items-center gap-2 shrink-0">
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-xl bg-warning/10 border border-warning/20 px-4 py-3 text-center">
                <p className="text-warning-400 font-bold text-xl">~16m</p>
                <p className="text-gray-500">Legacy</p>
              </div>
              <div className="rounded-xl bg-success/10 border border-success/20 px-4 py-3 text-center">
                <p className="text-success-400 font-bold text-xl">~2m</p>
                <p className="text-gray-500">Optimized</p>
              </div>
            </div>
            <p className="text-[10px] text-gray-500">150-page document estimate</p>
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          <StatCard
            label="Total Sessions"
            value={sessions.length}
            sub={`${complete.length} completed`}
            icon={Activity}
            color="bg-primary/10 text-primary-400"
          />
          <StatCard
            label="Avg Legacy Time"
            value={fmt(avgLegacy)}
            sub={`${legacyRuns.length} runs`}
            icon={Clock}
            color="bg-warning/10 text-warning-400"
          />
          <StatCard
            label="Avg Optimized"
            value={fmt(avgOpt)}
            sub={`${optRuns.length} runs`}
            icon={Zap}
            color="bg-success/10 text-success-400"
          />
          <StatCard
            label="Speed-up Factor"
            value={speedup ? `${speedup}×` : '—'}
            sub="Optimized vs Legacy"
            icon={TrendingDown}
            color="bg-primary/10 text-primary-400"
          />
        </div>

        {/* Optimizations summary */}
        <div className="card">
          <p className="section-title">Architecture Optimizations Active in Optimized Pipeline</p>
          <div className="grid grid-cols-2 xl:grid-cols-3 gap-3">
            {OPT_DETAILS.map(({ priority, title, desc, impact, color }) => (
              <button
                key={priority}
                onClick={() => setActiveOpt(priority)}
                className="rounded-xl bg-surface-700 border border-border p-4 space-y-1.5 text-left hover:border-primary/50 hover:bg-surface-600 transition-all group"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span
                      className={clsx(
                        'text-[10px] font-bold px-1.5 py-0.5 rounded',
                        color === 'success' ? 'bg-success/20 text-success-400' : 'bg-primary/20 text-primary-400'
                      )}
                    >
                      {priority}
                    </span>
                    <p className="text-xs font-semibold text-white">{title}</p>
                  </div>
                  <ChevronDown size={13} className="text-gray-600 group-hover:text-gray-400 transition-colors shrink-0" />
                </div>
                <p className="text-[11px] text-gray-400 leading-relaxed">{desc}</p>
                <p className={clsx('text-[10px] font-semibold', color === 'success' ? 'text-success-400' : 'text-primary-400')}>
                  {impact}
                </p>
              </button>
            ))}
          </div>
        </div>

        {activeOptData && <OptDetailModal opt={activeOptData} onClose={() => setActiveOpt(null)} />}


        {/* Recent sessions */}
        {recentSessions.length > 0 && (
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <p className="section-title mb-0">Recent Sessions</p>
              <button
                onClick={() => navigate('/sessions')}
                className="text-xs text-primary-400 hover:text-primary-300 transition-colors flex items-center gap-1"
              >
                View all <ArrowRight size={12} />
              </button>
            </div>
            <div className="space-y-2">
              {recentSessions.map((s) => (
                <div
                  key={s.session_id}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-surface-700/60 cursor-pointer transition-colors"
                  onClick={() => navigate(`/process?session=${s.session_id}`)}
                >
                  <FileText size={15} className="text-gray-500 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-white truncate">{s.document_name}</p>
                    <p className="text-[11px] text-gray-500">{new Date(s.created_at).toLocaleString()}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {s.pipeline_mode === 'optimized' ? (
                      <span className="badge badge-success"><Zap size={9} />Optimized</span>
                    ) : (
                      <span className="badge badge-warning"><Clock size={9} />Legacy</span>
                    )}
                    {s.status === 'complete' && <CheckCircle2 size={13} className="text-success-400" />}
                    {s.status === 'failed'   && <XCircle size={13} className="text-danger-400" />}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
