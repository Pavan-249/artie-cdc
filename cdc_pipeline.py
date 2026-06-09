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


TABLE_NAME = "trades"
SOURCE_COLUMNS = [
    "trade_id",
    "trade_ts",
    "account_id",
    "client_name",
    "desk",
    "trader",
    "symbol",
    "asset_class",
    "side",
    "quantity",
    "price",
    "notional_usd",
    "venue",
    "risk_score",
    "status",
    "updated_at",
]
DECIMAL_COLUMNS = {"quantity", "price", "notional_usd"}
TIMESTAMP_COLUMNS = {"trade_ts", "updated_at"}


def load_env_file(path=".env"):
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load_env_file()


PG_DSN = os.getenv("PG_DSN", "host=localhost port=5432 dbname=demo user=postgres password=postgres")
PG_REPL_DSN = os.getenv(
    "PG_REPL_DSN",
    "host=localhost port=5432 dbname=demo user=postgres password=postgres replication=database",
)
CH_HOST = os.getenv("CH_HOST", "localhost")
CH_PORT = int(os.getenv("CH_PORT", "8123"))
CH_USER = os.getenv("CH_USER", "default")
CH_PASSWORD = os.getenv("CH_PASSWORD", "clickhouse")
SLOT_NAME = os.getenv("SLOT_NAME", "finance_cdc_slot")
EVENT_LOG = Path(os.getenv("EVENT_LOG", "cdc_events.jsonl"))


def utc_now():
    return datetime.now(timezone.utc)


def json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def parse_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


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
        CREATE TABLE IF NOT EXISTS default.trades (
          trade_id Int64,
          trade_ts DateTime64(6, 'UTC'),
          account_id String,
          client_name String,
          desk String,
          trader String,
          symbol String,
          asset_class String,
          side String,
          quantity Decimal(18, 4),
          price Decimal(18, 4),
          notional_usd Decimal(18, 2),
          venue String,
          risk_score Int32,
          status String,
          updated_at DateTime64(6, 'UTC'),
          __cdc_operation String,
          __cdc_is_deleted UInt8,
          __cdc_updated_at DateTime64(6, 'UTC')
        )
        ENGINE = ReplacingMergeTree(__cdc_updated_at)
        ORDER BY trade_id
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
    for column in TIMESTAMP_COLUMNS:
        normalized[column] = parse_datetime(normalized[column])
    for column in DECIMAL_COLUMNS:
        normalized[column] = Decimal(str(normalized[column]))
    normalized["trade_id"] = int(normalized["trade_id"])
    normalized["risk_score"] = int(normalized["risk_score"])
    return normalized


def insert_versions(client, rows, operation, deleted, version_ts):
    if not rows:
        return
    payload = []
    for row in rows:
        item = normalize_row(row)
        payload.append(
            [
                item["trade_id"],
                item["trade_ts"],
                item["account_id"],
                item["client_name"],
                item["desk"],
                item["trader"],
                item["symbol"],
                item["asset_class"],
                item["side"],
                item["quantity"],
                item["price"],
                item["notional_usd"],
                item["venue"],
                item["risk_score"],
                item["status"],
                item["updated_at"],
                operation,
                int(deleted),
                version_ts,
            ]
        )
    client.insert(
        TABLE_NAME,
        payload,
        column_names=[
            *SOURCE_COLUMNS,
            "__cdc_operation",
            "__cdc_is_deleted",
            "__cdc_updated_at",
        ],
    )


def backfill(client):
    with psycopg2.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT trade_id, trade_ts, account_id, client_name, desk, trader,
                       symbol, asset_class, side, quantity, price, notional_usd,
                       venue, risk_score, status, updated_at
                FROM trades
                ORDER BY trade_id
                """
            )
            rows = [dict(zip(SOURCE_COLUMNS, record)) for record in cur.fetchall()]
    version_ts = utc_now()
    insert_versions(client, rows, "SNAPSHOT", 0, version_ts)
    print(f"Backfilled {len(rows)} trades", flush=True)


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
        return parse_datetime(raw)
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
        if change.get("table") != TABLE_NAME:
            continue
        kind = change["kind"]
        row = changed_row(change)
        deleted = 1 if kind == "delete" else 0
        operation = kind.upper()
        insert_versions(client, [row], operation, deleted, apply_ts)
        append_event(
            {
                "lsn": msg.data_start,
                "commit_timestamp": commit_ts,
                "applied_at": apply_ts,
                "lag_ms": round(lag_ms, 3),
                "operation": operation,
                "trade_id": row.get("trade_id"),
                "row": row,
            }
        )
        print(f"{operation:6} trade_id={row.get('trade_id')} lag_ms={lag_ms:.1f}", flush=True)

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
    print("Finance CDC worker starting", flush=True)
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
        print("\nCDC worker stopped", flush=True)
        sys.exit(0)
