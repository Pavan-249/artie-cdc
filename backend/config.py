"""
Centralised configuration via environment variables.
All secrets come from Railway / ClickHouse Cloud env vars – never hard-coded.
"""

import os


# ── Postgres ────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/demo",
)

# Build a replication-capable DSN from DATABASE_URL.
# psycopg2 LogicalReplicationConnection needs "replication=database" in the DSN.
def _repl_dsn() -> str:
    base = DATABASE_URL
    # If it already contains replication param, use as-is
    if "replication=" in base:
        return base
    # Convert URL form → keyword form if needed, then append
    if base.startswith("postgresql://") or base.startswith("postgres://"):
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}replication=database"
    # keyword=value form
    return f"{base} replication=database"


DATABASE_REPL_URL: str = os.getenv("DATABASE_REPL_URL", _repl_dsn())

# ── ClickHouse ──────────────────────────────────────────────────────────────
CH_HOST: str = os.getenv("CH_HOST", "localhost")
CH_PORT: int = int(os.getenv("CH_PORT", "8123"))
CH_USER: str = os.getenv("CH_USER", "default")
CH_PASSWORD: str = os.getenv("CH_PASSWORD", "clickhouse")
CH_SECURE: bool = os.getenv("CH_SECURE", "false").lower() in ("1", "true", "yes")
CH_DATABASE: str = os.getenv("CH_DATABASE", "default")

# ── CDC ─────────────────────────────────────────────────────────────────────
SLOT_NAME: str = os.getenv("SLOT_NAME", "cdc_artie_slot")

# ── Server ──────────────────────────────────────────────────────────────────
PORT: int = int(os.getenv("PORT", "8000"))
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "*")
