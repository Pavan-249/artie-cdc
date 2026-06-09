"""
CDC Worker – reads Postgres WAL via logical replication (wal2json),
applies changes to ClickHouse, and broadcasts normalised events
to SSE subscribers.

Runs in a daemon thread so the FastAPI server stays responsive.
"""

import json
import threading
import time
import asyncio
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal

import psycopg2

import config
import db


# ── Shared state ────────────────────────────────────────────────────────────

# Ring buffer of last 200 events (thread-safe via deque maxlen)
event_buffer: deque[dict] = deque(maxlen=200)

# List of asyncio.Queue objects — one per SSE subscriber
_subscribers: list[asyncio.Queue] = []
_subscribers_lock = threading.Lock()

# Stop signal for graceful shutdown
_stop_event = threading.Event()

# Pipeline status
pipeline_status: dict = {"status": "starting", "error": None, "started_at": None}


# ── Subscriber management ──────────────────────────────────────────────────

def add_subscriber(queue: asyncio.Queue) -> None:
    with _subscribers_lock:
        _subscribers.append(queue)


def remove_subscriber(queue: asyncio.Queue) -> None:
    with _subscribers_lock:
        try:
            _subscribers.remove(queue)
        except ValueError:
            pass


def _broadcast(event: dict) -> None:
    """Push an event to every SSE subscriber queue (non-blocking)."""
    with _subscribers_lock:
        dead = []
        for q in _subscribers:
            try:
                q.put_nowait(event)
            except Exception:
                dead.append(q)
        for q in dead:
            try:
                _subscribers.remove(q)
            except ValueError:
                pass


# ── Helpers ─────────────────────────────────────────────────────────────────

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _column_dict(container: dict) -> dict:
    names = container.get("columnnames") or container.get("keynames") or []
    values = container.get("columnvalues") or container.get("keyvalues") or []
    return dict(zip(names, values))


def _old_row_from_change(change: dict) -> dict:
    return _column_dict(change.get("oldkeys") or {})


def _changed_row(change: dict) -> dict:
    if change["kind"] == "delete":
        return _old_row_from_change(change)
    return _column_dict(change)


def _parse_commit_ts(payload: dict) -> datetime:
    raw = payload.get("timestamp")
    if not raw:
        return _utc_now()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return _utc_now()


def _normalize_row(row: dict) -> dict:
    normalized = dict(row)
    if isinstance(normalized.get("created_at"), str):
        try:
            normalized["created_at"] = datetime.fromisoformat(
                normalized["created_at"].replace("Z", "+00:00")
            )
        except ValueError:
            pass
    if isinstance(normalized.get("created_at"), datetime) and normalized["created_at"].tzinfo is None:
        normalized["created_at"] = normalized["created_at"].replace(tzinfo=timezone.utc)
    return normalized


def _build_sql_fired(op: str, row: dict) -> str:
    """Build a human-readable SQL string showing what was applied to ClickHouse."""
    row_safe = {k: v for k, v in row.items()}
    if op == "INSERT":
        cols = ", ".join(row_safe.keys())
        vals = ", ".join(repr(v) for v in row_safe.values())
        return f"INSERT INTO orders ({cols}) VALUES ({vals})"
    elif op == "UPDATE":
        sets = ", ".join(f"{k} = {repr(v)}" for k, v in row_safe.items() if k != "id")
        return f"UPDATE orders SET {sets} WHERE id = {row_safe.get('id')}"
    elif op == "DELETE":
        return f"DELETE FROM orders WHERE id = {row_safe.get('id')}"
    return f"-- {op} on orders"


# ── ClickHouse writer ──────────────────────────────────────────────────────

ORDER_COLUMNS = ["id", "customer_name", "product", "amount", "status", "created_at"]


def _insert_version(ch_client, row: dict, operation: str, deleted: int, version_ts: datetime):
    """Write a single version row to ClickHouse ReplacingMergeTree."""
    item = _normalize_row(row)
    payload = [[
        int(item["id"]),
        item.get("customer_name") or "",
        item.get("product") or "",
        Decimal(str(item.get("amount") or "0")),
        item.get("status") or "",
        item.get("created_at") or version_ts,
        operation,
        deleted,
        version_ts,
    ]]
    ch_client.insert(
        "orders",
        payload,
        column_names=[
            "id", "customer_name", "product", "amount", "status", "created_at",
            "__artie_operation", "__artie_delete", "__artie_updated_at",
        ],
    )


# ── Backfill ────────────────────────────────────────────────────────────────

def _backfill(ch_client):
    """Snapshot current Postgres rows into ClickHouse."""
    rows = db.pg_query(
        "SELECT id, customer_name, product, amount, status, created_at FROM orders ORDER BY id"
    )
    version_ts = _utc_now()
    for row in rows:
        _insert_version(ch_client, row, "SNAPSHOT", 0, version_ts)
    print(f"Backfilled {len(rows)} rows", flush=True)


# ── Replication slot ────────────────────────────────────────────────────────

def _ensure_slot():
    """Create the logical replication slot if it doesn't exist."""
    conn = db.get_pg_repl_connection()
    cur = conn.cursor()
    try:
        cur.create_replication_slot(config.SLOT_NAME, output_plugin="wal2json")
        print(f"Created replication slot: {config.SLOT_NAME}", flush=True)
    except psycopg2.errors.DuplicateObject:
        conn.rollback()
        print(f"Replication slot exists: {config.SLOT_NAME}", flush=True)
    finally:
        cur.close()
        conn.close()


# ── Stream processing ──────────────────────────────────────────────────────

def _process_message(ch_client, msg, payload):
    """Process a single WAL message: apply to ClickHouse + emit event."""
    commit_ts = _parse_commit_ts(payload)
    apply_ts = _utc_now()
    lag_ms = max(0.0, (apply_ts - commit_ts).total_seconds() * 1000.0)
    changes = payload.get("change", [])

    for change in changes:
        if change.get("table") != "orders":
            continue

        kind = change["kind"]
        op = kind.upper()
        new_row = _column_dict(change) if kind != "delete" else {}
        old_row = _old_row_from_change(change)
        row = new_row if kind != "delete" else old_row
        deleted = 1 if kind == "delete" else 0

        # Apply to ClickHouse
        _insert_version(ch_client, row, op, deleted, apply_ts)

        # Build diff for UPDATE
        diff = {}
        if kind == "update" and old_row and new_row:
            for k in new_row:
                old_val = old_row.get(k)
                new_val = new_row.get(k)
                if str(old_val) != str(new_val):
                    diff[k] = {"old": old_val, "new": new_val}

        # Build normalised event
        event = {
            "op": op,
            "table": "orders",
            "pk": row.get("id"),
            "before": _safe_dict(old_row),
            "after": _safe_dict(new_row),
            "diff": _safe_dict(diff),
            "commit_ts": commit_ts.isoformat(),
            "apply_ts": apply_ts.isoformat(),
            "lag_ms": round(lag_ms, 3),
            "sql_fired": _build_sql_fired(op, row),
        }

        # Store + broadcast
        event_buffer.append(event)
        _broadcast(event)

        print(f"CDC {op:6} id={row.get('id')} lag={lag_ms:.1f}ms", flush=True)

    msg.cursor.send_feedback(flush_lsn=msg.data_start)


def _safe_dict(d: dict) -> dict:
    """Make a dict JSON-safe."""
    out = {}
    for k, v in d.items():
        if isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, dict):
            out[k] = _safe_dict(v)
        else:
            out[k] = v
    return out


def _stream_loop(ch_client):
    """Main streaming loop — tries multiple wal2json option sets."""
    option_sets = [
        {"include-types": "true", "include-timestamp": "true"},
        {"include-types": "true"},
        {},
    ]

    while not _stop_event.is_set():
        for options in option_sets:
            conn = None
            try:
                conn = db.get_pg_repl_connection()
                cur = conn.cursor()
                print(f"Starting WAL stream with options={options}", flush=True)
                cur.start_replication(
                    slot_name=config.SLOT_NAME,
                    options=options,
                    decode=True,
                )

                pipeline_status["status"] = "running"
                pipeline_status["error"] = None
                pipeline_status["started_at"] = _utc_now().isoformat()

                def consume(msg):
                    if _stop_event.is_set():
                        raise StopIteration("Shutdown requested")
                    payload = json.loads(msg.payload)
                    _process_message(ch_client, msg, payload)

                cur.consume_stream(consume)
                return  # clean exit
            except StopIteration:
                return  # shutdown
            except Exception as exc:
                print(f"WAL stream error ({options}): {exc}", flush=True)
                pipeline_status["status"] = "error"
                pipeline_status["error"] = str(exc)
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
                time.sleep(2)

        # If all option sets failed, wait before retrying
        if not _stop_event.is_set():
            print("All WAL option sets failed, retrying in 5s...", flush=True)
            time.sleep(5)


# ── Thread entry point ─────────────────────────────────────────────────────

def _worker_main():
    """Top-level worker function that runs in a daemon thread."""
    try:
        print("CDC worker starting...", flush=True)

        # Wait for Postgres
        for attempt in range(30):
            try:
                db.get_pg_connection().close()
                break
            except Exception as e:
                print(f"Waiting for Postgres ({attempt+1}/30): {e}", flush=True)
                time.sleep(3)
        else:
            pipeline_status["status"] = "error"
            pipeline_status["error"] = "Postgres not reachable after 90s"
            return

        # Wait for ClickHouse
        ch_client = None
        for attempt in range(30):
            try:
                ch_client = db.get_ch_client()
                ch_client.command("SELECT 1")
                break
            except Exception as e:
                print(f"Waiting for ClickHouse ({attempt+1}/30): {e}", flush=True)
                time.sleep(3)
        else:
            pipeline_status["status"] = "error"
            pipeline_status["error"] = "ClickHouse not reachable after 90s"
            return

        # Bootstrap
        db.ensure_pg_schema()
        db.ensure_ch_schema()
        _ensure_slot()
        _backfill(ch_client)

        # Stream
        _stream_loop(ch_client)

    except Exception as exc:
        pipeline_status["status"] = "error"
        pipeline_status["error"] = str(exc)
        print(f"CDC worker fatal error: {exc}", flush=True)


_worker_thread: threading.Thread | None = None


def start():
    """Start the CDC worker in a background daemon thread."""
    global _worker_thread
    _stop_event.clear()
    _worker_thread = threading.Thread(target=_worker_main, daemon=True, name="cdc-worker")
    _worker_thread.start()
    print("CDC worker thread launched", flush=True)


def stop():
    """Signal the CDC worker to stop."""
    _stop_event.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=5)
    print("CDC worker stopped", flush=True)
