# SmarTraderAI

A live NSE market terminal built with a production-style, polyglot backend. The
FastAPI service is the running core; Java, Node.js and Django are optional
sidecars. Redis, Kafka, PostgreSQL, MySQL, MongoDB, AWS S3 and Azure Blob are
lazy-loaded adapters that fail soft when not configured, so the terminal always
keeps working with real Yahoo Finance data.

There is no simulated, paper or fallback market data in the UI or behavior.

## Brand asset

`frontend/assets/smartraderai-logo.png` is the primary logo for the header, login
card, dashboard and project presentations. Palette: white `SmarTrader`, electric
blue `AI`, green/red candlesticks on black.

## What is included

- **Accounts** — register, log in and signed session tokens. Every API request and the market WebSocket require authentication.
- **Dashboard** — real index quotes, breadth, top movers and live scanner signals.
- **Markets** — Yahoo Finance OHLCV candles with EMA/Bollinger overlays, plus a backend-driven, searchable catalog of all verified NSE/BSE banks and companies, NIFTY 50 / NIFTY BANK / SENSEX. Click any symbol to load its live chart, indicators and ML read; every symbol also links to TradingView.
- **Signals** — technical strategies gated by the ML model's out-of-sample direction probability.
- **TradingView** — a dedicated INTELLIGENCE view with TradingView's advanced chart, the same 196-symbol verified catalog, quick symbol/interval switching, and an in-app full-screen chart button (`Esc` exits).
- **Positions** — explicitly empty until a real broker session is configured; no fabricated P&L.
- **AI Insights** — RandomForest model trained on live Yahoo history, with accuracy, baseline, precision and feature importance.
- **AI Market Brief** — OpenAI narrative when quota is available, otherwise a clearly labelled local summary from the same live Yahoo data, RandomForest output and ATR levels; no invented numbers or order placement.
- **Alerts & Settings** — alerts generated only from real scanned setups; no static demo notifications.
- **Live feed** — backend poller broadcasts Yahoo ticks over `/ws/market` to authenticated clients.
- **Platform status** — `GET /api/platform/status` reports the live state of every backend adapter.

Yahoo Finance NSE quotes can be delayed by roughly 15 minutes. The UI says so;
nothing is represented as tick-by-tick exchange data.

## Backend technology map

| Component | Technologies | Where they live |
| --- | --- | --- |
| Backend language | Python, Java, Node.js | FastAPI core, `services/stream-java`, `services/gateway-node` |
| Backend framework | FastAPI, Django, Spring Boot, Express.js | `main.py`, `services/admin-django`, `services/stream-java`, `services/gateway-node` |
| Database | PostgreSQL, MySQL | Optional SQLAlchemy adapter in `backend_platform/sql.py` |
| NoSQL database | MongoDB | `database/mongodb.py`, optional connection |
| Cache | Redis | `backend_platform/cache.py`, optional with in-memory fallback |
| API | REST API, WebSocket API | `api/`, `main.py` (`/ws/market`) |
| Authentication | JWT, OAuth 2.0 | `core/security.py`, `api/oauth.py` |
| Real-time processing | Kafka, Redis Streams | `backend_platform/events.py`, Java consumer in `services/stream-java` |
| Deployment | AWS, Azure, Docker | Root `Dockerfile`, `docker-compose.yml`, `deploy/aws`, `deploy/azure`, `deploy/nginx.conf` |

All optional pieces are isolated behind configuration. Missing clients,
credentials or infrastructure never break live quotes, charts, auth or ML.

## Architecture

```text
Browser / TradingView iframe
        |
        v
 Nginx (optional edge)  -----> Node/Express gateway (optional)
        |                              |
        +------------------------------+
        v
FastAPI core  --------> Redis cache / Redis Streams (optional)
   |   |   |  \--------> Kafka producer (optional)
   |   |   \-----------> SQLAlchemy -> PostgreSQL / MySQL (optional)
   |   \---------------> MongoDB (optional)
   \-------------------> AWS S3 / Azure Blob / local exports (optional)

OAuth 2.0 client credentials ---> scoped service JWTs
Browser login -----------------> user JWTs
Yahoo Finance -----------------> real quotes, candles and ML training data
WebSocket /ws/market ----------> authenticated live tick broadcast
```

## Run locally

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. You will be redirected to `/login`; create an
account once, then sign in. API docs are at <http://127.0.0.1:8000/docs>.

### Run from VS Code

1. Open this folder in VS Code (`File > Open Folder`).
2. Install the recommended **Python** and **Python Debugger** extensions when prompted.
3. Press `Ctrl+Shift+P`, run **Python: Select Interpreter**, and choose
   `.venv\Scripts\python.exe`.
4. Press `F5` and select **SmarTraderAI: FastAPI**. Uvicorn starts in the integrated terminal.
5. Open <http://127.0.0.1:8000>.

For auto-reload instead of debugging, run **Terminal > Run Task > SmarTraderAI: Run server (auto-reload)**.
Use **SmarTraderAI: Install dependencies** once if packages are missing. The
`.vscode/` configs are committed so this works on a fresh checkout.

## Run with Docker

```powershell
Copy-Item .env.example .env
# Edit .env and set JWT_SECRET and OAUTH_CLIENT_SECRET

# Core API only
docker compose up -d --build

# Core + Redis/Postgres/Mongo/Kafka infrastructure
docker compose --profile infra up -d --build

# Core + Node, Django and Spring Boot sidecars
docker compose --profile sidecars up -d --build

# Everything including Nginx on port 80
docker compose --profile infra --profile sidecars --profile edge up -d --build
```

Service URLs:

| Service | URL | Profile |
| --- | --- | --- |
| FastAPI core / UI | `http://localhost:8000` | default |
| Express gateway | `http://localhost:3000/health` | `sidecars` |
| Django admin | `http://localhost:8001/health` | `sidecars` |
| Spring Boot stream | `http://localhost:8080/health` | `sidecars` |
| Nginx edge | `http://localhost` | `edge` |

Enable only the database you need. For example, set
`DATABASE_URL=postgresql://smartraderai:smartraderai@postgres:5432/smartraderai`
for PostgreSQL, or the MySQL equivalent with `@mysql:3306/smartraderai`.

## Configuration (`.env`)

Start from `.env.example`. Important variables:

| Variable | Purpose |
| --- | --- |
| `JWT_SECRET` | Secret used to sign user and service tokens. Change it in production. |
| `WATCHLIST`, `INDICES` | Comma-separated Yahoo symbols. `TMPV.NS` replaced `TATAMOTORS.NS` after the 2025 demerger. |
| `MARKET_REFRESH_SECONDS` | WebSocket broadcast interval. |
| `MARKET_DATA_PROVIDER` | `yahoo` (default) or `fyers`. Fyers is a skeleton integration; complete `services/fyers_client.py` mapping before live use. |
| `FYERS_APP_ID`, `FYERS_SECRET_ID`, `FYERS_ACCESS_TOKEN` | Optional Fyers credentials. Keep them in `.env` only; never commit secrets. |
| `FYERS_REDIRECT_URI`, `FYERS_API_BASE` | Optional Fyers OAuth callback/base URL placeholders for the skeleton integration. |
| `DATABASE_URL` | Optional PostgreSQL/MySQL/SQLite SQLAlchemy URL. |
| `MONGO_URI` | Optional MongoDB connection. Missing or invalid values only disable persistence. |
| `REDIS_URL` | Optional Redis cache. Falls back to memory. |
| `EVENT_BUS` | `memory`, `redis` or `kafka`. Falls back to memory. |
| `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_TOPIC` | Optional Kafka producer and Java consumer settings. |
| `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_CLIENTS` | OAuth 2.0 client-credentials clients. |
| `CLOUD_STORAGE` | `local`, `s3` or `azure`. Falls back to local exports. |
| `AWS_S3_BUCKET`, `AWS_REGION` | Optional AWS S3 export target. |
| `AZURE_STORAGE_CONNECTION_STRING`, `AZURE_CONTAINER` | Optional Azure Blob export target. |
| `NODE_GATEWAY_URL`, `SPRING_STREAM_URL`, `DJANGO_ADMIN_URL` | Advertise enabled sidecars in platform status. |
| `TRADING_ENABLED` | Safety switch for future real order placement. Currently no orders are placed. |
| `OPENAI_API_KEY` | Optional: enables OpenAI text for **AI Market Brief**. Without it (or with no quota), a clearly labelled local evidence summary is used. Keep it out of Git. |
| `OPENAI_MODEL` | Optional model override; defaults to `gpt-4o-mini`. |
| `OPENAI_BRIEF_TTL_SECONDS` | Server-side cache TTL for identical briefs; defaults to 600 seconds. |

The TradingView/Markets catalog is defined in `config/symbols.py` and served by
`GET /api/market/catalog`. It is separate from the live Yahoo watchlist so the
wider universe does not slow down polling or ML training.

The local SQLite user database (`data/app.db`) and signing secret (`data/.jwt_secret`)
are ignored by Git.

## Authentication and OAuth 2.0

Browser users get a JWT from `POST /api/auth/login`. Machine clients can use
OAuth 2.0 client credentials:

```powershell
$body = @{
  grant_type = "client_credentials"
  client_id = "smartraderai"
  client_secret = "your-client-secret"
  scope = "market:read catalog:read"
}
$token = (Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/oauth/token" -Body $body).access_token

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/platform/status" -Headers @{ Authorization = "Bearer $token" }
```

Supported scopes are `market:read`, `market:stream`, `signals:read` and
`catalog:read`. A client named `admin` may also request `*`. Tokens can be
checked with `POST /api/oauth/introspect`. User sessions without explicit
scopes retain full access.

## API

Authenticated endpoints use `Authorization: Bearer <token>`:

```
POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me
POST /api/oauth/token
POST /api/oauth/introspect
GET  /api/dashboard
GET  /api/market/quote?symbol=RELIANCE.NS
GET  /api/market/candles?symbol=TCS.NS&interval=5m&limit=120
GET  /api/market/watchlist
GET  /api/market/indices
GET  /api/market/catalog
GET  /api/platform/status
GET  /api/signals
POST /api/scan
GET  /api/positions
GET  /api/trades
GET  /api/broker/status
GET  /api/strategies
GET  /api/ai/analysis?symbol=INFY.NS
GET  /api/ai/model?interval=5m
GET  /api/ai/brief/status
POST /api/ai/brief  (JSON: symbol, interval, refresh)
GET  /api/ai/targets?group=indices&offset=0&limit=16
GET  /api/alerts
GET  /api/settings
WS   /ws/market  (JWT sent as Sec-WebSocket-Protocol; legacy ?token= still accepted)
```

`GET /api/ai/targets` powers **TARGET & STOPLOSS**. It pages through the full
backend catalog (indices, NSE banks, NSE companies and BSE companies) and scores
each symbol from real Yahoo OHLCV candles: live 5m where available, real 1d with
a per-row label where 5m is unavailable. Direction is the genuine RandomForest
bias confirmed by EMA/RSI/candle momentum; target, stoploss, buy zone and R:R
come from ATR(14) on those same candles. Symbols Yahoo cannot serve at either
interval are omitted and listed as failures — no estimates are substituted.
Model accuracy, edge, training universe, caveats and Yahoo delay notes are
returned in `meta` and shown in the UI. Stale candles are forced to watch-only.

`POST /api/ai/brief` powers **AI Market Brief**. It sends a compact JSON of the
same real evidence (live Yahoo price/change/market time, RandomForest bias and
out-of-sample accuracy, EMA/RSI momentum notes, ATR-derived entry/target/stop)
to OpenAI and returns a structured research narrative with observations, risks
and conditions to re-check. The UI always shows the evidence next to the text.
If the key is missing or OpenAI returns an error such as `credit_balance_exhausted`,
the service does not fail: it builds a deterministic summary from that same evidence,
labels the card **LOCAL EVIDENCE BRIEF (LOCAL)** and exposes `meta.fallback=true`
with the reason. No prices are invented and no order is placed. Results are cached
for `OPENAI_BRIEF_TTL_SECONDS`; pass `refresh: true` to retry OpenAI after adding
credits. `GET /api/ai/brief/status` reports configuration without exposing the key.

## Cloud deployment

### AWS

`deploy/aws/ecs-task-definition.json` defines an ECS Fargate task with the
`awslogs` driver and a Secrets Manager reference for `JWT_SECRET`.

```powershell
.\deploy\aws\deploy.ps1 -Region ap-south-1 -AccountId 123456789012 `
    -Cluster smartraderai-cluster -Service smartraderai-core
```

Update the IAM role ARNs, Secrets Manager ARN and region placeholders in the
task definition before running the script.

### Azure

`deploy/azure/main.bicep` provisions a Container Apps environment, a managed
identity, the container app, health probes and an optional ACR pull role.

```powershell
$env:JWT_SECRET = "replace-with-a-long-random-secret"
.\deploy\azure\deploy.ps1 -ResourceGroup smartraderai-rg -Location centralindia
```

### Vercel

The root FastAPI app is deployed as a single Vercel project. `vercel.json` pins
the framework, and `.vercelignore` keeps optional sidecars out of the function
bundle while preserving all application source files.

Production URL: <https://smar-trade-ai-yjzl.vercel.app>

Set these in the Vercel project environment variables:

| Variable | Purpose |
| --- | --- |
| `JWT_SECRET` | Long random secret for stable user/service tokens across instances. |
| `OAUTH_CLIENT_SECRET`, `OAUTH_CLIENTS` | Optional machine-client credentials. |
| `MONGO_URI`, `DATABASE_URL` | Optional external persistence for users and ticks. |

The serverless filesystem is ephemeral: without an external database, registered
users and local SQLite history do not survive instance replacement. Live Yahoo
quotes, catalog, charts and ML remain real.

## Model details

`ai/ml_model.py` builds 13 price, volume and technical features from Yahoo OHLCV
history. Labels are the direction three candles later for moves beyond ±0.2%;
flat outcomes are excluded so the baseline is a real 50/50 coin flip. A
`RandomForestClassifier` is trained on the first 75% of each symbol's history
and evaluated only on the untouched last 25%. The result includes that baseline
so the reported edge is honest. The model is cached for 15 minutes.

Latest verified run: `out_of_sample_accuracy 54.35%`,
`baseline_accuracy 51.24%`, `edge_over_baseline +3.11%`,
`train_samples 946`, `test_samples 322`.

## Trading safety

Real order placement is not implemented. `TRADING_ENABLED=false` by default and
broker credentials alone do not place orders. Positions and trades stay empty
until an authorised broker integration is added.
