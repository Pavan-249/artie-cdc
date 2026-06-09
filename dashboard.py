import json
import subprocess
import time

import clickhouse_connect
import pandas as pd
import psycopg2
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

import seed_data
from cdc_pipeline import CH_HOST, CH_PASSWORD, CH_PORT, CH_USER, EVENT_LOG, PG_DSN


st.set_page_config(page_title="mini-Artie CDC", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
      [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 14px 16px;
      }
      [data-testid="stMetricLabel"] p { color: #475569; font-size: 0.85rem; }
      [data-testid="stMetricValue"] { font-size: 1.65rem; }
      .stDataFrame { border: 1px solid #e5e7eb; border-radius: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)


def pg_query(sql):
    with psycopg2.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [desc[0] for desc in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=columns)


def ch_client():
    return clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)


def ch_query(sql):
    return ch_client().query_df(sql)


def read_events():
    if not EVENT_LOG.exists():
        return []
    lines = EVENT_LOG.read_text(encoding="utf-8").splitlines()
    events = []
    for line in reversed(lines):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def event_feed_df(events):
    rows = []
    for event in events[:30]:
        row = event.get("row") or {}
        rows.append(
            {
                "applied_at": str(event.get("applied_at", ""))[:19],
                "operation": event.get("operation"),
                "order_id": event.get("id"),
                "status": row.get("status"),
                "amount": row.get("amount"),
                "lag_ms": event.get("lag_ms"),
            }
        )
    return pd.DataFrame(rows)


def latest_event(events):
    return events[0] if events else None


def highlight_latest(row, latest_id):
    if latest_id is None:
        return [""] * len(row)
    try:
        row_id = int(row["id"])
        event_id = int(latest_id)
    except (TypeError, ValueError):
        return [""] * len(row)
    if row_id == event_id:
        return ["background-color: #fff7ed; font-weight: 600"] * len(row)
    return [""] * len(row)


def reset_demo():
    subprocess.run(["bash", "reset.sh"], check=False)


def safe_metric(label, value):
    st.metric(label, value)


with st.sidebar:
    st.title("Controls")
    if st.button("Add order", use_container_width=True):
        seed_data.add_demo_order()
    if st.button("Ship order", use_container_width=True):
        seed_data.ship_latest_order()
    if st.button("Delete order", use_container_width=True):
        seed_data.delete_latest_order()
    if st.button("Run full story", use_container_width=True):
        seed_data.run_story()
    st.divider()
    if st.button("Reset", use_container_width=True):
        reset_demo()

if st_autorefresh:
    st_autorefresh(interval=2000, key="cdc-refresh")
else:
    time.sleep(2)
    st.rerun()

st.title("Postgres -> ClickHouse CDC")
st.caption("Dataset: orders | Key: id | ClickHouse engine: ReplacingMergeTree")

events = read_events()
current_event = latest_event(events)
current_event_id = current_event.get("id") if current_event else None
current_event_op = current_event.get("operation") if current_event else "-"
current_lag_ms = current_event.get("lag_ms") if current_event else "-"
try:
    pg_count = int(pg_query("SELECT count(*) AS n FROM orders")["n"].iloc[0])
except Exception:
    pg_count = "down"
try:
    ch_count = int(ch_query("SELECT count(*) AS n FROM orders FINAL WHERE __artie_delete = 0")["n"].iloc[0])
except Exception:
    ch_count = "down"

changes = len(events)
avg_lag = round(sum(float(e.get("lag_ms", 0)) for e in events) / changes, 1) if changes else 0
in_sync = "yes" if pg_count == ch_count and pg_count != "down" else "no"

cols = st.columns(5)
with cols[0]:
    safe_metric("Postgres", pg_count)
with cols[1]:
    safe_metric("ClickHouse", ch_count)
with cols[2]:
    safe_metric("In sync", in_sync)
with cols[3]:
    safe_metric("Events", changes)
with cols[4]:
    safe_metric("Avg lag", f"{avg_lag} ms")

status_cols = st.columns([1, 1, 1])
with status_cols[0]:
    st.metric("Latest event", current_event_op)
with status_cols[1]:
    st.metric("Changed order", current_event_id or "-")
with status_cols[2]:
    st.metric("Latest lag", f"{current_lag_ms} ms" if current_lag_ms != "-" else "-")

st.graphviz_chart(
    """
    digraph {
      rankdir=LR;
      node [shape=box, style="rounded,filled", fillcolor="#f8fafc", color="#64748b"];
      pg [label="Postgres\\norders"];
      slot [label="WAL\\nwal2json"];
      py [label="Python\\nCDC worker"];
      ch [label="ClickHouse\\norders FINAL"];
      dash [label="Streamlit\\nlive view"];
      pg -> slot -> py -> ch -> dash;
      dash -> pg [label="actions"];
    }
    """
)

left, right = st.columns(2)
with left:
    st.subheader("Postgres source")
    try:
        pg_df = pg_query(
                """
                SELECT id, customer_name, product, amount, status, created_at
                FROM orders
                ORDER BY id
                """
            )
        st.dataframe(
            pg_df.style.apply(highlight_latest, latest_id=current_event_id, axis=1),
            use_container_width=True,
            hide_index=True,
        )
    except Exception as exc:
        st.warning(f"Postgres unavailable: {exc}")

with right:
    st.subheader("ClickHouse replica")
    try:
        ch_df = ch_query(
                """
                SELECT id, customer_name, product, amount, status, created_at, __artie_operation, __artie_updated_at
                FROM orders FINAL
                WHERE __artie_delete = 0
                ORDER BY id
                """
            )
        st.dataframe(
            ch_df.style.apply(highlight_latest, latest_id=current_event_id, axis=1),
            use_container_width=True,
            hide_index=True,
        )
    except Exception as exc:
        st.warning(f"ClickHouse unavailable: {exc}")

st.subheader("CDC events")
if events:
    feed_df = event_feed_df(events)
    st.dataframe(
        feed_df.style.apply(
            lambda row: ["background-color: #eff6ff; font-weight: 600"] * len(row) if row.name == 0 else [""] * len(row),
            axis=1,
        ),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No events yet.")
