# Project Handoff

This is a local-only Postgres to ClickHouse CDC demo for a finance trade surveillance use case.

## Run Commands

```bash
scripts/start_databases.sh
python scripts/ingest_finance_data.py
python cdc_pipeline.py
streamlit run dashboard.py
```

The Streamlit dashboard runs at `http://localhost:8501`.

## Current Product Shape

The dashboard should tell this story in order:

1. Pick one clear source change.
2. Preview the SQL without executing it.
3. Run the selected SQL only when the user clicks `Run selected SQL`.
4. Show the Postgres source table and ClickHouse destination table side by side.
5. Show KPI and chart changes after CDC applies the event.

The source and destination panes are the dashboard workaround for embedding the databases. They are live read-only `SELECT` results, not external database consoles.

Keep the UI compact and professional. Avoid tutorial-style blocks, pipeline explanation cards, emojis, decorative gradients, and extra prose.

## Key Files

- `dashboard.py`: Streamlit dashboard UI and charts.
- `finance_actions.py`: The 6 mapped SQL examples behind the buttons.
- `cdc_pipeline.py`: Logical replication worker from Postgres WAL to ClickHouse.
- `data/trades_seed.csv`: Deterministic baseline dataset.
- `postgres/init.sql`: Source `trades` schema.
- `clickhouse/init.sql`: Destination `trades` schema with CDC metadata.
- `scripts/ingest_finance_data.py`: Resets both stores and loads the CSV baseline.

## Demo Actions

Keep the action count small. Current buttons:

- Add JPM trade (INSERT)
- Flag NVDA risk (UPDATE)
- Approve US10Y review (UPDATE)
- Correct MSFT price (UPDATE)
- Cancel SOFR duplicate (UPDATE)
- Delete bad credit booking (DELETE)

If adding a new action, make sure it creates an easy-to-see movement in at least one KPI or chart and update this file plus `README.md`.
