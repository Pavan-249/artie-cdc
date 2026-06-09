"use client";

import { useState } from "react";
import {
  insertOrder,
  updateOrder,
  deleteOrder,
  resetDemo,
} from "@/lib/api";

interface ActionButtonsProps {
  onAction?: () => void;
}

export default function ActionButtons({ onAction }: ActionButtonsProps) {
  const [loading, setLoading] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<string | null>(null);

  async function handleAction(
    name: string,
    action: () => Promise<unknown>
  ) {
    setLoading(name);
    setLastResult(null);
    try {
      await action();
      setLastResult(`${name} ✓`);
      onAction?.();
    } catch (err) {
      setLastResult(`${name} failed: ${err}`);
    } finally {
      setLoading(null);
    }
  }

  const buttons = [
    {
      label: "Insert Order",
      icon: "➕",
      action: () => insertOrder(),
      color:
        "bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 border-emerald-500/30",
    },
    {
      label: "Update Order",
      icon: "✏️",
      action: () => updateOrder(),
      color:
        "bg-blue-500/15 hover:bg-blue-500/25 text-blue-400 border-blue-500/30",
    },
    {
      label: "Delete Order",
      icon: "🗑️",
      action: () => deleteOrder(),
      color:
        "bg-red-500/15 hover:bg-red-500/25 text-red-400 border-red-500/30",
    },
    {
      label: "Reset Demo",
      icon: "🔄",
      action: () => resetDemo(),
      color:
        "bg-amber-500/15 hover:bg-amber-500/25 text-amber-400 border-amber-500/30",
    },
  ];

  return (
    <div className="glass-card p-5">
      <div className="flex items-center gap-3 mb-4">
        <span className="text-lg">🎮</span>
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          Actions
        </h2>
        {lastResult && (
          <span className="ml-auto text-xs text-gray-400 animate-fade-in-up">
            {lastResult}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {buttons.map((btn) => (
          <button
            key={btn.label}
            id={`action-${btn.label.toLowerCase().replace(/\s+/g, "-")}`}
            disabled={loading !== null}
            onClick={() => handleAction(btn.label, btn.action)}
            className={`
              flex items-center justify-center gap-2 px-4 py-3
              rounded-xl border font-medium text-sm
              transition-all duration-200
              disabled:opacity-40 disabled:cursor-not-allowed
              cursor-pointer
              ${btn.color}
            `}
          >
            {loading === btn.label ? (
              <span className="animate-spin text-sm">⏳</span>
            ) : (
              <span>{btn.icon}</span>
            )}
            {btn.label}
          </button>
        ))}
      </div>

      <p className="text-[11px] text-gray-500 mt-3 text-center">
        Actions write to Postgres only — CDC worker replicates changes to
        ClickHouse automatically
      </p>
    </div>
  );
}
