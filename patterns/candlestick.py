"""Lightweight candlestick pattern recognition."""

from typing import Any, Dict, List


def _body(c: Dict[str, Any]) -> float:
    return abs(c["c"] - c["o"])


def _range(c: Dict[str, Any]) -> float:
    return max(c["h"] - c["l"], 1e-9)


def is_doji(c: Dict[str, Any]) -> bool:
    return _body(c) <= 0.08 * _range(c)


def is_hammer(c: Dict[str, Any]) -> bool:
    lower = min(c["o"], c["c"]) - c["l"]
    upper = c["h"] - max(c["o"], c["c"])
    return lower >= 2 * _body(c) and upper <= 0.5 * _body(c) and _body(c) > 0


def is_inverted_hammer(c: Dict[str, Any]) -> bool:
    lower = min(c["o"], c["c"]) - c["l"]
    upper = c["h"] - max(c["o"], c["c"])
    return upper >= 2 * _body(c) and lower <= 0.5 * _body(c) and _body(c) > 0


def is_bullish_engulfing(prev: Dict[str, Any], cur: Dict[str, Any]) -> bool:
    return (
        prev["c"] < prev["o"]
        and cur["c"] > cur["o"]
        and cur["o"] <= prev["c"]
        and cur["c"] >= prev["o"]
    )


def is_bearish_engulfing(prev: Dict[str, Any], cur: Dict[str, Any]) -> bool:
    return (
        prev["c"] > prev["o"]
        and cur["c"] < cur["o"]
        and cur["o"] >= prev["c"]
        and cur["c"] <= prev["o"]
    )


def detect(candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return all patterns found in the candle series."""
    found: List[Dict[str, Any]] = []
    for i, c in enumerate(candles):
        if is_doji(c):
            found.append({"name": "Doji", "side": "NEUTRAL", "index": i})
        elif is_hammer(c):
            found.append({"name": "Hammer", "side": "BUY", "index": i})
        elif is_inverted_hammer(c):
            found.append({"name": "Inverted Hammer", "side": "BUY", "index": i})
        if i > 0:
            if is_bullish_engulfing(candles[i - 1], c):
                found.append({"name": "Bullish Engulfing", "side": "BUY", "index": i})
            elif is_bearish_engulfing(candles[i - 1], c):
                found.append({"name": "Bearish Engulfing", "side": "SELL", "index": i})
    return found


def latest_signal(candles: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    """Return the most recent directional pattern, if any."""
    directional = [p for p in detect(candles) if p["side"] in ("BUY", "SELL")]
    return directional[-1] if directional else None
