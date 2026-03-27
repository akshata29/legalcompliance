import React, { useState, useEffect, useCallback } from 'react';
import {
  Cpu, Plus, Pencil, Trash2, X, Save, RefreshCw, ChevronDown, ChevronRight, AlertCircle
} from 'lucide-react';
import Header from '../components/layout/Header';
import {
  listAllRules, createRule, updateRule, deleteRule, reloadRules,
  type RulePayload,
} from '../services/rulesDesignerApi';

const USE_CASES = ['eu_sec', 'erisa', 'om', 'new_issuance'] as const;
type UseCase = typeof USE_CASES[number];

const UC_LABEL: Record<UseCase, string> = {
  eu_sec: 'EU Securitisation',
  erisa: 'ERISA',
  om: 'Offering Memorandum',
  new_issuance: 'New Issuance',
};

const UC_COLOR: Record<UseCase, string> = {
  eu_sec:       'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  erisa:        'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  om:           'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  new_issuance: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
};

const EMPTY_RULE: RulePayload = {
  id: '',
  version: '1.0',
  name: '',
  regulation: '',
  use_case: 'eu_sec',
  condition: '',
  obligation: '',
  evidence_fields: [],
  confidence_threshold: 0.85,
  human_review_trigger: '',
  effective_from: new Date().toISOString().split('T')[0],
  effective_until: null,
  supersedes: null,
  keywords: [],
  description: '',
};

// ── Tag input helper ───────────────────────────────────────────────────────────
function TagInput({
  value, onChange, placeholder,
}: { value: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [input, setInput] = useState('');
  function addTag() {
    const trimmed = input.trim();
    if (trimmed && !value.includes(trimmed)) onChange([...value, trimmed]);
    setInput('');
  }
  return (
    <div className="flex flex-wrap gap-1 rounded-md border border-gray-300 dark:border-gray-600 p-1.5 min-h-[36px]">
      {value.map(tag => (
        <span key={tag} className="flex items-center gap-0.5 rounded bg-indigo-100 dark:bg-indigo-800 text-indigo-700 dark:text-indigo-200 text-[11px] px-2 py-0.5">
          {tag}
          <button type="button" onClick={() => onChange(value.filter(t => t !== tag))}>
            <X size={10} />
          </button>
        </span>
      ))}
      <input
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTag(); } }}
        onBlur={addTag}
        placeholder={placeholder ?? 'Add, press Enter'}
        className="flex-1 min-w-[80px] bg-transparent text-xs outline-none"
      />
    </div>
  );
}

// ── Rule Form ──────────────────────────────────────────────────────────────────
function RuleForm({
  initial, isNew, saving, error, onSave, onCancel,
}: {
  initial: RulePayload;
  isNew: boolean;
  saving: boolean;
  error: string | null;
  onSave: (r: RulePayload) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<RulePayload>(initial);
  const set = (key: keyof RulePayload, val: unknown) =>
    setForm(f => ({ ...f, [key]: val }));

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <div className="flex items-center gap-2 rounded bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 px-3 py-2 text-xs text-red-700 dark:text-red-300">
          <AlertCircle size={13} /> {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        {/* Rule ID */}
        <div className="col-span-2 sm:col-span-1">
          <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">Rule ID *</label>
          <input value={form.id} readOnly={!isNew}
            onChange={e => set('id', e.target.value.toUpperCase().replace(/\s+/g, '_'))}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-xs font-mono disabled:opacity-60"
            placeholder="RISK_RETENTION" />
        </div>
        {/* Version */}
        <div>
          <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">Version</label>
          <input value={form.version} onChange={e => set('version', e.target.value)}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-xs" />
        </div>
        {/* Name */}
        <div className="col-span-2">
          <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">Name *</label>
          <input value={form.name} onChange={e => set('name', e.target.value)}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-xs"
            placeholder="Risk Retention Requirement" />
        </div>
        {/* Regulation */}
        <div>
          <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">Regulation</label>
          <input value={form.regulation} onChange={e => set('regulation', e.target.value)}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-xs"
            placeholder="EU 2017/2402 Art. 6" />
        </div>
        {/* Use case */}
        <div>
          <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">Use Case</label>
          <select value={form.use_case} onChange={e => set('use_case', e.target.value)}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-xs">
            {USE_CASES.map(uc => <option key={uc} value={uc}>{UC_LABEL[uc]}</option>)}
          </select>
        </div>
        {/* Effective from */}
        <div>
          <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">Effective From *</label>
          <input type="date" value={form.effective_from} onChange={e => set('effective_from', e.target.value)}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-xs" />
        </div>
        {/* Effective until */}
        <div>
          <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">Effective Until</label>
          <input type="date" value={form.effective_until ?? ''} onChange={e => set('effective_until', e.target.value || null)}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-xs" />
        </div>
        {/* Confidence threshold */}
        <div>
          <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">
            Confidence Threshold <span className="font-mono">{form.confidence_threshold.toFixed(2)}</span>
          </label>
          <input type="range" min="0" max="1" step="0.05"
            value={form.confidence_threshold}
            onChange={e => set('confidence_threshold', parseFloat(e.target.value))}
            className="w-full accent-indigo-600" />
        </div>
        {/* Human review trigger */}
        <div>
          <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">Human Review Trigger</label>
          <input value={form.human_review_trigger} onChange={e => set('human_review_trigger', e.target.value)}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-xs"
            placeholder="confidence < 0.7" />
        </div>
        {/* Condition */}
        <div className="col-span-2">
          <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">Condition</label>
          <textarea rows={2} value={form.condition} onChange={e => set('condition', e.target.value)}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-xs resize-none"
            placeholder="Plain-English description of the triggering condition" />
        </div>
        {/* Obligation */}
        <div className="col-span-2">
          <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">Obligation</label>
          <textarea rows={2} value={form.obligation} onChange={e => set('obligation', e.target.value)}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-xs resize-none"
            placeholder="What must be done to satisfy this rule" />
        </div>
        {/* Description */}
        <div className="col-span-2">
          <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">Description</label>
          <textarea rows={2} value={form.description} onChange={e => set('description', e.target.value)}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-xs resize-none"
            placeholder="Summary for display in the chat interface" />
        </div>
        {/* Evidence fields */}
        <div className="col-span-2">
          <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">Evidence Fields</label>
          <TagInput value={form.evidence_fields}
            onChange={v => set('evidence_fields', v)}
            placeholder="retention_percentage, maturity_date…" />
        </div>
        {/* Keywords */}
        <div className="col-span-2">
          <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">Keywords</label>
          <TagInput value={form.keywords}
            onChange={v => set('keywords', v)}
            placeholder="retention, originator…" />
        </div>
        {/* Supersedes */}
        <div>
          <label className="block text-[11px] font-medium text-gray-600 dark:text-gray-400 mb-1">Supersedes Rule ID</label>
          <input value={form.supersedes ?? ''} onChange={e => set('supersedes', e.target.value || null)}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 text-xs font-mono"
            placeholder="RISK_RETENTION_OLD" />
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-2 border-t border-gray-100 dark:border-gray-800">
        <button onClick={onCancel}
          className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800">
          <X size={12} /> Cancel
        </button>
        <button
          onClick={() => onSave(form)}
          disabled={saving || !form.id || !form.name}
          className="flex items-center gap-1.5 rounded bg-indigo-600 px-3 py-1.5 text-xs text-white hover:bg-indigo-700 disabled:opacity-50">
          {saving ? <RefreshCw size={12} className="animate-spin" /> : <Save size={12} />}
          {isNew ? 'Create Rule' : 'Save Changes'}
        </button>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function RulesDesigner() {
  const [rules, setRules] = useState<RulePayload[]>([]);
  const [grouped, setGrouped] = useState<Record<string, RulePayload[]>>({});
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<Record<UseCase, boolean>>({
    eu_sec: true, erisa: true, om: true, new_issuance: true,
  });
  const [selected, setSelected] = useState<RulePayload | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listAllRules();
      setRules(res.rules);
      setGrouped(res.grouped);
    } catch { /* handled */ }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleSave(form: RulePayload) {
    setSaving(true);
    setFormError(null);
    try {
      if (isNew) {
        await createRule(form);
      } else {
        await updateRule(form.id, form);
      }
      await load();
      setSelected(null);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Save failed';
      setFormError(msg);
    }
    setSaving(false);
  }

  async function handleDelete(ruleId: string) {
    try {
      await deleteRule(ruleId);
      setDeleteId(null);
      if (selected?.id === ruleId) setSelected(null);
      await load();
    } catch { /* handled */ }
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-gray-50 dark:bg-gray-950">
      {/* Header */}
      <Header title="Rules Designer" subtitle="Create and manage versioned compliance rule definitions" />

      <div className="flex flex-1 overflow-hidden">
        {/* Rule list — left */}
        <aside className="w-[420px] flex-shrink-0 border-r border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-800">
            <div className="flex items-center gap-2">
              <Cpu size={16} className="text-indigo-600" />
              <span className="text-sm font-semibold text-gray-900 dark:text-white">Rules Engine Designer</span>
              <span className="text-[11px] bg-gray-100 dark:bg-gray-800 text-gray-500 rounded-full px-2 py-0.5">{rules.length}</span>
            </div>
            <div className="flex items-center gap-1">
              <button onClick={load} title="Reload from YAML"
                className="p-1 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
                <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
              </button>
              <button
                onClick={() => { setSelected(EMPTY_RULE); setIsNew(true); setFormError(null); }}
                className="flex items-center gap-1 rounded bg-indigo-600 px-2.5 py-1 text-[11px] text-white hover:bg-indigo-700">
                <Plus size={12} /> New Rule
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
            {USE_CASES.map(uc => {
              const ucRules = grouped[uc] ?? [];
              const open = expanded[uc];
              return (
                <div key={uc}>
                  <button
                    onClick={() => setExpanded(p => ({ ...p, [uc]: !p[uc] }))}
                    className="flex items-center gap-1.5 w-full text-left py-1 text-[11px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                    <span className={`rounded-full px-2 py-0.5 ${UC_COLOR[uc]}`}>{UC_LABEL[uc]}</span>
                    <span className="ml-auto text-gray-400">{ucRules.length}</span>
                  </button>

                  {open && (
                    <ul className="mt-1 space-y-0.5 pl-2">
                      {ucRules.length === 0 && (
                        <li className="text-[11px] text-gray-400 italic px-2 py-1">No rules</li>
                      )}
                      {ucRules.map(r => (
                        <li key={r.id}>
                          <div className={[
                            'group flex items-center justify-between rounded-md px-2 py-1.5 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800',
                            selected?.id === r.id ? 'bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-200 dark:border-indigo-700' : '',
                          ].join(' ')}
                            onClick={() => { setSelected(r); setIsNew(false); setFormError(null); }}
                          >
                            <div className="min-w-0">
                              <p className="text-xs font-medium text-gray-800 dark:text-gray-200 truncate">{r.name}</p>
                              <p className="text-[10px] font-mono text-gray-400 truncate">{r.id}</p>
                            </div>
                            <div className="flex items-center gap-1.5 shrink-0 ml-2">
                              <span className="text-[10px] text-gray-400">v{r.version}</span>
                              <span className="text-[10px] bg-gray-100 dark:bg-gray-700 text-gray-500 rounded px-1">
                                {Math.round(r.confidence_threshold * 100)}%
                              </span>
                              {deleteId === r.id ? (
                                <>
                                  <button
                                    onClick={e => { e.stopPropagation(); handleDelete(r.id); }}
                                    className="text-[10px] text-red-600 font-semibold hover:underline">
                                    Confirm
                                  </button>
                                  <button
                                    onClick={e => { e.stopPropagation(); setDeleteId(null); }}
                                    className="text-[10px] text-gray-400 hover:underline">
                                    Cancel
                                  </button>
                                </>
                              ) : (
                                <button
                                  onClick={e => { e.stopPropagation(); setDeleteId(r.id); }}
                                  className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-600">
                                  <Trash2 size={11} />
                                </button>
                              )}
                            </div>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        </aside>

        {/* Form panel — right */}
        <main className="flex-1 overflow-y-auto">
          {selected ? (
            <div className="max-w-2xl mx-auto p-6">
              <div className="flex items-center gap-2 mb-4">
                <Pencil size={15} className="text-indigo-600" />
                <h2 className="text-sm font-semibold text-gray-900 dark:text-white">
                  {isNew ? 'New Rule' : `Edit — ${selected.name}`}
                </h2>
              </div>
              <RuleForm
                initial={selected}
                isNew={isNew}
                saving={saving}
                error={formError}
                onSave={handleSave}
                onCancel={() => setSelected(null)}
              />
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-gray-400 dark:text-gray-600 flex-col gap-3">
              <Cpu size={40} strokeWidth={1} />
              <p className="text-sm">Select a rule to edit, or click <strong>New Rule</strong> to create one</p>
              <p className="text-[11px]">
                Rules are persisted to <code className="font-mono bg-gray-100 dark:bg-gray-800 px-1 rounded">data/rules/*.yaml</code> and hot-reloaded
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
