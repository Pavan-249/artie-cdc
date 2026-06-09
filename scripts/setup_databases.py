from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.setup_clickhouse import main as setup_clickhouse
from scripts.setup_postgres import main as setup_postgres


def main():
    setup_postgres()
    setup_clickhouse()


if __name__ == "__main__":
    main()
