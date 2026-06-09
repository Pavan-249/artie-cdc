"use client";

import type { MetricsResponse } from "@/lib/api";

interface KPICardsProps {
  metrics: MetricsResponse | null;
}

export default function KPICards({ metrics }: KPICardsProps) {
  const cards = [
    {
      label: "Events Replicated",
      value: metrics?.events_replicated ?? "—",
      icon: "📨",
      accent: "text-indigo-400",
      bg: "from-indigo-500/10 to-indigo-600/5",
      border: "border-indigo-500/20",
    },
    {
      label: "Rows Synced",
      value: metrics
        ? `${metrics.rows_synced} / ${metrics.pg_rows}`
        : "—",
      icon: "🔄",
      accent: "text-emerald-400",
      bg: "from-emerald-500/10 to-emerald-600/5",
      border: "border-emerald-500/20",
      sub: metrics?.in_sync ? "In Sync ✓" : "Out of Sync",
      subColor: metrics?.in_sync ? "text-emerald-500" : "text-amber-400",
    },
    {
      label: "P95 Latency",
      value: metrics
        ? `${metrics.p95_latency_ms.toFixed(1)} ms`
        : "—",
      icon: "⚡",
      accent: "text-amber-400",
      bg: "from-amber-500/10 to-amber-600/5",
      border: "border-amber-500/20",
      sub: metrics
        ? `avg ${metrics.avg_latency_ms.toFixed(1)} ms`
        : undefined,
      subColor: "text-gray-500",
    },
    {
      label: "Pipeline Status",
      value: metrics?.pipeline_status === "running" ? "UP" : metrics?.pipeline_status?.toUpperCase() ?? "—",
      icon: metrics?.pipeline_status === "running" ? "🟢" : "🔴",
      accent:
        metrics?.pipeline_status === "running"
          ? "text-emerald-400"
          : "text-red-400",
      bg:
        metrics?.pipeline_status === "running"
          ? "from-emerald-500/10 to-emerald-600/5"
          : "from-red-500/10 to-red-600/5",
      border:
        metrics?.pipeline_status === "running"
          ? "border-emerald-500/20"
          : "border-red-500/20",
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card) => (
        <div
          key={card.label}
          id={`kpi-${card.label.toLowerCase().replace(/\s+/g, "-")}`}
          className={`
            glass-card glass-card-hover p-5
            bg-gradient-to-br ${card.bg} ${card.border}
          `}
        >
          <div className="flex items-start justify-between mb-3">
            <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">
              {card.label}
            </span>
            <span className="text-lg">{card.icon}</span>
          </div>
          <div className={`text-2xl font-bold ${card.accent} tracking-tight`}>
            {card.value}
          </div>
          {card.sub && (
            <div className={`text-xs mt-1.5 ${card.subColor}`}>{card.sub}</div>
          )}
        </div>
      ))}
    </div>
  );
}
