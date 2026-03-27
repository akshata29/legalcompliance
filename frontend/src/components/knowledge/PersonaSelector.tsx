import React from 'react';
import type { Persona } from '../../types/knowledge';

const PERSONAS: { id: Persona; label: string; icon: string; title: string }[] = [
  { id: 'trader',     label: 'Trader',      icon: '📈', title: 'Economic terms, yield, tranche structure' },
  { id: 'compliance', label: 'Compliance',  icon: '⚖️', title: 'Retention %, STS criteria, ERISA flags' },
  { id: 'legal',      label: 'Legal',       icon: '📜', title: 'Entity relationships, covenants, prospectus' },
  { id: 'data_mgmt',  label: 'Data Mgmt',   icon: '🗄️', title: 'URNs, graph topology, confidence scores' },
];

interface PersonaSelectorProps {
  selected: Persona | null;
  onChange: (persona: Persona | null) => void;
}

export function PersonaSelector({ selected, onChange }: PersonaSelectorProps) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mr-1">Persona</span>
      {PERSONAS.map((p) => {
        const active = selected === p.id;
        return (
          <button
            key={p.id}
            title={p.title}
            onClick={() => onChange(active ? null : p.id)}
            className={[
              'flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-all',
              active
                ? 'border-indigo-500 bg-indigo-600 text-white shadow-sm'
                : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:border-indigo-400 hover:text-indigo-600',
            ].join(' ')}
          >
            <span>{p.icon}</span>
            <span>{p.label}</span>
          </button>
        );
      })}
    </div>
  );
}
