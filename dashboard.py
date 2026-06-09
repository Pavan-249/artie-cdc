import html
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from string import Template
from textwrap import dedent

import altair as alt
import clickhouse_connect
import pandas as pd
import psycopg2
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

from cdc_pipeline import CH_HOST, CH_PASSWORD, CH_PORT, CH_USER, EVENT_LOG, PG_DSN
from finance_actions import ACTIONS, ACTION_MAP, execute_action


st.set_page_config(page_title="Trade Surveillance CDC", layout="wide")

# ---------------------------------------------------------------- session state
if "theme" not in st.session_state:
    st.session_state.theme = "dark"
if "last_sql" not in st.session_state:
    st.session_state.last_sql = "-- Pick a source change to preview its SQL."
if "last_action" not in st.session_state:
    st.session_state.last_action = "No source change selected."
if "selected_action_key" not in st.session_state:
    st.session_state.selected_action_key = None

# ----------------------------------------------------------------------- themes
# Accents are shared; only the surfaces flip. The SQL block stays a dark terminal
# panel in both themes so the statement is always legible.
ACCENTS = {"cyan": "#17c9e8", "green": "#5fcf80", "pink": "#ff7da0", "amber": "#f0b429", "red": "#ff5f67"}
DARK = {
    "bg": "#070d12", "panel": "#0e1a23", "panel2": "#13222d", "line": "#244353",
    "muted": "#a4b7c2", "text": "#eef5f8", "cell_text": "#dde8ee", "hdr_bg": "#13222d",
    "feedback_bg": "#0e1a23", "hi_bg": "#15455a", "hi_text": "#ffffff",
    "btn_bg": "#102029", "btn_border": "#2a4d60", "btn_text": "#e2eef3",
    "grid": "#173039", "domain": "#2f5161",
    "run_bg": "#17c9e8", "run_bg2": "#11b2cf", "run_text": "#04161d",
    **ACCENTS,
}
LIGHT = {
    "bg": "#eef2f6", "panel": "#ffffff", "panel2": "#f4f7fa", "line": "#d4dee6",
    "muted": "#566873", "text": "#0e1c25", "cell_text": "#1a2c37", "hdr_bg": "#f0f4f8",
    "feedback_bg": "#ffffff", "hi_bg": "#cdeef5", "hi_text": "#05222b",
    "btn_bg": "#ffffff", "btn_border": "#cbd7e0", "btn_text": "#1d2d37",
    "grid": "#e3eaef", "domain": "#c3cdd5",
    "run_bg": "#0fa6c4", "run_bg2": "#0d93ad", "run_text": "#ffffff",
    "cyan": "#0c8fab", "green": "#2f9e44", "pink": "#d6336c", "amber": "#b8860b", "red": "#e03131",
}
T = DARK if st.session_state.theme == "dark" else LIGHT

CSS = Template(
    """
    <style>
      .stApp { background: $bg; color: $text; }
      header[data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer { display: none; }
      .block-container { padding: 0.45rem 1.05rem 1rem; max-width: 1680px; }
      [data-testid="stVerticalBlock"] { gap: 0.5rem; }
      [data-testid="stElementContainer"] { margin: 0 !important; }
      [data-testid="stHorizontalBlock"] { gap: 0.5rem; }
      /* Streamlit puts margin-bottom:-1rem on markdown containers to cancel a trailing
         <p> margin. Our custom HTML uses <div>s (no such margin), so that negative
         margin collapses the container and overlaps the next element. Neutralise it. */
      [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
      /* Spacing comes from the flex gap above. Custom blocks carry NO margin so they
         cannot collapse out of their containers and overlap the next element. */
      .topbar, .rule, .section, .qcap, .feedback, .kpi-grid, .sqlbox, .tbl, .phead { margin: 0; }
      .phead .qcap { margin-top: 0.12rem; }

      .topbar { display: flex; align-items: flex-end; justify-content: space-between; }
      .topbar h1 { font-size: 1.22rem; font-weight: 850; margin: 0; letter-spacing: 0.01em; color: $text; }
      .topbar-meta { color: $muted; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 0.15rem; }
      .status-pill { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: $muted; }
      .status-ok { color: $green; font-weight: 850; }
      .status-warn { color: $amber; font-weight: 850; }
      .status-bad { color: $red; font-weight: 850; }
      .rule { border: none; border-top: 1px solid $line; }

      .section { color: $muted; font-size: 0.68rem; font-weight: 850; letter-spacing: 0.05em;
                 text-transform: uppercase; }
      .qcap { color: $muted; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
              font-size: 0.6rem; opacity: 0.8; white-space: nowrap;
              overflow: hidden; text-overflow: ellipsis; }

      /* KPI strip: small, one row */
      .kpi-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 0.45rem; }
      .kpi { background: $panel; border: 1px solid $line; border-radius: 6px; padding: 0.4rem 0.6rem; }
      .kpi .label { color: $muted; font-size: 0.62rem; text-transform: uppercase; font-weight: 800; letter-spacing: 0.04em; }
      .kpi .value { color: $text; font-size: 1.05rem; font-weight: 850; line-height: 1.1; margin-top: 0.12rem; }
      .kpi.cyan .value { color: $cyan; }
      .kpi.green .value { color: $green; }
      .kpi.pink .value { color: $pink; }
      .kpi.amber .value { color: $amber; }

      /* compact action + run buttons */
      div[data-testid="stButton"] button {
        background: $btn_bg; border: 1px solid $btn_border; color: $btn_text;
        border-radius: 6px; min-height: 32px; padding: 0.3rem 0.55rem;
        font-size: 0.77rem; font-weight: 700; line-height: 1.1; transition: all 0.12s ease;
      }
      div[data-testid="stButton"] button:hover { border-color: $cyan; color: $text; }
      div[data-testid="stButton"] button[kind="primary"] {
        background: $panel2; border: 1px solid $cyan; color: $cyan; box-shadow: inset 0 0 0 1px $cyan;
      }
      .st-key-run_sql button {
        background: linear-gradient(180deg, $run_bg 0%, $run_bg2 100%) !important;
        border: 1px solid $run_bg !important; color: $run_text !important;
        font-weight: 850 !important; letter-spacing: 0.02em; box-shadow: 0 1px 6px -2px $run_bg;
      }
      .st-key-run_sql button:hover { filter: brightness(1.07); }
      .st-key-run_sql button:disabled { background: $btn_bg !important; color: $muted !important;
        border-color: $btn_border !important; box-shadow: none; opacity: 0.55; }

      .feedback { background: $feedback_bg; border: 1px solid $line; border-left: 3px solid $cyan;
        border-radius: 5px; padding: 0.35rem 0.6rem; font-size: 0.76rem; color: $text; }

      /* SQL preview: always a dark terminal panel, hand-coloured for contrast */
      .sqlbox { background: #0a1620; border: 1px solid $line; border-radius: 6px;
        padding: 0.6rem 0.8rem; overflow: auto; max-height: 200px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.84rem; line-height: 1.5; }
      .sqlbox .sql-line { color: #e6edf3; white-space: pre; }
      .sqlbox span { background: transparent !important; background-color: transparent !important; padding: 0 !important; }

      /* compact themed preview tables */
      .tbl { max-height: 220px; overflow: auto; border: 1px solid $line; border-radius: 6px; }
      .tbl table { width: 100%; border-collapse: collapse; font-size: 0.75rem; font-variant-numeric: tabular-nums; }
      .tbl thead th { position: sticky; top: 0; z-index: 1; background: $hdr_bg; color: $muted;
        text-align: left; padding: 0.34rem 0.55rem; font-size: 0.62rem; text-transform: uppercase;
        letter-spacing: 0.03em; border-bottom: 1px solid $line; white-space: nowrap; }
      .tbl tbody td { padding: 0.3rem 0.55rem; border-bottom: 1px solid $line; color: $cell_text; white-space: nowrap; }
      .tbl tbody tr:last-child td { border-bottom: none; }
      .tbl tbody tr:hover td { background: $panel2; }

      .event-row { display: grid; grid-template-columns: 54px 50px 1fr 44px; gap: 0.45rem;
        border-bottom: 1px solid $line; padding: 0.3rem 0.1rem; font-size: 0.76rem; }
      .event-row:last-child { border-bottom: none; }
      .event-op { color: $cyan; font-weight: 850; }
      .event-risk { color: $pink; font-weight: 850; text-align: right; }
      .subtle { color: $muted; font-size: 0.8rem; padding: 0.3rem 0; }

      .st-key-theme_toggle { display: flex; justify-content: flex-end; }
      .stTabs [data-baseweb="tab-list"] { gap: 0.3rem; border-bottom: 1px solid $line; }
      .stTabs [data-baseweb="tab"] { color: $muted; background: $panel; border: 1px solid $line;
        border-bottom: none; border-radius: 5px 5px 0 0; height: 30px; padding: 0 0.65rem; }
      [data-testid="stDataFrame"] { border: 1px solid $line; border-radius: 6px; overflow: hidden; }
    </style>
    """
)
st.markdown(CSS.substitute(T), unsafe_allow_html=True)


# --------------------------------------------------------------- SQL rendering
SQL_KW = {
    "SELECT", "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE", "FROM", "WHERE",
    "AND", "OR", "NOT", "NULL", "ON", "CONFLICT", "DO", "NOTHING", "AS", "ORDER", "BY",
    "GROUP", "LIMIT", "FINAL", "RETURNING", "JOIN", "LEFT", "RIGHT", "INNER", "DEFAULT",
    "IS", "IN", "EXCLUDED",
}
SQL_FN = {"now", "least", "greatest", "coalesce", "sum", "count", "avg", "min", "max"}
SQL_COLORS = {
    "kw": "#5ab8ff", "fn": "#c794f5", "str": "#7ddc8a", "num": "#f1b44c",
    "plain": "#e6edf3", "punct": "#aebcc8", "comment": "#6b7d89",
}
_TOKEN = re.compile(r"(--[^\n]*|'(?:[^']|'')*'|\d+\.?\d*|\w+|\s+|.)")


def _sql_spans(line):
    out = []
    for token in _TOKEN.findall(line):
        if not token:
            continue
        esc = html.escape(token)
        if token.startswith("--"):
            out.append(f'<span style="color:{SQL_COLORS["comment"]}">{esc}</span>')
        elif token.startswith("'"):
            out.append(f'<span style="color:{SQL_COLORS["str"]}">{esc}</span>')
        elif re.fullmatch(r"\d+\.?\d*", token):
            out.append(f'<span style="color:{SQL_COLORS["num"]}">{esc}</span>')
        elif token.upper() in SQL_KW:
            out.append(f'<span style="color:{SQL_COLORS["kw"]};font-weight:700">{esc}</span>')
        elif token.lower() in SQL_FN:
            out.append(f'<span style="color:{SQL_COLORS["fn"]}">{esc}</span>')
        elif token.isspace():
            out.append(token.replace(" ", "&nbsp;"))
        elif token.isidentifier():
            out.append(f'<span style="color:{SQL_COLORS["plain"]}">{esc}</span>')
        else:
            out.append(f'<span style="color:{SQL_COLORS["punct"]}">{esc}</span>')
    return "".join(out)


def render_sql(sql):
    # Plain div/span only: no <code>/<pre>, so Streamlit's code-block CSS (which adds
    # a light background) can never apply. One div per line preserves formatting.
    lines = "".join(f'<div class="sql-line">{_sql_spans(line)}</div>' for line in sql.split("\n"))
    st.markdown(f'<div class="sqlbox">{lines}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------- helpers
def pg_query(sql):
    with psycopg2.connect(PG_DSN) as conn:
        return pd.read_sql_query(sql, conn)


def ch_client():
    return clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)


def ch_query(sql):
    return ch_client().query_df(sql)


def read_events():
    if not EVENT_LOG.exists():
        return []
    events = []
    for line in reversed(EVENT_LOG.read_text(encoding="utf-8").splitlines()):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def fmt_money(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if abs(number) >= 1_000_000:
        return f"${number / 1_000_000:,.1f}M"
    return f"${number:,.0f}"


def fmt_number(value):
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "-"


def latest_event_id(events):
    if not events:
        return None
    return events[0].get("trade_id")


def highlight_latest(row, latest_id):
    if latest_id is None or "trade_id" not in row:
        return [""] * len(row)
    try:
        if int(row["trade_id"]) == int(latest_id):
            return [f"background-color: {T['hi_bg']}; color: {T['hi_text']}; font-weight: 700"] * len(row)
    except (TypeError, ValueError):
        pass
    return [""] * len(row)


def live_source_df():
    return pg_query(
        """
        SELECT trade_id, trade_ts, account_id, client_name, desk, trader,
               symbol, asset_class, side, quantity, price, notional_usd,
               venue, risk_score, status, updated_at
        FROM trades
        ORDER BY trade_id
        """
    )


def live_replica_df():
    return ch_query(
        """
        SELECT trade_id, trade_ts, account_id, client_name, desk, trader,
               symbol, asset_class, side, quantity, price, notional_usd,
               venue, risk_score, status, updated_at, __cdc_operation, __cdc_updated_at
        FROM trades FINAL
        WHERE __cdc_is_deleted = 0
        ORDER BY trade_id
        """
    )


def metrics(df):
    if df.empty:
        return {"rows": 0, "notional": 0, "exceptions": 0, "high_risk": 0, "avg_risk": 0, "blocked": 0}
    open_df = df[df["status"] != "CANCELLED"]
    return {
        "rows": len(df),
        "notional": open_df["notional_usd"].astype(float).sum(),
        "exceptions": len(df[df["status"].isin(["REVIEW", "BLOCKED"])]),
        "high_risk": len(df[df["risk_score"].astype(int) >= 80]),
        "avg_risk": round(df["risk_score"].astype(float).mean(), 1),
        "blocked": len(df[df["status"] == "BLOCKED"]),
    }


def event_feed_df(events):
    rows = []
    for event in events[:50]:
        row = event.get("row") or {}
        rows.append(
            {
                "applied_at": str(event.get("applied_at", ""))[:19],
                "operation": event.get("operation"),
                "trade_id": event.get("trade_id"),
                "symbol": row.get("symbol"),
                "desk": row.get("desk"),
                "status": row.get("status"),
                "risk_score": row.get("risk_score"),
                "notional_usd": row.get("notional_usd"),
                "lag_ms": event.get("lag_ms"),
            }
        )
    return pd.DataFrame(rows)


def run_reset():
    subprocess.run([sys.executable, "scripts/ingest_finance_data.py"], check=False)


def style_chart(chart):
    return (
        chart.configure(background="transparent")
        .configure_view(stroke=None, fill=None)
        .configure_axis(
            labelColor=T["muted"], titleColor=T["muted"], gridColor=T["grid"],
            domainColor=T["domain"], tickColor=T["domain"],
        )
        .configure_legend(labelColor=T["muted"], titleColor=T["muted"])
    )


def panel_head(title, query=None):
    cap = f'<div class="qcap">{query}</div>' if query else ""
    st.markdown(f'<div class="phead"><div class="section">{title}</div>{cap}</div>', unsafe_allow_html=True)


def render_kpis(items):
    cards = "".join(
        f'<div class="kpi {tone}"><div class="label">{label}</div><div class="value">{value}</div></div>'
        for label, value, tone in items
    )
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)


def render_events(events):
    if not events:
        st.markdown('<div class="subtle">No CDC events yet.</div>', unsafe_allow_html=True)
        return
    rows = []
    for event in events[:9]:
        row = event.get("row") or {}
        rows.append(
            f'<div class="event-row"><div class="event-op">{event.get("operation", "-")}</div>'
            f'<div>{event.get("trade_id", "-")}</div>'
            f'<div>{row.get("symbol", "-")} {row.get("status", "-")}</div>'
            f'<div class="event-risk">{row.get("risk_score", "-")}</div></div>'
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


def source_preview(df):
    if df.empty:
        return df
    columns = ["trade_id", "symbol", "desk", "status", "risk_score", "notional_usd", "updated_at"]
    return df.sort_values("updated_at", ascending=False)[columns]


def replica_preview(df):
    if df.empty:
        return df
    columns = ["trade_id", "symbol", "desk", "status", "risk_score", "notional_usd", "__cdc_operation", "__cdc_updated_at"]
    return df.sort_values("__cdc_updated_at", ascending=False)[columns]


def render_table(df, latest_id):
    """Compact, theme-aware HTML table that scrolls internally."""
    if df.empty:
        st.markdown('<div class="subtle">No rows.</div>', unsafe_allow_html=True)
        return
    df = df.copy()
    for col in ("updated_at", "__cdc_updated_at"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col]).dt.strftime("%Y-%m-%d %H:%M:%S")
    fmt = {}
    if "notional_usd" in df.columns:
        fmt["notional_usd"] = lambda v: f"{float(v):,.0f}"
    if "risk_score" in df.columns:
        fmt["risk_score"] = lambda v: f"{int(v)}"
    styler = (
        df.style.hide(axis="index")
        .format(fmt)
        .apply(highlight_latest, latest_id=latest_id, axis=1)
    )
    st.markdown(f'<div class="tbl">{styler.to_html()}</div>', unsafe_allow_html=True)


def selected_action():
    if not st.session_state.selected_action_key:
        return None
    return ACTION_MAP.get(st.session_state.selected_action_key)


# ------------------------------------------------------------------ data + sync
if st_autorefresh:
    st_autorefresh(interval=2500, key="cdc-refresh")
else:
    time.sleep(2)
    st.rerun()

events = read_events()
latest_id = latest_event_id(events)
latest_lag = events[0].get("lag_ms") if events else None

source_error = replica_error = None
try:
    source_df = live_source_df()
except Exception as exc:
    source_error, source_df = exc, pd.DataFrame()
try:
    replica_df = live_replica_df()
except Exception as exc:
    replica_error, replica_df = exc, pd.DataFrame()

source_metrics = metrics(source_df)
replica_metrics = metrics(replica_df)
sync_delta = source_metrics["rows"] - replica_metrics["rows"]
if source_error or replica_error:
    sync_status, status_class = "Unavailable", "status-bad"
elif sync_delta == 0:
    sync_status, status_class = "In sync", "status-ok"
else:
    sync_status, status_class = "Lagging", "status-warn"

# --------------------------------------------------------------------- header
head_col, toggle_col = st.columns([7, 1.1], gap="small")
with head_col:
    st.markdown(
        f"""
        <div class="topbar">
          <div>
            <h1>TRADE SURVEILLANCE</h1>
            <div class="topbar-meta">Postgres &rarr; ClickHouse CDC &nbsp;|&nbsp; {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC</div>
          </div>
          <div class="status-pill">
            STATUS <span class="{status_class}">{sync_status}</span> &nbsp;|&nbsp; DELTA {sync_delta}
            &nbsp;|&nbsp; LAG {latest_lag if latest_lag is not None else "-"} MS
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with toggle_col:
    light_on = st.toggle("Light mode", value=(st.session_state.theme == "light"), key="theme_toggle")
    if light_on != (st.session_state.theme == "light"):
        st.session_state.theme = "light" if light_on else "dark"
        st.rerun()

st.markdown('<hr class="rule" />', unsafe_allow_html=True)

# ----------------------------------------------------- controls + SQL preview
ctrl_col, sql_col = st.columns([1.5, 1.05], gap="medium")
with ctrl_col:
    st.markdown('<div class="section">Pick one source change</div>', unsafe_allow_html=True)
    for row_start in range(0, len(ACTIONS), 2):
        btn_cols = st.columns(2, gap="small")
        for col, action in zip(btn_cols, ACTIONS[row_start : row_start + 2]):
            with col:
                is_selected = st.session_state.selected_action_key == action.key
                if st.button(
                    action.label,
                    use_container_width=True,
                    help=action.description,
                    type="primary" if is_selected else "secondary",
                    key=f"act_{action.key}",
                ):
                    st.session_state.selected_action_key = action.key
                    st.session_state.last_action = f"Selected: {action.description}"
                    st.session_state.last_sql = dedent(action.sql).strip()
                    st.rerun()

    selected = selected_action()
    run_col, reset_col = st.columns([1.4, 1], gap="small")
    with run_col:
        if st.button("Run selected SQL", use_container_width=True, disabled=selected is None, key="run_sql"):
            try:
                executed = execute_action(selected.key)
                st.session_state.last_action = f"Executed: {executed.description}"
                st.session_state.last_sql = dedent(executed.sql).strip()
            except Exception as exc:
                st.session_state.last_action = f"Execution failed: {exc}"
    with reset_col:
        if st.button("Reload baseline", use_container_width=True, key="reload_baseline"):
            try:
                run_reset()
                st.session_state.last_action = "Baseline dataset reloaded."
            except Exception as exc:
                st.session_state.last_action = f"Baseline reload failed: {exc}"
            st.session_state.last_sql = "-- python scripts/ingest_finance_data.py"
    st.markdown(f'<div class="feedback">{st.session_state.last_action}</div>', unsafe_allow_html=True)

with sql_col:
    st.markdown('<div class="section">SQL preview (runs only when you click Run)</div>', unsafe_allow_html=True)
    render_sql(st.session_state.last_sql)

# ----------------------------------------------------------------------- KPIs
render_kpis(
    [
        ("Source rows", "-" if source_error else fmt_number(source_metrics["rows"]), "cyan"),
        ("Replica rows", "-" if replica_error else fmt_number(replica_metrics["rows"]), "green"),
        ("Open notional", "-" if replica_error else fmt_money(replica_metrics["notional"]), "cyan"),
        ("Exceptions", "-" if replica_error else fmt_number(replica_metrics["exceptions"]), "pink"),
        ("High risk (>=80)", "-" if replica_error else fmt_number(replica_metrics["high_risk"]), "amber"),
        ("Avg risk", "-" if replica_error else replica_metrics["avg_risk"], "green"),
    ]
)

# ------------------------------------------------------- side-by-side tables
# The query captions show these panes are live read-only SELECTs (not edits).
source_col, replica_col = st.columns(2, gap="small")
with source_col:
    panel_head("Source: Postgres trades", "SELECT trade_id, symbol, desk, status, risk_score, notional_usd, updated_at FROM trades")
    if source_error:
        st.warning(f"Postgres unavailable: {source_error}")
    else:
        render_table(source_preview(source_df), latest_id)
with replica_col:
    panel_head("Destination: ClickHouse trades (FINAL)", "SELECT trade_id, symbol, desk, status, risk_score, notional_usd, __cdc_operation, __cdc_updated_at FROM trades FINAL")
    if replica_error:
        st.warning(f"ClickHouse unavailable: {replica_error}")
    else:
        render_table(replica_preview(replica_df), latest_id)

# ----------------------------------------------- impact charts (above the fold)
chart_a, chart_b = st.columns(2, gap="small")
with chart_a:
    panel_head("Notional by desk", "SELECT desk, sum(notional_usd) FROM trades FINAL GROUP BY desk")
    if replica_df.empty:
        st.markdown('<div class="subtle">No replica data.</div>', unsafe_allow_html=True)
    else:
        desk_chart = (
            replica_df[replica_df["status"] != "CANCELLED"]
            .assign(notional_usd=lambda d: d["notional_usd"].astype(float))
            .groupby("desk", as_index=False)["notional_usd"].sum()
            .sort_values("notional_usd", ascending=False)
        )
        chart = (
            alt.Chart(desk_chart)
            .mark_bar(color=T["cyan"], cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("desk:N", title=None, sort="-y"),
                y=alt.Y("notional_usd:Q", title=None),
                tooltip=["desk", alt.Tooltip("notional_usd:Q", format="$,.0f")],
            )
            .properties(height=168)
        )
        st.altair_chart(style_chart(chart), use_container_width=True)
with chart_b:
    panel_head("Average risk by desk", "SELECT desk, avg(risk_score) FROM trades FINAL GROUP BY desk")
    if replica_df.empty:
        st.markdown('<div class="subtle">No replica data.</div>', unsafe_allow_html=True)
    else:
        risk_chart = (
            replica_df.assign(risk_score=lambda d: d["risk_score"].astype(float))
            .groupby("desk", as_index=False)["risk_score"].mean()
            .sort_values("risk_score", ascending=False)
        )
        chart = (
            alt.Chart(risk_chart)
            .mark_bar(color=T["pink"], cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("desk:N", title=None, sort="-y"),
                y=alt.Y("risk_score:Q", title=None, scale=alt.Scale(domain=[0, 100])),
                tooltip=["desk", alt.Tooltip("risk_score:Q", format=".1f")],
            )
            .properties(height=168)
        )
        st.altair_chart(style_chart(chart), use_container_width=True)

# ------------------------------------------------------------- detail section
st.markdown('<hr class="rule" />', unsafe_allow_html=True)
tabs = st.tabs(["Analytics", "CDC events", "Full ClickHouse", "Full Postgres", "Exceptions"])

with tabs[0]:
    a_col, b_col, e_col = st.columns([1, 1, 1.1], gap="small")
    with a_col:
        st.markdown('<div class="section">Status distribution</div>', unsafe_allow_html=True)
        if replica_df.empty:
            st.markdown('<div class="subtle">No status data.</div>', unsafe_allow_html=True)
        else:
            status_chart = replica_df.groupby("status", as_index=False).size().rename(columns={"size": "trades"})
            chart = (
                alt.Chart(status_chart)
                .mark_bar(color=T["green"], cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                .encode(x=alt.X("status:N", title=None), y=alt.Y("trades:Q", title=None), tooltip=["status", "trades"])
                .properties(height=200)
            )
            st.altair_chart(style_chart(chart), use_container_width=True)
    with b_col:
        st.markdown('<div class="section">Notional by asset class</div>', unsafe_allow_html=True)
        if replica_df.empty:
            st.markdown('<div class="subtle">No asset data.</div>', unsafe_allow_html=True)
        else:
            asset_chart = (
                replica_df[replica_df["status"] != "CANCELLED"]
                .assign(notional_usd=lambda d: d["notional_usd"].astype(float))
                .groupby("asset_class", as_index=False)["notional_usd"].sum()
                .sort_values("notional_usd", ascending=False)
            )
            chart = (
                alt.Chart(asset_chart)
                .mark_bar(color=T["amber"], cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                .encode(
                    x=alt.X("asset_class:N", title=None, sort="-y"),
                    y=alt.Y("notional_usd:Q", title=None),
                    tooltip=["asset_class", alt.Tooltip("notional_usd:Q", format="$,.0f")],
                )
                .properties(height=200)
            )
            st.altair_chart(style_chart(chart), use_container_width=True)
    with e_col:
        st.markdown('<div class="section">Latest CDC events</div>', unsafe_allow_html=True)
        render_events(events)

with tabs[1]:
    if events:
        st.dataframe(event_feed_df(events), use_container_width=True, hide_index=True, height=260)
    else:
        st.info("No CDC events yet.")

with tabs[2]:
    if replica_error:
        st.warning(f"ClickHouse unavailable: {replica_error}")
    else:
        st.dataframe(
            replica_df.style.apply(highlight_latest, latest_id=latest_id, axis=1),
            use_container_width=True, hide_index=True, height=300,
        )

with tabs[3]:
    if source_error:
        st.warning(f"Postgres unavailable: {source_error}")
    else:
        st.dataframe(
            source_df.style.apply(highlight_latest, latest_id=latest_id, axis=1),
            use_container_width=True, hide_index=True, height=300,
        )

with tabs[4]:
    if replica_df.empty:
        st.info("No exception data available.")
    else:
        exceptions_df = replica_df[replica_df["status"].isin(["REVIEW", "BLOCKED"])].sort_values(
            ["risk_score", "notional_usd"], ascending=[False, False]
        )
        st.dataframe(exceptions_df, use_container_width=True, hide_index=True, height=300)
