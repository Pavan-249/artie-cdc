from decimal import Decimal

import psycopg2

from cdc_pipeline import PG_DSN


DEMO_CUSTOMER = "Demo Buyer"
DEMO_PRODUCT = "Mechanical Keyboard"
DEMO_AMOUNT = Decimal("149.99")


def connect():
    return psycopg2.connect(PG_DSN)


def add_demo_order():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO orders (customer_name, product, amount, status)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (
                    DEMO_CUSTOMER,
                    DEMO_PRODUCT,
                    DEMO_AMOUNT,
                    "pending",
                ),
            )
            return cur.fetchone()[0]


def latest_order_id(cur):
    cur.execute("SELECT id FROM orders ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    return row[0] if row else None


def ship_latest_order():
    with connect() as conn:
        with conn.cursor() as cur:
            order_id = latest_order_id(cur)
            if order_id is None:
                order_id = add_demo_order()
            cur.execute(
                """
                UPDATE orders
                SET status = 'shipped',
                    amount = %s
                WHERE id = %s
                """,
                (DEMO_AMOUNT + Decimal("10.00"), order_id),
            )
            return order_id


def delete_latest_order():
    with connect() as conn:
        with conn.cursor() as cur:
            order_id = latest_order_id(cur)
            if order_id is None:
                return None
            cur.execute("DELETE FROM orders WHERE id = %s", (order_id,))
            return order_id


def run_story():
    order_id = add_demo_order()
    ship_latest_order()
    delete_latest_order()
    return order_id


new_order = add_demo_order
update_order = ship_latest_order
delete_order = delete_latest_order


if __name__ == "__main__":
    run_story()
    print("Ran add -> ship -> delete demo story")
