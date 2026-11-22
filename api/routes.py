"""Authenticated REST API for the live trading terminal."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ai.analyzer import analyze
from ai.ml_model import ml
from backend_platform.status import platform_status
from config.settings import settings
from config.symbols import market_catalog
from core.logger import logger
from core.security import get_current_user, require_scope
from data.store import store
from services.market_data import (
    get_candles, get_feed, get_indices, get_quote, get_top_movers,
    get_watchlist, market_breadth,
)
from services.portfolio import broker_status, get_positions, get_trades
from services.signal_engine import scan
from services.target_planner import build_targets

router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])


def _guard(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


@router.get("/dashboard")
async def dashboard() -> Dict[str, Any]:
    try:
        indices, watchlist = await get_feed()
    except Exception as exc:
        raise _guard(exc) from exc
    signals = store.get_signals()
    try:
        model = ml.status(await ml.bundle("5m"))
    except Exception as exc:
        logger.warning(f"Model status unavailable: {exc}")
        model = {"out_of_sample_accuracy": None}
    return {
        "indices": indices,
        "breadth": market_breadth(watchlist),
        "top_movers": get_top_movers(watchlist, 5),
        "gainers": sorted(watchlist, key=lambda q: q["change_pct"], reverse=True)[:5],
        "losers": sorted(watchlist, key=lambda q: q["change_pct"])[:5],
        "stats": {
            "active_signals": len(signals),
            "watchlist_size": len(watchlist),
            "model_accuracy": model.get("out_of_sample_accuracy"),
            "last_scan": store.last_scan,
        },
        "signals": signals[:5],
        "market_time": max((q["market_time"] for q in indices + watchlist), default=""),
        "source": "Yahoo Finance",
    }


@router.get("/market/quote")
async def quote(symbol: str = Query(default="RELIANCE")) -> Dict[str, Any]:
    try:
        return await get_quote(symbol)
    except Exception as exc:
        raise _guard(exc) from exc


@router.get("/market/candles")
async def candles(
    symbol: str = Query(default="RELIANCE"),
    interval: str = Query(default="5m"),
    limit: int = Query(default=120, ge=20, le=500),
) -> Dict[str, Any]:
    try:
        return await get_candles(symbol, interval, limit)
    except Exception as exc:
        raise _guard(exc) from exc


@router.get("/market/watchlist")
async def watchlist() -> Dict[str, Any]:
    try:
        return {"watchlist": await get_watchlist()}
    except Exception as exc:
        raise _guard(exc) from exc


@router.get("/market/indices")
async def indices() -> Dict[str, Any]:
    try:
        return {"indices": await get_indices()}
    except Exception as exc:
        raise _guard(exc) from exc


@router.get("/market/catalog", dependencies=[Depends(require_scope("catalog:read"))])
async def catalog() -> Dict[str, Any]:
    return market_catalog()


@router.get("/platform/status", dependencies=[Depends(require_scope("market:read"))])
async def platform() -> Dict[str, Any]:
    return platform_status()


@router.get("/signals")
async def signals() -> Dict[str, Any]:
    return {"signals": store.get_signals(), "last_scan": store.last_scan}


@router.post("/scan")
async def run_scan(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    try:
        return await scan(symbols)
    except Exception as exc:
        raise _guard(exc) from exc


@router.get("/positions")
async def positions() -> Dict[str, Any]:
    return await get_positions()


@router.get("/trades")
async def trades() -> Dict[str, Any]:
    return await get_trades()


@router.get("/broker/status")
async def broker() -> Dict[str, Any]:
    return broker_status()


@router.get("/strategies")
async def strategies() -> Dict[str, Any]:
    return {"strategies": store.get_strategies()}


@router.post("/strategies/{strategy_id}/toggle")
async def toggle_strategy(strategy_id: str) -> Dict[str, Any]:
    updated = store.toggle_strategy(strategy_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"strategy": updated}


@router.get("/ai/analysis")
async def ai_analysis(
    symbol: str = Query(default="RELIANCE"), interval: str = Query(default="5m")
) -> Dict[str, Any]:
    try:
        return await analyze(symbol, interval)
    except Exception as exc:
        raise _guard(exc) from exc


@router.get("/ai/model")
async def ai_model(interval: str = Query(default="5m")) -> Dict[str, Any]:
    try:
        return ml.status(await ml.bundle(interval))
    except Exception as exc:
        raise _guard(exc) from exc


@router.get("/ai/targets")
async def ai_targets(
    group: str = Query(default="all"),
    limit: int = Query(default=16, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    refresh: bool = Query(default=False),
) -> Dict[str, Any]:
    if group not in {"all", "indices", "banks", "nse_companies", "bse_companies"}:
        raise HTTPException(status_code=400, detail="Unknown symbol group")
    try:
        return await build_targets(group, limit, offset, refresh)
    except Exception as exc:
        raise _guard(exc) from exc


@router.get("/alerts")
async def alerts() -> Dict[str, Any]:
    return {"alerts": store.get_alerts()}


@router.post("/alerts/read")
async def read_alerts() -> Dict[str, Any]:
    return {"marked": store.mark_all_read()}


@router.get("/settings")
async def app_settings() -> Dict[str, Any]:
    return {
        "app_name": settings.APP_NAME, "version": settings.APP_VERSION,
        "market": "NSE", "exchange": "NSE", "data_source": "Yahoo Finance chart API",
        "refresh_seconds": settings.MARKET_REFRESH_SECONDS,
        "watchlist": settings.watchlist, "indices": settings.indices,
        "signal_min_confidence": settings.SIGNAL_MIN_CONFIDENCE,
        "model": "RandomForestClassifier (retrained every 15 minutes)",
        "broker": broker_status(),
    }
