"""
FastAPI backend for the CDC demo.

Endpoints:
  GET  /health           – health check
  GET  /metrics          – KPI metrics
  GET  /orders/source    – Postgres orders
  GET  /orders/clickhouse – ClickHouse orders
  POST /orders/insert    – insert order into Postgres
  POST /orders/update    – update order in Postgres
  POST /orders/delete    – delete order from Postgres
  POST /reset            – reset demo (truncate + reseed)
  GET  /events/stream    – SSE stream of CDC events
"""

import asyncio
import statistics
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

import cdc_worker
import config
import db


# ── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start CDC worker on startup, stop on shutdown."""
    cdc_worker.start()
    yield
    cdc_worker.stop()


app = FastAPI(
    title="CDC Pipeline API",
    description="Real Postgres → ClickHouse CDC pipeline backend",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ────────────────────────────────────────────────────────────────────

origins = [config.FRONTEND_URL] if config.FRONTEND_URL != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request models ──────────────────────────────────────────────────────────

class InsertOrderRequest(BaseModel):
    customer_name: str = "Demo Buyer"
    product: str = "Mechanical Keyboard"
    amount: float = 149.99
    status: str = "pending"


class UpdateOrderRequest(BaseModel):
    id: int
    customer_name: Optional[str] = None
    product: Optional[str] = None
    amount: Optional[float] = None
    status: Optional[str] = None


class DeleteOrderRequest(BaseModel):
    id: Optional[int] = None  # None = delete latest


# ── Health ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    pg_ok = False
    ch_ok = False
    try:
        db.pg_query("SELECT 1")
        pg_ok = True
    except Exception:
        pass
    try:
        db.ch_query("SELECT 1")
        ch_ok = True
    except Exception:
        pass
    return {
        "status": "ok" if pg_ok and ch_ok else "degraded",
        "postgres": "up" if pg_ok else "down",
        "clickhouse": "up" if ch_ok else "down",
        "cdc_worker": cdc_worker.pipeline_status,
    }


# ── Metrics ─────────────────────────────────────────────────────────────────

@app.get("/metrics")
async def metrics():
    events = list(cdc_worker.event_buffer)
    total = len(events)
    lags = [e["lag_ms"] for e in events if e.get("lag_ms") is not None]

    p95 = 0
    avg_lag = 0
    if lags:
        sorted_lags = sorted(lags)
        p95_idx = int(len(sorted_lags) * 0.95)
        p95 = sorted_lags[min(p95_idx, len(sorted_lags) - 1)]
        avg_lag = statistics.mean(lags)

    # Row counts
    pg_count = 0
    ch_count = 0
    try:
        result = db.pg_query("SELECT count(*) AS n FROM orders")
        pg_count = result[0]["n"] if result else 0
    except Exception:
        pass
    try:
        result = db.ch_query(
            "SELECT count(*) AS n FROM orders FINAL WHERE __artie_delete = 0"
        )
        ch_count = result[0]["n"] if result else 0
    except Exception:
        pass

    return {
        "events_replicated": total,
        "rows_synced": ch_count,
        "pg_rows": pg_count,
        "p95_latency_ms": round(p95, 2),
        "avg_latency_ms": round(avg_lag, 2),
        "pipeline_status": cdc_worker.pipeline_status["status"],
        "in_sync": pg_count == ch_count,
    }


# ── Orders ──────────────────────────────────────────────────────────────────

@app.get("/orders/source")
async def orders_source():
    try:
        rows = db.pg_query(
            "SELECT id, customer_name, product, amount, status, created_at "
            "FROM orders ORDER BY id"
        )
        return {"rows": rows}
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"error": f"Postgres unavailable: {exc}"},
        )


@app.get("/orders/clickhouse")
async def orders_clickhouse():
    try:
        rows = db.ch_query(
            "SELECT id, customer_name, product, amount, status, created_at, "
            "__artie_operation, __artie_updated_at "
            "FROM orders FINAL WHERE __artie_delete = 0 ORDER BY id"
        )
        return {"rows": rows}
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"error": f"ClickHouse unavailable: {exc}"},
        )


@app.post("/orders/insert")
async def orders_insert(req: InsertOrderRequest):
    """Insert a new order into Postgres only. CDC handles the rest."""
    try:
        result = db.pg_execute(
            "INSERT INTO orders (customer_name, product, amount, status) "
            "VALUES (%s, %s, %s, %s) RETURNING id, customer_name, product, amount, status, created_at",
            (req.customer_name, req.product, req.amount, req.status),
        )
        return {"ok": True, "order": result[0] if result else None}
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": str(exc)},
        )


@app.post("/orders/update")
async def orders_update(req: UpdateOrderRequest):
    """Update an order in Postgres only. CDC handles the rest."""
    try:
        # If no id provided, update the latest
        order_id = req.id
        if order_id is None:
            rows = db.pg_query("SELECT id FROM orders ORDER BY id DESC LIMIT 1")
            if not rows:
                return JSONResponse(status_code=404, content={"error": "No orders to update"})
            order_id = rows[0]["id"]

        # Build SET clause from provided fields
        updates = []
        params = []
        if req.customer_name is not None:
            updates.append("customer_name = %s")
            params.append(req.customer_name)
        if req.product is not None:
            updates.append("product = %s")
            params.append(req.product)
        if req.amount is not None:
            updates.append("amount = %s")
            params.append(req.amount)
        if req.status is not None:
            updates.append("status = %s")
            params.append(req.status)

        if not updates:
            # Default: ship the order and bump the amount
            updates = ["status = %s", "amount = amount + %s"]
            params = ["shipped", 10.00]

        params.append(order_id)
        sql = f"UPDATE orders SET {', '.join(updates)} WHERE id = %s RETURNING id, customer_name, product, amount, status, created_at"
        result = db.pg_execute(sql, params)
        return {"ok": True, "order": result[0] if result else None}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/orders/delete")
async def orders_delete(req: DeleteOrderRequest):
    """Delete an order from Postgres only. CDC handles the rest."""
    try:
        order_id = req.id
        if order_id is None:
            rows = db.pg_query("SELECT id FROM orders ORDER BY id DESC LIMIT 1")
            if not rows:
                return JSONResponse(status_code=404, content={"error": "No orders to delete"})
            order_id = rows[0]["id"]

        db.pg_execute("DELETE FROM orders WHERE id = %s", (order_id,))
        return {"ok": True, "deleted_id": order_id}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


# ── Reset ───────────────────────────────────────────────────────────────────

@app.post("/reset")
async def reset():
    """
    Reset the demo: truncate both tables, drop/recreate slot, reseed.
    This is an admin endpoint for demo setup.
    """
    errors = []

    # Stop the CDC worker
    cdc_worker.stop()

    # Truncate Postgres
    try:
        db.pg_execute("TRUNCATE TABLE orders RESTART IDENTITY")
    except Exception as exc:
        errors.append(f"PG truncate: {exc}")

    # Drop replication slot
    try:
        with db.get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_drop_replication_slot(slot_name) "
                    "FROM pg_replication_slots WHERE slot_name = %s",
                    (config.SLOT_NAME,),
                )
                conn.commit()
    except Exception as exc:
        errors.append(f"Slot drop: {exc}")

    # Truncate ClickHouse
    try:
        ch = db.get_ch_client()
        ch.command("TRUNCATE TABLE orders")
    except Exception as exc:
        errors.append(f"CH truncate: {exc}")

    # Clear event buffer
    cdc_worker.event_buffer.clear()

    # Re-seed
    try:
        db.seed_initial_data()
    except Exception as exc:
        errors.append(f"Seed: {exc}")

    # Restart CDC worker
    cdc_worker.start()

    return {
        "ok": len(errors) == 0,
        "errors": errors if errors else None,
        "message": "Demo reset and CDC worker restarted",
    }


# ── SSE ─────────────────────────────────────────────────────────────────────

@app.get("/events/stream")
async def events_stream(
    catchup: bool = Query(default=True, description="Send buffered events first"),
):
    """
    Server-Sent Events stream of CDC events.
    Sends buffered events first (if catchup=true), then live events.
    """

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        cdc_worker.add_subscriber(queue)
        try:
            # Send catch-up events from the ring buffer
            if catchup:
                for event in list(cdc_worker.event_buffer):
                    yield {
                        "event": "cdc",
                        "data": _event_json(event),
                    }

            # Stream live events
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield {
                        "event": "cdc",
                        "data": _event_json(event),
                    }
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"event": "ping", "data": "{}"}
        finally:
            cdc_worker.remove_subscriber(queue)

    return EventSourceResponse(event_generator())


def _event_json(event: dict) -> str:
    import json
    return json.dumps(event, default=str)


# ── Run directly ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, reload=False)
