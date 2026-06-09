"use client";

import type { Order } from "@/lib/api";

interface DataTableProps {
  title: string;
  icon: string;
  rows: Order[];
  highlightId?: number | null;
  columns: { key: keyof Order; label: string }[];
  accentColor?: string;
}

export default function DataTable({
  title,
  icon,
  rows,
  highlightId,
  columns,
  accentColor = "indigo",
}: DataTableProps) {
  const accentMap: Record<string, string> = {
    indigo: "border-indigo-500/20",
    blue: "border-blue-500/20",
    emerald: "border-emerald-500/20",
  };

  return (
    <div className={`glass-card overflow-hidden ${accentMap[accentColor] || ""}`}>
      <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-800/50">
        <span className="text-lg">{icon}</span>
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          {title}
        </h2>
        <span className="ml-auto text-xs text-gray-500 tabular-nums">
          {rows.length} rows
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800/50">
              {columns.map((col) => (
                <th
                  key={String(col.key)}
                  className="px-4 py-3 text-left text-[11px] font-semibold text-gray-400 uppercase tracking-wider"
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/30">
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-8 text-center text-gray-500"
                >
                  No data
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr
                  key={row.id}
                  className={`
                    transition-colors hover:bg-gray-800/30
                    ${
                      highlightId != null && row.id === highlightId
                        ? "bg-indigo-500/10 border-l-2 border-l-indigo-400"
                        : ""
                    }
                  `}
                >
                  {columns.map((col) => (
                    <td
                      key={String(col.key)}
                      className="px-4 py-3 text-gray-300 whitespace-nowrap font-mono text-xs"
                    >
                      {formatCell(col.key, row[col.key])}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function formatCell(key: string, value: unknown): string {
  if (value == null) return "—";
  if (key === "amount" && typeof value === "number") {
    return `$${value.toFixed(2)}`;
  }
  if (key === "created_at" || key === "__artie_updated_at") {
    try {
      return new Date(String(value)).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return String(value);
    }
  }
  if (key === "status") {
    return String(value).charAt(0).toUpperCase() + String(value).slice(1);
  }
  return String(value);
}
