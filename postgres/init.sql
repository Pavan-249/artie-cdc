CREATE TABLE IF NOT EXISTS orders (
  id BIGSERIAL PRIMARY KEY,
  customer_name TEXT NOT NULL,
  product TEXT NOT NULL,
  amount NUMERIC(12, 2) NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE orders REPLICA IDENTITY FULL;

INSERT INTO orders (customer_name, product, amount, status, created_at)
VALUES
  ('Ada Lovelace', 'Keyboard', 149.99, 'paid', now() - interval '12 minutes'),
  ('Grace Hopper', 'Monitor', 329.50, 'shipped', now() - interval '9 minutes'),
  ('Katherine Johnson', 'Desk lamp', 41.25, 'pending', now() - interval '6 minutes'),
  ('Margaret Hamilton', 'Dock', 119.00, 'paid', now() - interval '3 minutes')
ON CONFLICT DO NOTHING;
