"""
Database helpers for Postgres and ClickHouse.
"""

from datetime import datetime, timezone
from decimal import Decimal

import clickhouse_connect
import psycopg2
from psycopg2.extras import LogicalReplicationConnection, RealDictCursor

import config


# ── Postgres ────────────────────────────────────────────────────────────────

def get_pg_connection():
    """Return a regular psycopg2 connection."""
    return psycopg2.connect(config.DATABASE_URL)


def get_pg_repl_connection():
    """Return a logical-replication-capable psycopg2 connection."""
    return psycopg2.connect(
        config.DATABASE_REPL_URL,
        connection_factory=LogicalReplicationConnection,
    )


def pg_query(sql: str, params=None) -> list[dict]:
    """Execute a read query and return rows as list of dicts."""
    with get_pg_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [_serialise_row(dict(r)) for r in rows]


def pg_execute(sql: str, params=None):
    """Execute a write query (INSERT/UPDATE/DELETE) and commit."""
    with get_pg_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            conn.commit()
            if cur.description:
                return [_serialise_row(dict(r)) for r in cur.fetchall()]
            return None


# ── ClickHouse ──────────────────────────────────────────────────────────────

def get_ch_client():
    """Return a clickhouse-connect client."""
    kwargs = dict(
        host=config.CH_HOST,
        port=config.CH_PORT,
        username=config.CH_USER,
        password=config.CH_PASSWORD,
        database=config.CH_DATABASE,
    )
    if config.CH_SECURE:
        kwargs["secure"] = True
    return clickhouse_connect.get_client(**kwargs)


def ch_query(sql: str) -> list[dict]:
    """Execute a ClickHouse query and return rows as list of dicts."""
    client = get_ch_client()
    result = client.query(sql)
    columns = result.column_names
    rows = []
    for row in result.result_rows:
        rows.append(_serialise_row(dict(zip(columns, row))))
    return rows


# ── Schema bootstrap ───────────────────────────────────────────────────────

def ensure_pg_schema():
    """Create the orders table in Postgres if it doesn't exist."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id BIGSERIAL PRIMARY KEY,
                    customer_name TEXT NOT NULL,
                    product TEXT NOT NULL,
                    amount NUMERIC(12, 2) NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            cur.execute("ALTER TABLE orders REPLICA IDENTITY FULL")
            conn.commit()


def ensure_ch_schema():
    """Create the orders table in ClickHouse if it doesn't exist."""
    client = get_ch_client()
    client.command("""
        CREATE TABLE IF NOT EXISTS orders (
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
    """)


def seed_initial_data():
    """Insert the 4 seed orders (idempotent via ON CONFLICT)."""
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO orders (customer_name, product, amount, status, created_at)
                VALUES
                    ('Ada Lovelace',       'Keyboard',  149.99, 'paid',    now() - interval '12 minutes'),
                    ('Grace Hopper',       'Monitor',   329.50, 'shipped', now() - interval '9 minutes'),
                    ('Katherine Johnson',  'Desk lamp',  41.25, 'pending', now() - interval '6 minutes'),
                    ('Margaret Hamilton',  'Dock',      119.00, 'paid',    now() - interval '3 minutes')
                ON CONFLICT DO NOTHING
            """)
            conn.commit()


def ensure_wal_level():
    """
    Check and set wal_level to logical if possible.
    Returns True if wal_level is already logical, False otherwise.
    """
    try:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SHOW wal_level")
                level = cur.fetchone()[0]
                if level == "logical":
                    return True
                # Try to set it (requires superuser; may fail on managed PG)
                try:
                    cur.execute("ALTER SYSTEM SET wal_level = 'logical'")
                    conn.commit()
                    print("Set wal_level=logical (restart required)", flush=True)
                except Exception as e:
                    print(f"Cannot set wal_level=logical: {e}", flush=True)
                return False
    except Exception as e:
        print(f"Cannot check wal_level: {e}", flush=True)
        return False


# ── Helpers ─────────────────────────────────────────────────────────────────

def _serialise_row(row: dict) -> dict:
    """Convert Decimal/datetime values to JSON-safe types."""
    out = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out
