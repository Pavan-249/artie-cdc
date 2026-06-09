from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import psycopg2

from cdc_pipeline import PG_DSN


def main():
    schema_sql = Path("postgres/init.sql").read_text(encoding="utf-8")
    with psycopg2.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
    print("Postgres trades schema is ready")


if __name__ == "__main__":
    main()
