from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import clickhouse_connect

from cdc_pipeline import CH_HOST, CH_PASSWORD, CH_PORT, CH_USER


def main():
    schema_sql = Path("clickhouse/init.sql").read_text(encoding="utf-8").strip().rstrip(";")
    client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)
    client.command(schema_sql)
    print("ClickHouse trades schema is ready")


if __name__ == "__main__":
    main()
