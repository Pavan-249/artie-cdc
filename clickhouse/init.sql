CREATE TABLE IF NOT EXISTS default.orders (
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
ORDER BY id;
