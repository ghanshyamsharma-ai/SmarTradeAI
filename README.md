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
GET  /api/alerts
GET  /api/settings
WS   /ws/market  (JWT sent as Sec-WebSocket-Protocol; legacy ?token= still accepted)
```

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
