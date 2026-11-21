"""Signal engine combining technical strategies with the ML direction model."""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from ai.ml_model import ml
from config.settings import settings
from core.logger import logger
from data.store import store
from indicators.technical import compute_all
from services.yahoo_client import yahoo
from strategy.momentum import STRATEGIES


async def generate_signal_for(symbol: str) -> List[Dict[str, Any]]:
    try:
        data = await yahoo.chart(symbol, "5m", 120)
        indicators = compute_all(data["candles"])
        setups = []
        for strategy in STRATEGIES:
            setup = strategy.analyze(data["candles"], indicators)
            if setup:
                setups.append(setup)
        if not setups:
            return []

        prediction = await ml.predict(symbol, "5m")
        best = max(setups, key=lambda s: s["confidence"])
        agrees = (
            (best["side"] == "BUY" and prediction["bias"] == "BULLISH")
            or (best["side"] == "SELL" and prediction["bias"] == "BEARISH")
        )
        if not agrees or prediction["confidence"] < 50:
            return []

        confidence = round(best["confidence"] * 0.4 + prediction["confidence"] * 0.6)
        if confidence < settings.SIGNAL_MIN_CONFIDENCE:
            return []

        return [{
            "id": f"{data['symbol']}-{datetime.now().strftime('%H%M%S')}",
            "symbol": data["symbol"],
            "name": data["name"],
            **best,
            "strategy": f"{best['strategy']} + ML",
            "confidence": confidence,
            "ml_bias": prediction["bias"],
            "ml_probability_up": prediction["probability_up"],
            "ml_probability_down": prediction["probability_down"],
            "model_accuracy": prediction["model"]["out_of_sample_accuracy"],
            "price": data["price"],
            "market_time": data["market_time"],
            "time": datetime.now().strftime("%H:%M:%S"),
            "status": "ACTIVE",
        }]
    except Exception as exc:
        logger.warning(f"Signal skipped for {symbol}: {exc}")
        return []


async def scan(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    watchlist = symbols or settings.watchlist
    results = await asyncio.gather(*(generate_signal_for(s) for s in watchlist))
    found = [item for group in results for item in group]
    found.sort(key=lambda s: (s["confidence"], s["ml_probability_up"]), reverse=True)
    found = found[:12]
    store.set_signals(found)
    store.add_alerts_for_signals(found)
    await store.persist_signals()
    return {
        "scanned": len(watchlist),
        "signals_generated": len(found),
        "signals": found,
        "last_scan": datetime.now().isoformat(timespec="seconds"),
    }


async def seed_if_empty() -> None:
    if not store.get_signals():
        try:
            await scan()
        except Exception as exc:
            logger.warning(f"Initial scan deferred: {exc}")
