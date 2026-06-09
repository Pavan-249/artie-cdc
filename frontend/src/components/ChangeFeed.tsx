"use client";

import type { CDCEvent } from "@/lib/api";

interface ChangeFeedProps {
  events: CDCEvent[];
}

function opBadgeClass(op: string): string {
  switch (op) {
    case "INSERT":
      return "badge-insert";
    case "UPDATE":
      return "badge-update";
    case "DELETE":
      return "badge-delete";
    default:
      return "badge-snapshot";
  }
}

function timeAgo(isoString: string): string {
  try {
    const diff = Date.now() - new Date(isoString).getTime();
    if (diff < 1000) return "just now";
    if (diff < 60_000) return `${Math.floor(diff / 1000)}s ago`;
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
    return `${Math.floor(diff / 3_600_000)}h ago`;
  } catch {
    return "—";
  }
}

export default function ChangeFeed({ events }: ChangeFeedProps) {
  return (
    <div className="glass-card flex flex-col h-full">
      <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-800/50">
        <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          Live Change Feed
        </h2>
        <span className="ml-auto text-xs text-gray-500">
          {events.length} events
        </span>
      </div>

      <div className="flex-1 overflow-y-auto max-h-[420px] divide-y divide-gray-800/30">
        {events.length === 0 ? (
          <div className="p-8 text-center text-gray-500 text-sm">
            <div className="text-3xl mb-3">📭</div>
            Waiting for CDC events…
          </div>
        ) : (
          events.map((event, i) => (
            <div
              key={`${event.pk}-${event.apply_ts}-${i}`}
              className={`
                px-5 py-3 hover:bg-gray-800/30 transition-colors
                ${i === 0 ? "animate-fade-in-up bg-gray-800/20" : ""}
              `}
            >
              <div className="flex items-center gap-3 mb-1">
                <span
                  className={`
                    text-[11px] font-bold px-2 py-0.5 rounded-md uppercase
                    ${opBadgeClass(event.op)}
                  `}
                >
                  {event.op}
                </span>
                <span className="text-xs text-gray-400 font-mono">
                  {event.table}.id={event.pk}
                </span>
                <span className="ml-auto text-[11px] text-gray-500 tabular-nums">
                  {event.lag_ms.toFixed(1)} ms
                </span>
              </div>
              <div className="flex items-center gap-2 text-[11px] text-gray-500">
                <span>{timeAgo(event.apply_ts)}</span>
                {event.diff && Object.keys(event.diff).length > 0 && (
                  <span className="text-blue-400/70">
                    Δ {Object.keys(event.diff).join(", ")}
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
