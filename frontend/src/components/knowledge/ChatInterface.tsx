import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Send, ThumbsDown, ThumbsUp, X, FileText, Trash2, ChevronDown } from 'lucide-react';
import type { ChatMessage, Citation, Persona } from '../../types/knowledge';
import { streamChat, submitFeedback, fetchIngestedDocuments } from '../../services/knowledgeApi';
import { CitationDrawer } from './CitationDrawer';

interface ChatInterfaceProps {
  persona: Persona | null;
  instrumentUrn?: string | null;
  instrumentLabel?: string | null;
  onClearScope?: () => void;
  onSelectDocument?: (docName: string) => void;
}

// ── Doc-type aware sample questions ──────────────────────────────────────────

function detectDocType(label: string | null | undefined): 'erisa' | 'om' | 'issuance' | 'eu_sec' {
  const n = (label ?? '').toLowerCase();
  if (n.includes('erisa')) return 'erisa';
  if (n.startsWith('om_') || n.startsWith('om ') || n.includes('_om_')) return 'om';
  if (n.includes('issuance')) return 'issuance';
  return 'eu_sec';
}

const DOC_QUESTIONS: Record<string, Record<string, string[]>> = {
  erisa: {
    trader:     ['What are the plan contribution limits?', 'What distribution options are available?', 'What is the vesting schedule?', 'What investment options does the plan offer?'],
    compliance: ['Are all fiduciary duties documented per §404?', 'Are there any prohibited transaction findings?', 'Is the fidelity bond amount compliant?', 'What are the high-risk non-compliant findings?'],
    legal:      ["What trustee obligations are defined?", "Summarise the plan's anti-alienation provisions", 'What claims and appeals procedure is specified?', 'Are there any ERISA §406 prohibited transaction findings?'],
    data_mgmt:  ['List all provision URNs extracted', 'How many findings were classified as high risk?', 'What confidence scores were assigned to ERISA findings?', 'Show all rule IDs with non-compliant verdicts'],
    _default:   ['What fiduciary duties are documented?', 'List all compliance findings for this plan', 'Are there any prohibited transactions?', 'What are the vesting and distribution rules?'],
  },
  om: {
    trader:     ['What is the management fee and carried interest?', 'Describe the distribution waterfall', 'What is the target fund size and investment period?', 'What asset classes can the fund invest in?'],
    compliance: ['Is the ERISA 25% plan asset limit addressed?', 'What accredited investor requirements apply?', 'Are conflicts of interest disclosed?', 'What AIFMD compliance findings were identified?'],
    legal:      ['What transfer restriction provisions apply?', 'Summarise the key person clause', 'What reporting obligations are specified?', 'Are conflicts of interest disclosed?'],
    data_mgmt:  ['List all provisions extracted', 'What rules were applied to this offering memorandum?', 'How many findings are non-compliant?', 'List all high-risk findings'],
    _default:   ['What are the fee terms?', 'List all compliance findings', 'What investor restrictions apply?', 'What are the distribution waterfall terms?'],
  },
  issuance: {
    trader:     ['What are the bond coupon and maturity terms?', 'What covenants apply to this issuance?', 'What ISIN was assigned?', 'What stabilisation arrangements are in place?'],
    compliance: ['Has FCA prospectus approval been obtained?', 'What UK MAR insider list obligations apply?', 'Are MiFIR transaction reporting requirements met?', 'What sanctions/AML findings were identified?'],
    legal:      ['What events of default are defined?', 'Summarise the indenture covenant obligations', 'What consent and amendment provisions apply?', 'What prospectus disclosure obligations were identified?'],
    data_mgmt:  ['List all extracted provisions', 'What compliance rules were applied?', 'How many high-risk findings were found?', 'Show all non-compliant findings with rule IDs'],
    _default:   ['Has FCA approval been confirmed?', 'List all compliance findings', 'What covenants and events of default apply?', 'What are the key issuance obligations?'],
  },
  eu_sec: {
    trader:     ['What are the senior tranche coupon and maturity?', 'Describe the tranche waterfall structure', 'What yield and spread are disclosed?', 'Who are the key counterparties?'],
    compliance: ['Does this instrument meet EU 5% retention requirements?', 'List all non-compliant findings', 'Is this STS-eligible under the Securitisation Regulation?', 'What ERISA flags or restrictions apply?'],
    legal:      ['What trustee obligations are defined?', 'Summarise the covenant conditions', 'Are there any disclosed conflicts of interest?', 'What prospectus disclosure obligations apply?'],
    data_mgmt:  ['List all provision URNs extracted', 'What confidence scores were assigned to findings?', 'Show the graph topology for this instrument', 'How many provisions were marked relevant?'],
    _default:   ['List ERISA-restricted instruments', 'Which instruments are STS-eligible?', 'Show all non-compliant findings', 'What rules are in the knowledge graph?'],
  },
};

function getSampleQuestions(persona: Persona | null, label: string | null | undefined): string[] {
  const docType = detectDocType(label);
  const set = DOC_QUESTIONS[docType] ?? DOC_QUESTIONS.eu_sec;
  const base: string[] = persona ? (set[persona] ?? set._default) : set._default;
  if (!label) return base;
  const name = label.replace(/\.txt$/i, '').replace(/_/g, ' ');
  return base.map((q) =>
    q.replace('this instrument', `"${name}"`)
     .replace('this plan', `"${name}"`)
     .replace('this offering memorandum', `"${name}"`)
  );
}

let _msgCounter = 0;
function nextId() {
  return `msg-${++_msgCounter}-${Date.now()}`;
}

export function ChatInterface({ persona, instrumentUrn, instrumentLabel, onClearScope, onSelectDocument }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [openCitation, setOpenCitation] = useState<Citation[] | null>(null);
  const [ingestedDocs, setIngestedDocs] = useState<string[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const stopRef = useRef<(() => void) | null>(null);

  // Load ingested documents once for the picker
  useEffect(() => {
    fetchIngestedDocuments().then(setIngestedDocs).catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = useCallback(() => {
    const q = input.trim();
    if (!q || busy) return;
    setInput('');
    setBusy(true);

    const userMsg: ChatMessage = {
      id: nextId(),
      role: 'user',
      content: q,
      timestamp: new Date().toISOString(),
    };
    const assistantId = nextId();
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      loading: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);

    const history = messages.map((m) => ({ role: m.role, content: m.content }));

    const cancel = streamChat(
      { question: q, persona, session_history: history, instrument_urn: instrumentUrn ?? undefined },
      (token) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: m.content + token, loading: false } : m,
          ),
        );
      },
      (citations) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, citations, loading: false } : m)),
        );
        setBusy(false);
      },
      (err) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `Error: ${err}`, loading: false }
              : m,
          ),
        );
        setBusy(false);
      },
    );
    stopRef.current = cancel;
  }, [input, busy, messages, persona]);

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const sendFeedback = async (msg: ChatMessage, sentiment: 'positive' | 'negative') => {
    await submitFeedback({
      question: messages.find((m) => m.role === 'user')?.content ?? '',
      answer_excerpt: msg.content.slice(0, 200),
      sentiment,
      persona: persona ?? undefined,
    });
  };

  return (
    <div className="flex h-full">
      {/* ── Chat area ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
      {/* ── Scope banner ──────────────────────────────────────────────────── */}
      {instrumentUrn && instrumentLabel && (
        <div className="flex items-center gap-2 px-4 py-2 bg-indigo-600/15 border-b border-indigo-500/30 shrink-0">
          <FileText size={13} className="text-indigo-400 shrink-0" />
          <span className="text-xs text-indigo-300 font-medium flex-1 truncate">
            Scoped to: <span className="text-white font-semibold">{instrumentLabel.replace(/\.txt$/i, '')}</span>
            <span className="text-indigo-400/60 ml-2 font-normal">· answers focus on this instrument</span>
          </span>
          {onClearScope && (
            <button
              onClick={onClearScope}
              title="Ask about all documents"
              className="text-indigo-400 hover:text-white transition-colors shrink-0"
            >
              <X size={13} />
            </button>
          )}
        </div>
      )}

      {/* Message list */}
      <div className="flex-1 overflow-y-auto space-y-3 p-4">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-5 text-gray-400 dark:text-gray-600 p-4">
            <div className="text-center space-y-1">
              <div className="text-4xl">🧠</div>
              {instrumentLabel ? (
                <>
                  <p className="text-sm text-gray-300">
                    Asking about <span className="text-white font-semibold">{instrumentLabel.replace(/\.txt$/i, '')}</span>
                  </p>
                  <p className="text-xs text-gray-500">Switch to Graph view and click any node to change scope</p>
                </>
              ) : (
                <>
                  <p className="text-sm">Ask anything about your financial instruments</p>
                  <p className="text-xs text-gray-500">Select a document below or click a node in Graph view</p>
                  {/* Inline document picker */}
                  {onSelectDocument && ingestedDocs.length > 0 && (
                    <div className="relative mt-2">
                      <button
                        onClick={() => setPickerOpen(v => !v)}
                        className="flex items-center gap-2 rounded-xl border border-indigo-500/40 bg-indigo-600/10 hover:bg-indigo-600/20 px-3 py-2 text-xs text-indigo-300 transition-all"
                      >
                        <FileText size={13} />
                        Select a document to scope chat
                        <ChevronDown size={12} className={pickerOpen ? 'rotate-180 transition-transform' : 'transition-transform'} />
                      </button>
                      {pickerOpen && (
                        <div className="absolute z-20 mt-1 w-64 rounded-xl border border-gray-700 bg-gray-900 shadow-xl overflow-hidden">
                          {ingestedDocs.map(doc => (
                            <button
                              key={doc}
                              onClick={() => { onSelectDocument(doc); setPickerOpen(false); }}
                              className="w-full text-left px-3 py-2 text-xs text-gray-300 hover:bg-indigo-600/20 hover:text-white transition-colors flex items-center gap-2 border-b border-gray-800 last:border-0"
                            >
                              <FileText size={11} className="text-indigo-400 shrink-0" />
                              {doc.replace(/\.txt$/i, '').replace(/_/g, ' ')}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Sample question chips */}
            <div className="w-full max-w-sm space-y-1.5">
              <p className="text-[10px] uppercase tracking-wider text-gray-500 text-center">
                {persona ? `Sample ${persona} questions` : 'Sample questions'}
              </p>
              <div className="flex flex-col gap-1.5">
                {getSampleQuestions(persona, instrumentLabel).map((q) => (
                  <button
                    key={q}
                    onClick={() => { setInput(q); }}
                    className="text-left text-xs rounded-xl border border-gray-700 bg-gray-800/60 hover:bg-indigo-600/20 hover:border-indigo-500/50 px-3 py-2 text-gray-300 hover:text-white transition-all"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={[
                'max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow-sm',
                msg.role === 'user'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700',
              ].join(' ')}
            >
              {msg.loading ? (
                <span className="inline-flex gap-1">
                  <span className="animate-bounce">●</span>
                  <span className="animate-bounce [animation-delay:0.15s]">●</span>
                  <span className="animate-bounce [animation-delay:0.3s]">●</span>
                </span>
              ) : (
                <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
              )}

              {/* Citations button */}
              {msg.role === 'assistant' && msg.citations && msg.citations.length > 0 && (
                <button
                  onClick={() => setOpenCitation(msg.citations!)}
                  className="mt-2 text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
                >
                  📎 {msg.citations.length} citation{msg.citations.length > 1 ? 's' : ''}
                </button>
              )}

              {/* Feedback bar */}
              {msg.role === 'assistant' && !msg.loading && (
                <div className="mt-2 flex gap-2">
                  <button
                    onClick={() => sendFeedback(msg, 'positive')}
                    className="text-gray-400 hover:text-green-500 transition-colors"
                    title="Helpful"
                  >
                    <ThumbsUp size={13} />
                  </button>
                  <button
                    onClick={() => sendFeedback(msg, 'negative')}
                    className="text-gray-400 hover:text-red-500 transition-colors"
                    title="Not helpful"
                  >
                    <ThumbsDown size={13} />
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t border-gray-200 dark:border-gray-700 px-4 py-3">
        {messages.length > 0 && (
          <div className="flex justify-end mb-1.5">
            <button
              onClick={() => { setMessages([]); onClearScope?.(); }}
              title="Clear conversation and scope"
              className="flex items-center gap-1 text-[11px] text-gray-500 hover:text-red-400 transition-colors"
            >
              <Trash2 size={11} />
              Clear conversation
            </button>
          </div>
        )}
        <div className="flex gap-2">
          <textarea
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder={
            instrumentLabel
              ? `Ask about ${instrumentLabel.replace(/\.txt$/i, '')}…`
              : 'Ask about instruments, rules, ERISA status…'
          }
            className="flex-1 resize-none rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <button
            onClick={send}
            disabled={!input.trim() || busy || !instrumentUrn}
            title={!instrumentUrn ? 'Select a document first' : undefined}
            className="flex items-center justify-center rounded-xl bg-indigo-600 px-3 py-2 text-white disabled:opacity-40 hover:bg-indigo-700 transition-colors"
          >
            <Send size={16} />
          </button>
        </div>
      </div>

      {/* Citation drawer */}
      {openCitation && (
        <CitationDrawer citations={openCitation} onClose={() => setOpenCitation(null)} />
      )}
      </div>{/* end chat area */}

      {/* ── Persistent questions panel ──────────────────────────────────── */}
      <aside className="hidden lg:flex flex-col w-52 shrink-0 border-l border-gray-700/50 overflow-y-auto">
        <div className="px-3 py-3 border-b border-gray-700/50 shrink-0">
          <p className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">
            {persona ? `${persona} questions` : 'sample questions'}
          </p>
          {instrumentLabel && (
            <p className="text-[10px] text-gray-600 truncate mt-0.5">
              {instrumentLabel.replace(/\.txt$/i, '').replace(/_/g, ' ')}
            </p>
          )}
        </div>
        <div className="flex flex-col gap-1.5 p-2">
          {getSampleQuestions(persona, instrumentLabel).map((q) => (
            <button
              key={q}
              onClick={() => setInput(q)}
              className="text-left text-[11px] rounded-lg border border-gray-700/60 bg-gray-800/40 hover:bg-indigo-600/20 hover:border-indigo-500/50 px-2.5 py-2 text-gray-400 hover:text-white transition-all leading-snug"
            >
              {q}
            </button>
          ))}
        </div>
      </aside>
    </div>
  );
}
