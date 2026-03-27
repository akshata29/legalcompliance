import React, { useEffect, useState } from 'react';
import type { TelemetrySummary } from '../../types/knowledge';
import { fetchTelemetry } from '../../services/knowledgeApi';

function StatTile({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-xl border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 px-4 py-3">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">{label}</p>
      <p className="text-xl font-bold text-gray-900 dark:text-white">{value}</p>
      {sub && <p className="text-[11px] text-gray-400">{sub}</p>}
    </div>
  );
}

export function TelemetryPanel() {
  const [data, setData] = useState<TelemetrySummary | null>(null);

  useEffect(() => {
    fetchTelemetry().then(setData).catch(() => {});
    const t = setInterval(() => fetchTelemetry().then(setData).catch(() => {}), 15_000);
    return () => clearInterval(t);
  }, []);

  if (!data) return null;

  const slaColor = data.sla_breach_rate > 0.05 ? 'text-red-500' : 'text-green-600';

  return (
    <div className="space-y-3 p-4">
      <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
        Live Telemetry
      </p>
      <div className="grid grid-cols-2 gap-2">
        <StatTile label="Total Queries" value={data.total_queries} />
        <StatTile label="Avg Latency" value={`${data.avg_latency_ms}ms`} sub={`p95 ${data.p95_latency_ms}ms`} />
        <StatTile
          label="SLA Breach Rate"
          value={`${(data.sla_breach_rate * 100).toFixed(1)}%`}
          sub={`${data.sla_breach_count} breaches${data.sla_breach_rate > 0.05 ? ' ⚠' : ''}`}
        />
        <StatTile
          label="Top Intent"
          value={
            Object.entries(data.intent_distribution).sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'n/a'
          }
        />
      </div>
      {/* Intent distribution mini-bar */}
      {Object.keys(data.intent_distribution).length > 0 && (
        <div className="space-y-1">
          {Object.entries(data.intent_distribution)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 6)
            .map(([intent, count]) => {
              const max = Math.max(...Object.values(data.intent_distribution));
              const pct = (count / max) * 100;
              return (
                <div key={intent} className="flex items-center gap-2 text-[11px]">
                  <span className="w-28 truncate text-gray-500">{intent}</span>
                  <div className="flex-1 bg-gray-100 dark:bg-gray-800 rounded-full h-1.5">
                    <div
                      className="bg-indigo-500 h-1.5 rounded-full"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="w-6 text-right text-gray-400">{count}</span>
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}
