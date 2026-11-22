"""Momentum + RandomForest target/stoploss planner.

Levels come from live Yahoo Finance OHLCV data. 5-minute candles are primary;
when Yahoo has no 5m series for a symbol, real daily candles are used and the
row is labelled with the interval actually used. Direction is the genuine
RandomForest read confirmed by EMA/RSI/candle momentum, and levels are ATR(14)
derived from those same candles. Symbols Yahoo cannot serve at either interval
are reported as failures; no estimated or simulated row is added.
"""

import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

from ai.ml_model import ModelBundle, ml
from config.settings import settings
from config.symbols import market_catalog
from core.logger import logger
from indicators.technical import compute_all
from patterns.candlestick import latest_signal
from services.yahoo_client import yahoo

CACHE_TTL_SECONDS = 300
INTERVAL = "5m"
FALLBACK_INTERVAL = "1d"
STALE_DAYS = 10
HORIZON_TEXT = {
    INTERVAL: "next 3 five-minute candles",
    FALLBACK_INTERVAL: "next 3 daily candles (5m unavailable)",
}

GROUP_LABELS = {
    "indices": "Index",
    "banks": "Bank",
    "nse_companies": "NSE Company",
    "bse_companies": "BSE Company",
}

_CACHE: Dict[Tuple[Any, ...], Tuple[float, Dict[str, Any]]] = {}
_LOCK = asyncio.Lock()


def _universe(group: str) -> List[Dict[str, str]]:
    catalog = market_catalog()
    if group == "all":
        items: List[Dict[str, str]] = []
        for key, label in GROUP_LABELS.items():
            items.extend({**item, "group": key, "group_label": label} for item in catalog[key])
        return items
    return [
        {**item, "group": group, "group_label": GROUP_LABELS[group]}
        for item in catalog[group]
    ]


def _r2(value: float) -> float:
    return round(float(value), 2)


def _atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    true_ranges: List[float] = []
    for i in range(1, len(candles)):
        prev_close = candles[i - 1]["c"]
        candle = candles[i]
        true_ranges.append(max(
            candle["h"] - candle["l"],
            abs(candle["h"] - prev_close),
            abs(candle["l"] - prev_close),
        ))
    if not true_ranges:
        candle = candles[-1]
        return max(candle["h"] - candle["l"], candle["c"] * 0.004)
    window = true_ranges[-period:]
    return sum(window) / len(window)


def _momentum(candles: List[Dict[str, Any]], ind: Dict[str, List[Any]]) -> Dict[str, Any]:
    price = candles[-1]["c"]
    ema20 = ind["ema20"][-1]
    ema50 = ind["ema50"][-1]
    rsi = ind["rsi14"][-1]
    score = 0.0
    notes: List[str] = []

    if ema20 is not None and ema50 is not None:
        if price > ema20 > ema50:
            score += 28
            notes.append(f"Price above EMA20 {_r2(ema20)} and EMA50 {_r2(ema50)}")
        elif price < ema20 < ema50:
            score -= 28
            notes.append(f"Price below EMA20 {_r2(ema20)} and EMA50 {_r2(ema50)}")
        else:
            notes.append("EMA20/EMA50 structure is mixed")

    if rsi is not None:
        if rsi < 35:
            score += 18
            notes.append(f"RSI(14) {rsi} oversold")
        elif rsi > 65:
            score -= 18
            notes.append(f"RSI(14) {rsi} overbought")
        else:
            score += 6 if rsi >= 50 else -6
            notes.append(f"RSI(14) {rsi}")
    else:
        notes.append("RSI unavailable on this series")

    if len(candles) >= 4:
        ret3 = price / candles[-4]["c"] - 1
        score += max(-20.0, min(20.0, ret3 * 1000))
        notes.append(f"3-candle move {ret3 * 100:+.2f}%")

    pattern = latest_signal(candles[-8:])
    if pattern:
        pattern_dir = 1 if pattern["side"] == "BUY" else -1
        if (score >= 0 and pattern_dir > 0) or (score < 0 and pattern_dir < 0):
            score += 12
        notes.append(f"{pattern['name']} candle confirmation")

    side = "BUY" if score > 12 else "SELL" if score < -12 else "NEUTRAL"
    return {
        "score": round(score, 1), "side": side, "notes": notes,
        "ema20": ema20, "ema50": ema50, "rsi14": rsi,
    }


def _build_row(
    item: Dict[str, str], data: Dict[str, Any], bundle: ModelBundle, interval: str = INTERVAL
) -> Dict[str, Any]:
    candles = data["candles"]
    if len(candles) < 65:
        raise RuntimeError("Yahoo returned fewer than 65 live candles")

    prediction = ml.predict_data(data, bundle)
    ind = compute_all(candles)
    momentum = _momentum(candles, ind)

    price = float(data["price"])
    atr = _atr(candles)
    market_time = data.get("market_time", "")
    stale_days: Any = None
    if market_time:
        try:
            last = datetime.fromisoformat(market_time)
            now = datetime.now(last.tzinfo) if last.tzinfo else datetime.now()
            stale_days = max(0, (now - last).days)
        except (TypeError, ValueError):
            stale_days = None
    is_stale = stale_days is not None and stale_days > STALE_DAYS
    ml_bias = prediction["bias"]
    ml_conf = float(prediction["confidence"])
    momentum_side = momentum["side"]
    disagreement = (
        (ml_bias == "BULLISH" and momentum_side == "SELL")
        or (ml_bias == "BEARISH" and momentum_side == "BUY")
    )

    if ml_bias == "BULLISH" and momentum_side != "SELL":
        signal = "BUY"
    elif ml_bias == "BEARISH" and momentum_side != "BUY":
        signal = "SELL"
    elif momentum_side != "NEUTRAL" and ml_conf >= 52:
        signal = momentum_side
    else:
        signal = "WAIT"

    confidence = round(0.65 * ml_conf + 0.35 * min(100.0, abs(momentum["score"])))
    if disagreement:
        confidence -= 12
    if interval != INTERVAL:
        # The RandomForest was fitted on 5-minute labels; daily inference is
        # real data but out-of-distribution, so do not overstate confidence.
        confidence -= 10
    confidence = max(0, min(96, confidence))
    if is_stale:
        signal = "WAIT"
        confidence = min(confidence, 40)
    if signal != "WAIT" and confidence < settings.SIGNAL_MIN_CONFIDENCE:
        signal = "WAIT"

    direction = 1 if signal == "BUY" else -1 if signal == "SELL" else (1 if momentum["score"] >= 0 else -1)
    target = price + direction * atr * 2.0
    stoploss = price - direction * atr * 1.0
    zone_low = price - (0.25 if direction > 0 else 0.10) * atr
    zone_high = price + (0.10 if direction > 0 else 0.25) * atr
    risk = abs(price - stoploss) or max(price * 0.001, 0.01)
    reward = abs(target - price)
    rr = round(reward / risk, 2)

    exchange = data.get("exchange") or ("BSE" if item["symbol"].endswith(".BO") else "NSE")
    if signal == "BUY":
        action = (
            f"Buy near ₹{_r2(zone_low)}–₹{_r2(zone_high)} on {exchange}. "
            f"Trigger only while price holds above EMA20 ₹{_r2(momentum['ema20'] or price)}; "
            f"target ₹{_r2(target)}, stop ₹{_r2(stoploss)} (risk:reward 1:{rr})."
        )
    elif signal == "SELL":
        action = (
            f"Sell / avoid longs near ₹{_r2(zone_low)}–₹{_r2(zone_high)} on {exchange}. "
            f"Target ₹{_r2(target)}, stop ₹{_r2(stoploss)} (risk:reward 1:{rr})."
        )
    else:
        action = (
            f"No buy zone yet. Watch ₹{_r2(zone_low)}–₹{_r2(zone_high)} on {exchange} and wait for "
            f"ML confidence ≥{settings.SIGNAL_MIN_CONFIDENCE}% with EMA/RSI momentum alignment. "
            f"Levels shown are reference only."
            + (" Yahoo candle is stale; no action until fresh data." if is_stale else "")
        )

    reasons = list(momentum["notes"])
    reasons.append(f"RandomForest {ml_bias} {ml_conf}% over {HORIZON_TEXT[interval]}")
    if disagreement:
        reasons.append("Momentum disagrees with ML - confidence reduced")
    if interval != INTERVAL:
        reasons.append("5m candles unavailable; scored from real 1d candles (model trained on 5m)")
    if is_stale:
        reasons.append(f"Yahoo candle stale by {stale_days} days - reference only")
    if signal == "WAIT" and confidence >= settings.SIGNAL_MIN_CONFIDENCE:
        reasons.append("Direction not confirmed - no actionable signal")

    return {
        "symbol": data["symbol"],
        "name": data.get("name") or item["group_label"],
        "group": item["group"],
        "group_label": item["group_label"],
        "exchange": exchange,
        "price": _r2(price),
        "change_pct": _r2(data.get("change_pct", 0.0)),
        "signal": signal,
        "ml_bias": ml_bias,
        "ml_confidence": ml_conf,
        "momentum_score": momentum["score"],
        "momentum_side": momentum_side,
        "confidence": confidence,
        "entry": _r2(price),
        "zone_low": _r2(zone_low),
        "zone_high": _r2(zone_high),
        "zone_label": "BUY ZONE" if signal == "BUY" else "SELL ZONE" if signal == "SELL" else "WATCH",
        "target": _r2(target),
        "stoploss": _r2(stoploss),
        "risk_reward": rr,
        "atr14": _r2(atr),
        "ema20": _r2(momentum["ema20"]) if momentum["ema20"] is not None else None,
        "ema50": _r2(momentum["ema50"]) if momentum["ema50"] is not None else None,
        "rsi14": _r2(momentum["rsi14"]) if momentum["rsi14"] is not None else None,
        "reason": " • ".join(reasons),
        "action": action,
        "reference_only": signal == "WAIT" or is_stale,
        "stale": is_stale,
        "stale_days": stale_days,
        "interval_used": interval,
        "horizon": HORIZON_TEXT[interval],
        "model_accuracy": prediction["model"]["out_of_sample_accuracy"],
        "market_time": market_time,
        "source": f"Yahoo Finance live {interval} OHLCV + RandomForest + EMA/RSI momentum",
    }


async def _one(item: Dict[str, str], bundle: ModelBundle) -> Dict[str, Any]:
    last_error: Any = None
    for interval in (INTERVAL, FALLBACK_INTERVAL):
        try:
            data = await yahoo.chart(item["symbol"], interval, 200)
            row = _build_row(item, data, bundle, interval)
            row["group"] = item["group"]
            row["group_label"] = item["group_label"]
            return row
        except Exception as exc:
            last_error = exc
            if interval == INTERVAL:
                logger.warning(
                    f"Target planner {item['symbol']} 5m unavailable ({exc}); retrying 1d"
                )
    logger.warning(f"Target planner skipped {item['symbol']}: {last_error}")
    return {"_error": str(last_error), "_symbol": item["symbol"]}


async def build_targets(
    group: str = "all", limit: int = 20, offset: int = 0, refresh: bool = False
) -> Dict[str, Any]:
    universe = _universe(group)
    page = universe[offset:offset + limit]
    key = (group, offset, limit)

    cached = _CACHE.get(key)
    if not refresh and cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return {**cached[1], "meta": {**cached[1]["meta"], "cache": "hit"}}

    async with _LOCK:
        cached = _CACHE.get(key)
        if not refresh and cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
            return {**cached[1], "meta": {**cached[1]["meta"], "cache": "hit"}}

        bundle = await ml.bundle(INTERVAL)
        outcomes = await asyncio.gather(*(_one(item, bundle) for item in page))
        rows: List[Dict[str, Any]] = []
        failed: List[Dict[str, str]] = []
        for outcome in outcomes:
            if "_error" in outcome:
                failed.append({"symbol": outcome["_symbol"], "reason": outcome["_error"]})
            else:
                rows.append(outcome)

        rows.sort(key=lambda r: (
            r["signal"] == "WAIT", -r["confidence"], -r["risk_reward"], r["symbol"]
        ))
        model_status = ml.status(bundle)
        payload = {
            "targets": rows,
            "meta": {
                "group": group,
                "offset": offset,
                "limit": limit,
                "universe_total": len(universe),
                "page_size": len(page),
                "returned": len(rows),
                "failed": len(failed),
                "failed_symbols": failed[:10],
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "cache": "miss",
                "interval": INTERVAL,
                "fallback_interval": FALLBACK_INTERVAL,
                "horizon": HORIZON_TEXT[INTERVAL],
                "model_accuracy": model_status["out_of_sample_accuracy"],
                "model_edge": model_status["edge_over_baseline"],
                "model_symbols": len(model_status["symbols"]),
                "trained_symbols": model_status["symbols"],
                "min_confidence": settings.SIGNAL_MIN_CONFIDENCE,
                "source": "Yahoo Finance live chart API",
                "delay_note": "Yahoo Finance · NSE quotes may be delayed ~15 minutes",
                "note": (
                    "Model trained on a 15-symbol live 5m watchlist; other symbols use the same generic "
                    "feature space. Symbols without 5m candles use real 1d Yahoo candles and are labelled "
                    "per row. Symbols unavailable at both intervals are omitted, never estimated."
                ),
            },
        }
        _CACHE[key] = (time.monotonic(), payload)
        return payload
