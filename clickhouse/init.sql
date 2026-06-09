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
ORDER BY trade_id;
