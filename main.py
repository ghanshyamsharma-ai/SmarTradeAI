import asyncio
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.auth import router as auth_router
from api.oauth import router as oauth_router
from api.profile import router as profile_router
from api.routes import router as api_router
from backend_platform import cache as platform_cache
from backend_platform import events as platform_events
from backend_platform import sql as platform_sql
from backend_platform import storage as platform_storage
from config.settings import settings
from core.logger import logger
from core.security import decode_token
from database.mongodb import close_mongodb_connection, connect_to_mongodb
from database.profile import init_profile_db
from database.users import init_db
from services.market_data import get_feed
from services.signal_engine import seed_if_empty
from services.yahoo_client import yahoo

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Live market terminal with machine-learning signals and account auth.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(oauth_router)
app.include_router(profile_router)
app.include_router(api_router)

connections: set[WebSocket] = set()
_broadcaster_task: asyncio.Task | None = None


async def _broadcast_ticks() -> None:
    while True:
        try:
            indices, watchlist = await get_feed()
            payload = {
                "type": "ticks",
                "indices": indices,
                "watchlist": watchlist,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            }

            # Optional platform adapters: cache, event stream, SQL history.
            cache_backend = await platform_cache.get_cache()
            await cache_backend.set(
                "market:latest", payload, ttl=max(30, settings.MARKET_REFRESH_SECONDS * 2)
            )
            await platform_events.publish("market.ticks", payload)
            for quote in watchlist:
                await platform_sql.store_tick(
                    quote["symbol"], quote["price"], quote["change_pct"], quote["market_time"]
                )

            stale = []
            for ws in list(connections):
                try:
                    await ws.send_json(payload)
                except Exception:
                    stale.append(ws)
            for ws in stale:
                connections.discard(ws)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"Market broadcast failed: {exc}")
        await asyncio.sleep(settings.MARKET_REFRESH_SECONDS)


@app.on_event("startup")
async def startup() -> None:
    global _broadcaster_task
    init_db()
    init_profile_db()
    for label, initializer in (
        ("MongoDB", connect_to_mongodb),
        ("Redis cache", platform_cache.get_cache),
        ("Event bus", platform_events.get_bus),
        ("SQL database", platform_sql.init_sql),
        ("Object storage", platform_storage.get_storage),
    ):
        try:
            await initializer()
        except Exception as exc:
            logger.warning(f"{label} adapter unavailable: {exc}")
    _broadcaster_task = asyncio.create_task(_broadcast_ticks())
    asyncio.create_task(seed_if_empty())


@app.on_event("shutdown")
async def shutdown() -> None:
    if _broadcaster_task:
        _broadcaster_task.cancel()
    await yahoo.close()
    await close_mongodb_connection()
    await platform_cache.close_cache()
    await platform_events.close_bus()
    await platform_storage.close_storage()
    await platform_sql.close_sql()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.websocket("/ws/market")
async def market_socket(websocket: WebSocket, token: str = Query(default="")) -> None:
    # Preferred: send the JWT as a Sec-WebSocket-Protocol token so it never
    # appears in URLs or access logs. Query token remains for older clients.
    protocol = websocket.headers.get("sec-websocket-protocol", "").split(",")[0].strip()
    auth_token = protocol or token
    try:
        decode_token(auth_token)
    except Exception:
        await websocket.close(code=1008, reason="Unauthorized")
        return
    await websocket.accept(subprotocol=protocol if protocol else None)
    connections.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connections.discard(websocket)


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/login")
    async def login_page():
        return FileResponse(FRONTEND_DIR / "login.html")
