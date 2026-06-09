"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { CDCEvent, MetricsResponse, Order } from "@/lib/api";
import {
  fetchMetrics,
  fetchSourceOrders,
  fetchClickHouseOrders,
  subscribeToEvents,
} from "@/lib/api";

import PipelineVisualization from "@/components/PipelineVisualization";
import KPICards from "@/components/KPICards";
import ChangeFeed from "@/components/ChangeFeed";
import SQLPanel from "@/components/SQLPanel";
import DataTable from "@/components/DataTable";
import ActionButtons from "@/components/ActionButtons";

const SOURCE_COLUMNS: { key: keyof Order; label: string }[] = [
  { key: "id", label: "ID" },
  { key: "customer_name", label: "Customer" },
  { key: "product", label: "Product" },
  { key: "amount", label: "Amount" },
  { key: "status", label: "Status" },
  { key: "created_at", label: "Created" },
];

const CH_COLUMNS: { key: keyof Order; label: string }[] = [
  { key: "id", label: "ID" },
  { key: "customer_name", label: "Customer" },
  { key: "product", label: "Product" },
  { key: "amount", label: "Amount" },
  { key: "status", label: "Status" },
  { key: "created_at", label: "Created" },
  { key: "__artie_operation", label: "CDC Op" },
  { key: "__artie_updated_at", label: "Replicated At" },
];

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [sourceOrders, setSourceOrders] = useState<Order[]>([]);
  const [chOrders, setCHOrders] = useState<Order[]>([]);
  const [events, setEvents] = useState<CDCEvent[]>([]);
  const [lastPk, setLastPk] = useState<number | null>(null);
  const [connected, setConnected] = useState(false);

  const eventsRef = useRef(events);
  eventsRef.current = events;

  // ── Refresh data from backend ────────────────────────────────────────
  const refreshData = useCallback(async () => {
    try {
      const [m, src, ch] = await Promise.all([
        fetchMetrics(),
        fetchSourceOrders(),
        fetchClickHouseOrders(),
      ]);
      setMetrics(m);
      setSourceOrders(src.rows);
      setCHOrders(ch.rows);
    } catch (err) {
      console.error("Refresh failed:", err);
    }
  }, []);

  // ── SSE subscription ─────────────────────────────────────────────────
  useEffect(() => {
    const unsubscribe = subscribeToEvents(
      (event) => {
        setEvents((prev) => [event, ...prev].slice(0, 100));
        setLastPk(event.pk);
        setConnected(true);
        // Debounce data refresh — wait a bit for CDC to complete
        setTimeout(refreshData, 500);
      },
      () => {
        setConnected(false);
      }
    );

    return unsubscribe;
  }, [refreshData]);

  // ── Initial data load + polling ──────────────────────────────────────
  useEffect(() => {
    refreshData();
    const interval = setInterval(refreshData, 5000);
    return () => clearInterval(interval);
  }, [refreshData]);

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Header */}
      <header className="border-b border-gray-800/50 bg-gray-950/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-[1440px] mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white text-sm font-bold shadow-lg shadow-indigo-500/20">
                ⚡
              </div>
              <div>
                <h1 className="text-base font-bold text-gray-100 tracking-tight">
                  CDC Pipeline
                </h1>
                <p className="text-[11px] text-gray-500 -mt-0.5">
                  Postgres → ClickHouse · Real-time
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div
              className={`
                flex items-center gap-2 text-xs font-medium px-3 py-1.5 rounded-full
                ${
                  connected
                    ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                    : "bg-red-500/15 text-red-400 border border-red-500/30"
                }
              `}
            >
              <div
                className={`w-1.5 h-1.5 rounded-full ${
                  connected ? "bg-emerald-400 animate-pulse" : "bg-red-400"
                }`}
              />
              {connected ? "SSE Connected" : "Disconnected"}
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-[1440px] mx-auto px-6 py-6 space-y-6">
        {/* Pipeline Visualization */}
        <PipelineVisualization
          pipelineStatus={metrics?.pipeline_status || "starting"}
        />

        {/* KPI Cards */}
        <KPICards metrics={metrics} />

        {/* Action Buttons */}
        <ActionButtons onAction={refreshData} />

        {/* Live Feed + SQL Panel */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ChangeFeed events={events} />
          <SQLPanel events={events} />
        </div>

        {/* Source + ClickHouse Tables */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <DataTable
            title="Source — Postgres"
            icon="🐘"
            rows={sourceOrders}
            highlightId={lastPk}
            columns={SOURCE_COLUMNS}
            accentColor="blue"
          />
          <DataTable
            title="Replica — ClickHouse"
            icon="🏠"
            rows={chOrders}
            highlightId={lastPk}
            columns={CH_COLUMNS}
            accentColor="emerald"
          />
        </div>

        {/* Footer */}
        <footer className="text-center py-6 text-xs text-gray-600">
          Real CDC pipeline — no mocks, no replays. Actions write to Postgres →
          WAL → wal2json → Python CDC worker → ClickHouse
        </footer>
      </main>
    </div>
  );
}
