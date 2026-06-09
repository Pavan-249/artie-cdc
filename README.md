# CDC Pipeline Demo — Postgres → ClickHouse

A real-time Change Data Capture (CDC) pipeline that replicates data from Postgres to ClickHouse using logical replication (WAL + wal2json). No mocks, no replays — real CDC.

## Architecture

```
┌─────────────────────┐       ┌────────────────────────────────────┐
│   Vercel            │       │   Railway                          │
│                     │       │                                    │
│   Next.js Frontend  │◄─────►│   FastAPI Backend                  │
│   (Tailwind CSS)    │  API  │     ├── REST endpoints             │
│                     │       │     ├── SSE /events/stream          │
│                     │       │     └── CDC Worker (background)    │
└─────────────────────┘       │                                    │
                              │   Railway Postgres                 │
                              │     └── wal_level=logical          │
                              └───────────┬────────────────────────┘
                              ┌───────────┴───────────┐
                              │   ClickHouse Cloud     │
                              └───────────────────────┘
```

## Quick Start (Local Docker)

The original local demo still works with Docker Compose:

```bash
docker compose up -d
pip install -r requirements.txt
python cdc_pipeline.py &
streamlit run dashboard.py
```

---

## Hosted MVP Deployment

### Prerequisites

- [Railway](https://railway.app) account
- [Vercel](https://vercel.com) account
- [ClickHouse Cloud](https://clickhouse.com/cloud) account (free tier works)

---

### 1. ClickHouse Cloud Setup

1. Sign up at [clickhouse.com/cloud](https://clickhouse.com/cloud)
2. Create a new service (free tier is fine)
3. Note your connection details:
   - **Host**: e.g., `abc123.us-east-1.aws.clickhouse.cloud`
   - **Port**: `8443` (HTTPS)
   - **User**: `default`
   - **Password**: (the one you set)
4. The backend will automatically create the `orders` table on first startup

---

### 2. Railway Backend Setup

1. **Create a new project** on [Railway](https://railway.app)

2. **Add a Postgres addon**:
   - Click "New" → "Database" → "Postgres"
   - Railway provisions a managed Postgres instance

3. **Enable logical replication** on Railway Postgres:
   ```sql
   -- Connect via Railway's psql or Data tab
   ALTER SYSTEM SET wal_level = 'logical';
   ALTER SYSTEM SET max_wal_senders = '4';
   ALTER SYSTEM SET max_replication_slots = '4';
   ```
   Then **restart** the Postgres service from Railway dashboard.

   > **Note**: Verify with `SHOW wal_level;` — it must return `logical`.

4. **Deploy the backend**:
   - Click "New" → "GitHub Repo" (or deploy from CLI)
   - Set the **root directory** to `backend/`
   - Or use Railway CLI:
     ```bash
     cd backend
     railway link
     railway up
     ```

5. **Set environment variables** on the backend service:
   ```
   DATABASE_URL=<Railway Postgres connection string>
   CH_HOST=<your ClickHouse Cloud host>
   CH_PORT=8443
   CH_USER=default
   CH_PASSWORD=<your ClickHouse password>
   CH_SECURE=true
   CH_DATABASE=default
   SLOT_NAME=cdc_artie_slot
   FRONTEND_URL=https://your-app.vercel.app
   ```

   > Railway auto-injects `DATABASE_URL` if you link the Postgres addon to the backend service. You can reference it as `${{Postgres.DATABASE_URL}}`.

6. **Verify**: Visit `https://your-backend.railway.app/health`

---

### 3. Vercel Frontend Setup

1. **Import the repo** on [Vercel](https://vercel.com/new)

2. **Configure**:
   - Set **Root Directory** to `frontend/`
   - Framework Preset: **Next.js** (auto-detected)

3. **Set environment variables**:
   ```
   NEXT_PUBLIC_API_URL=https://your-backend.railway.app
   ```

4. **Deploy** — Vercel will build and deploy automatically

5. **Verify**: Visit your Vercel URL — the dashboard should load

---

### 4. Post-Deployment

1. Open the dashboard on Vercel
2. Click **"Reset Demo"** to seed initial data and start the CDC pipeline
3. Click **"Insert Order"** — watch the row appear in Postgres, then replicate to ClickHouse
4. Click **"Update Order"** — see the change propagate
5. Click **"Delete Order"** — verify removal from both views
6. Watch the **Live Change Feed** and **SQL Fired** panels update in real-time

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check with DB connectivity |
| `GET` | `/metrics` | KPI metrics (events, latency, sync status) |
| `GET` | `/orders/source` | Postgres orders table |
| `GET` | `/orders/clickhouse` | ClickHouse orders table |
| `POST` | `/orders/insert` | Insert order into Postgres |
| `POST` | `/orders/update` | Update order in Postgres |
| `POST` | `/orders/delete` | Delete order from Postgres |
| `POST` | `/reset` | Reset demo (truncate + reseed + restart CDC) |
| `GET` | `/events/stream` | SSE stream of CDC events |

## CDC Event Shape

```json
{
  "op": "INSERT",
  "table": "orders",
  "pk": 123,
  "before": {},
  "after": { "id": 123, "customer_name": "Ada Lovelace", ... },
  "diff": {},
  "commit_ts": "2026-06-08T21:48:53.635733+00:00",
  "apply_ts": "2026-06-08T21:48:53.638910+00:00",
  "lag_ms": 3.177,
  "sql_fired": "INSERT INTO orders (...) VALUES (...)"
}
```

## Project Structure

```
cdc-artie-demo/
├── backend/              # FastAPI + CDC worker (Railway)
│   ├── main.py           # FastAPI app with all endpoints
│   ├── cdc_worker.py     # Real CDC worker (WAL → ClickHouse)
│   ├── db.py             # Database connection helpers
│   ├── config.py         # Environment-based configuration
│   ├── Dockerfile        # Railway deployment
│   ├── railway.toml      # Railway config
│   └── requirements.txt
├── frontend/             # Next.js dashboard (Vercel)
│   ├── src/
│   │   ├── app/          # Next.js App Router
│   │   ├── components/   # Dashboard components
│   │   └── lib/          # API client + types
│   └── .env.example
├── docker-compose.yml    # Local Docker demo (unchanged)
├── cdc_pipeline.py       # Local CDC worker (unchanged)
├── dashboard.py          # Local Streamlit dashboard (unchanged)
└── README.md
```

## Important Notes

- **No mocks or replays** — all CDC is real Postgres logical replication
- **Actions write to Postgres only** — the CDC worker picks up changes from WAL and applies them to ClickHouse
- **SSE for real-time updates** — the dashboard receives events as they happen
- **Existing local demo is untouched** — all hosted code lives in `backend/` and `frontend/`
