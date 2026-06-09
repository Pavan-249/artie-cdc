# Building a Local Finance CDC Demo

## Working Title

From trade booking to analytics in seconds: a local Postgres to ClickHouse CDC demo

## Thesis

A serious CDC demo does not need hosted infrastructure. A local stack can still show the core production pattern: trades are booked in Postgres, streamed from the write-ahead log, materialized into ClickHouse, and monitored through a control-room dashboard.

## Outline

1. Why finance operations care about low-latency replication.
2. The use case: trade surveillance for booked, reviewed, blocked, cancelled, and corrected trades.
3. The local architecture: Postgres, logical WAL, wal2json, Python worker, ClickHouse, Streamlit.
4. The reproducible dataset: deterministic institutional trade records with desk, trader, symbol, notional, risk score, and status.
5. The demo scenarios: add a trade, flag risk, approve review, correct price, cancel duplicate, and delete an erroneous booking.
6. How ClickHouse stores the latest analytical state with `ReplacingMergeTree`.
7. What a production implementation would add: schema governance, retries, dead letter handling, access controls, lineage, and alerting.

## Draft

This project is a local finance CDC demo that moves trade events from Postgres into ClickHouse. It uses Postgres logical replication with `wal2json`, a Python CDC worker, and a Streamlit dashboard that behaves like a small trade surveillance control room.

The dataset is deterministic so the experiment is easy to reproduce. The baseline contains institutional trades across equities, rates, credit, FX, and ETFs. Each trade includes operational fields such as desk, trader, venue, notional, risk score, and status. The dashboard scenarios execute mapped SQL statements against Postgres, then the worker streams those changes into ClickHouse.

The key idea is that the dashboard does not write to ClickHouse. It changes only the source system. ClickHouse updates only after the CDC worker reads the Postgres WAL and inserts a new row version. That makes the demo useful for explaining both correctness and latency.

The dashboard tracks source row count, replica row count, open notional, exceptions, high-risk trades, average risk score, source rows, destination rows, notional by desk, trade status distribution, recent CDC events, and the exact SQL selected for each scenario. Scenario selection previews SQL first; execution happens only after the user clicks `Run selected SQL`.

This is still a local project, not a production platform. A production version would need stricter schema management, replay controls, observability, access controls, and operational runbooks. The local version keeps the moving parts visible and makes the CDC mechanics easy to inspect.
