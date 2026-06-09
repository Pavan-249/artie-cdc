CREATE TABLE IF NOT EXISTS trades (
  trade_id BIGINT PRIMARY KEY,
  trade_ts TIMESTAMPTZ NOT NULL,
  account_id TEXT NOT NULL,
  client_name TEXT NOT NULL,
  desk TEXT NOT NULL,
  trader TEXT NOT NULL,
  symbol TEXT NOT NULL,
  asset_class TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
  quantity NUMERIC(18, 4) NOT NULL,
  price NUMERIC(18, 4) NOT NULL,
  notional_usd NUMERIC(18, 2) NOT NULL,
  venue TEXT NOT NULL,
  risk_score INTEGER NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
  status TEXT NOT NULL CHECK (status IN ('BOOKED', 'REVIEW', 'APPROVED', 'BLOCKED', 'CANCELLED')),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE trades REPLICA IDENTITY FULL;
