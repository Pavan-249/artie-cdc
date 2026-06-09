#!/usr/bin/env bash
set -euo pipefail

: > cdc_events.jsonl

python - <<'PY'
import clickhouse_connect
import psycopg2

from cdc_pipeline import CH_HOST, CH_PASSWORD, CH_PORT, CH_USER, PG_DSN

with psycopg2.connect(PG_DSN) as conn:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE orders RESTART IDENTITY")

client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)
client.command("TRUNCATE TABLE orders")
PY

echo "Reset Postgres, ClickHouse, and cdc_events.jsonl"
