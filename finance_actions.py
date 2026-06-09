from dataclasses import dataclass
from textwrap import dedent

import psycopg2

from cdc_pipeline import PG_DSN


@dataclass(frozen=True)
class DemoAction:
    key: str
    label: str
    category: str
    description: str
    sql: str


def connect():
    return psycopg2.connect(PG_DSN)


ACTIONS = [
    DemoAction(
        "insert_equity_trade",
        "Add JPM trade (INSERT)",
        "New trade",
        "Adds a new JPM equity trade to Postgres. CDC should add the same row to ClickHouse.",
        """
        INSERT INTO trades (
          trade_id, trade_ts, account_id, client_name, desk, trader,
          symbol, asset_class, side, quantity, price, notional_usd,
          venue, risk_score, status, updated_at
        )
        VALUES (
          9001, now(), 'ACC-2044', 'Northbridge Capital', 'Equities', 'Maya Rao',
          'JPM', 'Equity', 'BUY', 10000, 198.42, 1984200.00,
          'NYSE', 38, 'BOOKED', now()
        )
        ON CONFLICT (trade_id) DO UPDATE
        SET quantity = EXCLUDED.quantity,
            price = EXCLUDED.price,
            notional_usd = EXCLUDED.notional_usd,
            risk_score = EXCLUDED.risk_score,
            status = EXCLUDED.status,
            updated_at = now();
        """,
    ),
    DemoAction(
        "flag_nvda_review",
        "Flag NVDA risk (UPDATE)",
        "Risk review",
        "Raises risk on one trade. The risk chart and exception count should move.",
        """
        UPDATE trades
        SET risk_score = LEAST(100, risk_score + 8),
            status = 'REVIEW',
            updated_at = now()
        WHERE trade_id = 1004;
        """,
    ),
    DemoAction(
        "approve_rates_review",
        "Approve US10Y review (UPDATE)",
        "Compliance",
        "Clears a review item. The exception count should decrease.",
        """
        UPDATE trades
        SET risk_score = 42,
            status = 'APPROVED',
            updated_at = now()
        WHERE trade_id = 1002;
        """,
    ),
    DemoAction(
        "correct_msft_price",
        "Correct MSFT price (UPDATE)",
        "Trade repair",
        "Applies a small price correction. The notional chart should move slightly.",
        """
        UPDATE trades
        SET price = price + 0.25,
            notional_usd = quantity * (price + 0.25),
            risk_score = 54,
            updated_at = now()
        WHERE trade_id = 1003;
        """,
    ),
    DemoAction(
        "cancel_duplicate_sofr",
        "Cancel SOFR duplicate (UPDATE)",
        "Trade repair",
        "Marks a duplicate as cancelled. Open notional and status distribution should change.",
        """
        UPDATE trades
        SET status = 'CANCELLED',
            risk_score = 20,
            updated_at = now()
        WHERE trade_id = 1009;
        """,
    ),
    DemoAction(
        "delete_erroneous_credit_trade",
        "Delete bad credit booking (DELETE)",
        "Delete",
        "Deletes an operational error. ClickHouse should receive a tombstone and hide the row.",
        """
        DELETE FROM trades
        WHERE trade_id = 1015;
        """,
    ),
]


ACTION_MAP = {action.key: action for action in ACTIONS}


def execute_action(action_key):
    action = ACTION_MAP[action_key]
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(dedent(action.sql))
    return action
