"use client";

import type { CDCEvent } from "@/lib/api";

interface SQLPanelProps {
  events: CDCEvent[];
}

export default function SQLPanel({ events }: SQLPanelProps) {
  // Show last 15 SQL statements
  const recentSQL = events.slice(0, 15);

  return (
    <div className="glass-card flex flex-col h-full">
      <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-800/50">
        <span className="text-lg">🔧</span>
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          SQL Fired
        </h2>
        <span className="ml-auto text-xs text-gray-500">ClickHouse writes</span>
      </div>

      <div className="flex-1 overflow-y-auto max-h-[420px]">
        {recentSQL.length === 0 ? (
          <div className="p-8 text-center text-gray-500 text-sm">
            <div className="text-3xl mb-3">💤</div>
            No SQL statements yet
          </div>
        ) : (
          <div className="divide-y divide-gray-800/30">
            {recentSQL.map((event, i) => (
              <div
                key={`sql-${event.pk}-${event.apply_ts}-${i}`}
                className={`
                  px-5 py-3 hover:bg-gray-800/30 transition-colors
                  ${i === 0 ? "animate-fade-in-up bg-gray-800/20" : ""}
                `}
              >
                <div className="flex items-center gap-2 mb-1.5">
                  <span
                    className={`
                      text-[10px] font-bold px-1.5 py-0.5 rounded uppercase
                      ${
                        event.op === "INSERT"
                          ? "badge-insert"
                          : event.op === "UPDATE"
                          ? "badge-update"
                          : event.op === "DELETE"
                          ? "badge-delete"
                          : "badge-snapshot"
                      }
                    `}
                  >
                    {event.op}
                  </span>
                  <span className="text-[11px] text-gray-500 tabular-nums">
                    id={event.pk}
                  </span>
                </div>
                <code className="block text-xs font-mono text-gray-400 leading-relaxed break-all whitespace-pre-wrap">
                  {event.sql_fired}
                </code>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
