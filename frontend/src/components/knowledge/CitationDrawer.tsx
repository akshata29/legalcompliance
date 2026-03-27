import React from 'react';
import { X, FileText, BookOpen } from 'lucide-react';
import type { Citation } from '../../types/knowledge';

interface CitationDrawerProps {
  citations: Citation[];
  onClose: () => void;
}

export function CitationDrawer({ citations, onClose }: CitationDrawerProps) {
  return (
    <div className="fixed inset-y-0 right-0 z-50 flex">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 backdrop-blur-sm"
        onClick={onClose}
      />
      {/* Panel */}
      <aside className="relative ml-auto w-96 bg-white dark:bg-gray-900 shadow-2xl flex flex-col">
        <div className="flex items-center justify-between border-b border-gray-200 dark:border-gray-700 px-4 py-3">
          <div className="flex items-center gap-2">
            <BookOpen size={16} className="text-indigo-600" />
            <h2 className="font-semibold text-sm">Source Citations</h2>
            <span className="rounded-full bg-indigo-100 dark:bg-indigo-900 px-2 py-0.5 text-xs text-indigo-700 dark:text-indigo-300">
              {citations.length}
            </span>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto divide-y divide-gray-100 dark:divide-gray-800">
          {citations.map((c, i) => (
            <div key={i} className="p-4 space-y-2">
              <div className="flex items-start gap-2">
                <FileText size={14} className="mt-0.5 flex-shrink-0 text-gray-400" />
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-gray-700 dark:text-gray-300 truncate">
                    {c.document_id}
                  </p>
                  <div className="flex gap-3 mt-0.5">
                    {c.page !== null && (
                      <span className="text-[11px] text-gray-500">Page {c.page}</span>
                    )}
                    {c.section && (
                      <span className="text-[11px] text-gray-500">§ {c.section}</span>
                    )}
                    {c.rule_id && (
                      <span className="rounded bg-indigo-50 dark:bg-indigo-900/40 px-1 text-[11px] text-indigo-600 dark:text-indigo-400">
                        {c.rule_id}
                      </span>
                    )}
                  </div>
                </div>
                <span
                  className={[
                    'ml-auto flex-shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium',
                    c.confidence >= 0.85
                      ? 'bg-green-100 text-green-700'
                      : c.confidence >= 0.65
                      ? 'bg-yellow-100 text-yellow-700'
                      : 'bg-red-100 text-red-700',
                  ].join(' ')}
                >
                  {Math.round(c.confidence * 100)}%
                </span>
              </div>
              {c.verbatim && (
                <blockquote className="rounded-lg bg-gray-50 dark:bg-gray-800 px-3 py-2 text-[11px] italic text-gray-600 dark:text-gray-400 border-l-2 border-indigo-300">
                  "{c.verbatim}"
                </blockquote>
              )}
            </div>
          ))}
        </div>
      </aside>
    </div>
  );
}
