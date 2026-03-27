import React, { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { Rule, RuleEvalResult } from '../../types/knowledge';
import { evaluateRule, fetchRules } from '../../services/knowledgeApi';

const USE_CASES = ['eu_sec', 'erisa', 'om'];

interface RuleExplorerProps {
  instrumentUrn?: string;
  instrumentLabel?: string;
}

export function RuleExplorer({ instrumentUrn, instrumentLabel }: RuleExplorerProps) {
  const [rules, setRules] = useState<Rule[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, RuleEvalResult>>({});
  const [evaluating, setEvaluating] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>('eu_sec');

  useEffect(() => {
    fetchRules().then((d) => setRules(d.rules)).catch(() => {});
  }, []);

  const runEval = async (ruleId: string) => {
    if (!instrumentUrn) return;
    setEvaluating(ruleId);
    try {
      const result = await evaluateRule(ruleId, instrumentUrn);
      setResults((prev) => ({ ...prev, [ruleId]: result }));
    } finally {
      setEvaluating(null);
    }
  };

  const filtered = rules.filter((r) => r.use_case === activeTab);

  const verdictColor = (v?: string) =>
    v === 'compliant'
      ? 'text-green-600'
      : v === 'non_compliant'
      ? 'text-red-600'
      : 'text-yellow-600';

  return (
    <div className="flex h-full flex-col">
      {/* Selected instrument indicator */}
      {instrumentUrn ? (
        <div className="flex items-center gap-1.5 px-4 py-2 bg-indigo-50 dark:bg-indigo-900/20 border-b border-indigo-200 dark:border-indigo-700 text-[11px]">
          <span className="text-indigo-400">Evaluating against:</span>
          <span className="font-semibold text-indigo-700 dark:text-indigo-300 truncate" title={instrumentUrn}>
            {instrumentLabel || instrumentUrn}
          </span>
        </div>
      ) : (
        <div className="flex items-center gap-2 px-4 py-2 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700 text-[11px] text-gray-400 italic">
          <span>↑ Switch to Graph view and click an instrument node to enable evaluation</span>
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-gray-200 dark:border-gray-700">
        {USE_CASES.map((uc) => (
          <button
            key={uc}
            onClick={() => setActiveTab(uc)}
            className={[
              'px-4 py-2 text-xs font-medium uppercase tracking-wide border-b-2 transition-colors',
              activeTab === uc
                ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                : 'border-transparent text-gray-500 hover:text-gray-700',
            ].join(' ')}
          >
            {uc}
          </button>
        ))}
      </div>

      {/* Rule list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 && (
          <div className="py-8 text-center text-xs text-gray-400">No rules loaded</div>
        )}
        {filtered.map((rule) => {
          const isOpen = expanded === rule.rule_id;
          const result = results[rule.rule_id];
          return (
            <div key={rule.rule_id} className="border-b border-gray-100 dark:border-gray-800">
              <button
                className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                onClick={() => setExpanded(isOpen ? null : rule.rule_id)}
              >
                {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <span className="flex-1 text-xs font-medium truncate">{rule.name}</span>
                {result && (
                  <span className={`text-[10px] font-semibold ${verdictColor(result.verdict)}`}>
                    {result.verdict.replace('_', ' ')}
                  </span>
                )}
              </button>
              {isOpen && (
                <div className="px-4 pb-3 space-y-2 text-[11px] text-gray-600 dark:text-gray-400">
                  <p>
                    <span className="font-semibold text-gray-700 dark:text-gray-300">Regulation: </span>
                    {rule.regulation}
                  </p>
                  <p>{rule.description}</p>
                  <p className="text-[10px] text-gray-400">
                    v{rule.version} · confidence threshold {rule.confidence_threshold}
                  </p>

                  {instrumentUrn && (
                    <button
                      onClick={() => runEval(rule.rule_id)}
                      disabled={evaluating === rule.rule_id}
                      className="mt-1 rounded-lg bg-indigo-600 px-3 py-1 text-white text-[11px] disabled:opacity-50 hover:bg-indigo-700 transition-colors"
                    >
                      {evaluating === rule.rule_id ? 'Evaluating…' : 'Evaluate against selection'}
                    </button>
                  )}

                  {result && (
                    <div className="mt-2 rounded-lg bg-gray-50 dark:bg-gray-800 p-2 space-y-1">
                      <p>
                        <span className={`font-semibold ${verdictColor(result.verdict)}`}>
                          {result.verdict.replace('_', ' ')}
                        </span>
                        <span className="ml-2 text-gray-400">
                          confidence {Math.round(result.confidence * 100)}%
                        </span>
                        {result.human_review_required && (
                          <span className="ml-2 text-yellow-600">⚠ review required</span>
                        )}
                      </p>
                      <p className="italic">{result.explanation}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
