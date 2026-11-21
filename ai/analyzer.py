"""AI analysis: live market context combined with the ML model output."""

from typing import Any, Dict, List

from ai.ml_model import ml
from indicators.technical import compute_all
from patterns.candlestick import latest_signal
from services.yahoo_client import yahoo


async def analyze(symbol: str, interval: str = "5m") -> Dict[str, Any]:
    prediction = await ml.predict(symbol, interval)
    data = await yahoo.chart(symbol, interval, 120)
    ind = compute_all(data["candles"])
    pattern = latest_signal(data["candles"][-8:])
    rsi = ind["rsi14"][-1]
    ema20 = ind["ema20"][-1]
    ema50 = ind["ema50"][-1]

    points: List[str] = []
    if ema20 and ema50:
        trend = "bullish" if data["price"] > ema20 > ema50 else \
                "bearish" if data["price"] < ema20 < ema50 else "transitioning"
        points.append(f"EMA structure is {trend} (EMA20 {ema20}, EMA50 {ema50})")
    if rsi is not None:
        zone = "oversold" if rsi < 35 else "overbought" if rsi > 65 else "neutral"
        points.append(f"RSI(14) at {rsi} - {zone} zone")
    if pattern:
        points.append(f"{pattern['name']} pattern on the latest completed candle")
    points.append(f"Day range {data['day_low']} - {data['day_high']} | Volume {data['volume']:,}")
    points.append(f"ML out-of-sample accuracy {prediction['model']['out_of_sample_accuracy']}% "
                  f"on {prediction['model']['test_samples']} held-out samples")

    bias = prediction["bias"]
    suggestion = (
        "Model favours long setups; wait for price to confirm above short-term moving averages."
        if bias == "BULLISH" else
        "Model favours short setups; avoid longs until the trend reverses."
        if bias == "BEARISH" else
        "No directional edge detected; stay flat and wait for a clearer setup."
    )

    return {
        **prediction,
        "interval": interval,
        "exchange": data["exchange"],
        "currency": data["currency"],
        "summary": (
            f"{data['name']} ({data['symbol']}) last traded at {data['price']} "
            f"({data['change_pct']:+.2f}%). The RandomForest model assigns "
            f"{prediction['confidence']}% confidence to a {bias.lower()} bias over the next 3 candles."
        ),
        "key_points": points,
        "suggestion": suggestion,
        "technical": {
            "rsi14": rsi, "ema20": ema20, "ema50": ema50,
            "day_high": data["day_high"], "day_low": data["day_low"],
        },
        "delay_note": data["delay_note"],
        "source": "Yahoo Finance live chart API",
    }
