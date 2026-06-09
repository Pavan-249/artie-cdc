// ── API Client ─────────────────────────────────────────────────────────────
// All requests go to the FastAPI backend. No secrets are exposed here.

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────

export interface Order {
  id: number;
  customer_name: string;
  product: string;
  amount: number;
  status: string;
  created_at: string;
  __artie_operation?: string;
  __artie_updated_at?: string;
}

export interface CDCEvent {
  op: "INSERT" | "UPDATE" | "DELETE" | "SNAPSHOT";
  table: string;
  pk: number;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  diff: Record<string, unknown>;
  commit_ts: string;
  apply_ts: string;
  lag_ms: number;
  sql_fired: string;
}

export interface HealthResponse {
  status: string;
  postgres: string;
  clickhouse: string;
  cdc_worker: {
    status: string;
    error: string | null;
    started_at: string | null;
  };
}

export interface MetricsResponse {
  events_replicated: number;
  rows_synced: number;
  pg_rows: number;
  p95_latency_ms: number;
  avg_latency_ms: number;
  pipeline_status: string;
  in_sync: boolean;
}

// ── Fetch helpers ──────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

// ── Endpoints ──────────────────────────────────────────────────────────────

export async function fetchHealth(): Promise<HealthResponse> {
  return apiFetch("/health");
}

export async function fetchMetrics(): Promise<MetricsResponse> {
  return apiFetch("/metrics");
}

export async function fetchSourceOrders(): Promise<{ rows: Order[] }> {
  return apiFetch("/orders/source");
}

export async function fetchClickHouseOrders(): Promise<{ rows: Order[] }> {
  return apiFetch("/orders/clickhouse");
}

export async function insertOrder(data?: {
  customer_name?: string;
  product?: string;
  amount?: number;
  status?: string;
}): Promise<{ ok: boolean; order: Order }> {
  return apiFetch("/orders/insert", {
    method: "POST",
    body: JSON.stringify(data || {}),
  });
}

export async function updateOrder(data?: {
  id?: number;
  customer_name?: string;
  product?: string;
  amount?: number;
  status?: string;
}): Promise<{ ok: boolean; order: Order }> {
  return apiFetch("/orders/update", {
    method: "POST",
    body: JSON.stringify(data || {}),
  });
}

export async function deleteOrder(
  id?: number
): Promise<{ ok: boolean; deleted_id: number }> {
  return apiFetch("/orders/delete", {
    method: "POST",
    body: JSON.stringify(id != null ? { id } : {}),
  });
}

export async function resetDemo(): Promise<{
  ok: boolean;
  errors: string[] | null;
  message: string;
}> {
  return apiFetch("/reset", { method: "POST" });
}

// ── SSE ────────────────────────────────────────────────────────────────────

export function subscribeToEvents(
  onEvent: (event: CDCEvent) => void,
  onError?: (err: Event) => void
): () => void {
  const es = new EventSource(`${API_URL}/events/stream?catchup=true`);

  es.addEventListener("cdc", (e) => {
    try {
      const data: CDCEvent = JSON.parse(e.data);
      onEvent(data);
    } catch {
      // ignore parse errors
    }
  });

  es.addEventListener("ping", () => {
    // keepalive — no action needed
  });

  es.onerror = (e) => {
    if (onError) onError(e);
  };

  // Return unsubscribe function
  return () => {
    es.close();
  };
}
