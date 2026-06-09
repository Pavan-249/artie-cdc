import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import clickhouse_connect
import psycopg2

from cdc_pipeline import CH_HOST, CH_PASSWORD, CH_PORT, CH_USER, EVENT_LOG, PG_DSN
from scripts.setup_databases import main as setup_databases


DATASET_PATH = ROOT / "data" / "trades_seed.csv"


def reset_postgres():
    with psycopg2.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE trades")


def reset_clickhouse():
    client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)
    client.command("TRUNCATE TABLE trades")


def read_seed_trades():
    with DATASET_PATH.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def insert_seed_trades(rows):
    with psycopg2.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO trades (
                      trade_id, trade_ts, account_id, client_name, desk, trader,
                      symbol, asset_class, side, quantity, price, notional_usd,
                      venue, risk_score, status, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        int(row["trade_id"]),
                        datetime.fromisoformat(row["trade_ts"]),
                        row["account_id"],
                        row["client_name"],
                        row["desk"],
                        row["trader"],
                        row["symbol"],
                        row["asset_class"],
                        row["side"],
                        Decimal(row["quantity"]),
                        Decimal(row["price"]),
                        Decimal(row["notional_usd"]),
                        row["venue"],
                        int(row["risk_score"]),
                        row["status"],
                        datetime.fromisoformat(row["trade_ts"]),
                    ),
                )


def main():
    setup_databases()
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    EVENT_LOG.write_text("", encoding="utf-8")
    rows = read_seed_trades()
    reset_postgres()
    reset_clickhouse()
    insert_seed_trades(rows)
    print(f"Loaded {len(rows)} deterministic finance trades from {DATASET_PATH}")


if __name__ == "__main__":
    main()
