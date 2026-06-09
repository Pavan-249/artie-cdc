import json
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import clickhouse_connect
import psycopg2
from psycopg2.extras import LogicalReplicationConnection


PG_DSN = os.getenv("PG_DSN", "host=localhost port=5432 dbname=demo user=postgres password=postgres")
PG_REPL_DSN = os.getenv(
    "PG_REPL_DSN",
    "host=localhost port=5432 dbname=demo user=postgres password=postgres replication=database",
)
CH_HOST = os.getenv("CH_HOST", "localhost")
CH_PORT = int(os.getenv("CH_PORT", "8123"))
CH_USER = os.getenv("CH_USER", "default")
CH_PASSWORD = os.getenv("CH_PASSWORD", "clickhouse")
SLOT_NAME = os.getenv("SLOT_NAME", "mini_artie_slot")
EVENT_LOG = Path(os.getenv("EVENT_LOG", "cdc_events.jsonl"))

ORDER_COLUMNS = ["id", "customer_name", "product", "amount", "status", "created_at"]


def utc_now():
    return datetime.now(timezone.utc)


def json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def wait_for_postgres(timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with psycopg2.connect(PG_DSN) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return
        except Exception as exc:
            print(f"Waiting for Postgres: {exc}", flush=True)
            time.sleep(2)
    raise TimeoutError("Postgres did not become reachable")


def clickhouse_client():
    return clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)


def wait_for_clickhouse(timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            client = clickhouse_client()
            client.command("SELECT 1")
            return client
        except Exception as exc:
            print(f"Waiting for ClickHouse: {exc}", flush=True)
            time.sleep(2)
    raise TimeoutError("ClickHouse did not become reachable")


def ensure_schema(client):
    client.command(
        """
        CREATE TABLE IF NOT EXISTS default.orders (
          id Int64,
          customer_name String,
          product String,
          amount Decimal(12, 2),
          status String,
          created_at DateTime64(6, 'UTC'),
          __artie_operation String,
          __artie_delete UInt8,
          __artie_updated_at DateTime64(6, 'UTC')
        )
        ENGINE = ReplacingMergeTree(__artie_updated_at)
        ORDER BY id
        """
    )


def ensure_slot():
    conn = psycopg2.connect(PG_REPL_DSN, connection_factory=LogicalReplicationConnection)
    cur = conn.cursor()
    try:
        cur.create_replication_slot(SLOT_NAME, output_plugin="wal2json")
        print(f"Created logical replication slot {SLOT_NAME}", flush=True)
    except psycopg2.errors.DuplicateObject:
        conn.rollback()
        print(f"Using existing logical replication slot {SLOT_NAME}", flush=True)
    finally:
        cur.close()
        conn.close()


def normalize_row(row):
    normalized = dict(row)
    if isinstance(normalized.get("created_at"), str):
        normalized["created_at"] = datetime.fromisoformat(normalized["created_at"].replace("Z", "+00:00"))
    if isinstance(normalized.get("created_at"), datetime) and normalized["created_at"].tzinfo is None:
        normalized["created_at"] = normalized["created_at"].replace(tzinfo=timezone.utc)
    return normalized


def insert_versions(client, rows, operation, deleted, version_ts):
    if not rows:
        return
    payload = []
    for row in rows:
        item = normalize_row(row)
        payload.append(
            [
                int(item["id"]),
                item.get("customer_name") or "",
                item.get("product") or "",
                Decimal(str(item.get("amount") or "0")),
                item.get("status") or "",
                item["created_at"],
                operation,
                int(deleted),
                version_ts,
            ]
        )
    client.insert(
        "orders",
        payload,
        column_names=[
            "id",
            "customer_name",
            "product",
            "amount",
            "status",
            "created_at",
            "__artie_operation",
            "__artie_delete",
            "__artie_updated_at",
        ],
    )


def backfill(client):
    with psycopg2.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, customer_name, product, amount, status, created_at FROM orders ORDER BY id")
            rows = [dict(zip(ORDER_COLUMNS, record)) for record in cur.fetchall()]
    version_ts = utc_now()
    insert_versions(client, rows, "SNAPSHOT", 0, version_ts)
    print(f"Backfilled {len(rows)} rows", flush=True)


def column_dict(container):
    names = container.get("columnnames") or container.get("keynames") or []
    values = container.get("columnvalues") or container.get("keyvalues") or []
    return dict(zip(names, values))


def old_row_from_change(change):
    return column_dict(change.get("oldkeys") or {})


def changed_row(change):
    if change["kind"] == "delete":
        return old_row_from_change(change)
    return column_dict(change)


def parse_commit_ts(payload):
    raw = payload.get("timestamp")
    if not raw:
        return utc_now()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return utc_now()


def append_event(event):
    with EVENT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, default=json_default, sort_keys=True) + "\n")


def apply_message(client, msg, payload):
    commit_ts = parse_commit_ts(payload)
    apply_ts = utc_now()
    lag_ms = max(0.0, (apply_ts - commit_ts).total_seconds() * 1000.0)
    changes = payload.get("change", [])

    for change in changes:
        if change.get("table") != "orders":
            continue
        kind = change["kind"]
        row = changed_row(change)
        deleted = 1 if kind == "delete" else 0
        op = kind.upper()
        insert_versions(client, [row], op, deleted, apply_ts)
        append_event(
            {
                "lsn": msg.data_start,
                "commit_timestamp": commit_ts,
                "applied_at": apply_ts,
                "lag_ms": round(lag_ms, 3),
                "operation": op,
                "id": row.get("id"),
                "row": row,
            }
        )
        print(f"{op:6} id={row.get('id')} lag_ms={lag_ms:.1f}", flush=True)

    msg.cursor.send_feedback(flush_lsn=msg.data_start)


def stream_changes(client):
    option_sets = [
        {"include-types": "true", "include-timestamp": "true"},
        {"include-types": "true"},
        {},
    ]
    last_error = None
    for options in option_sets:
        conn = psycopg2.connect(PG_REPL_DSN, connection_factory=LogicalReplicationConnection)
        cur = conn.cursor()
        try:
            print(f"Starting wal2json stream with options={options}", flush=True)
            cur.start_replication(slot_name=SLOT_NAME, options=options, decode=True)

            def consume(msg):
                payload = json.loads(msg.payload)
                apply_message(client, msg, payload)

            cur.consume_stream(consume)
            return
        except Exception as exc:
            last_error = exc
            print(f"wal2json option set failed ({options}): {exc}", flush=True)
            cur.close()
            conn.close()
            time.sleep(1)
    raise RuntimeError(f"Could not start wal2json stream: {last_error}")


def main():
    print("mini-Artie CDC pipeline starting", flush=True)
    wait_for_postgres()
    client = wait_for_clickhouse()
    ensure_schema(client)
    ensure_slot()
    backfill(client)
    stream_changes(client)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCDC pipeline stopped", flush=True)
        sys.exit(0)
