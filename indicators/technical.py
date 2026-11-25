"""Pure-Python technical indicators used by the signal engine.

No external dependencies (no pandas/numpy) so the app runs from requirements.txt
without adding heavy scientific packages.
"""

from typing import List, Optional, Dict, Any


def _clean(values: List[float]) -> List[float]:
    return [float(v) for v in values if v is not None]


def sma(values: List[float], period: int) -> List[Optional[float]]:
    """Simple moving average. Leading values are None."""
    out: List[Optional[float]] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1:i + 1]
        out[i] = round(sum(window) / period, 2)
    return out


def _ema_numeric(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if not values:
        return out
    k = 2.0 / (period + 1)
    if len(values) >= period:
        seed = sum(values[:period]) / period
        start = period - 1
    else:
        seed = sum(values) / len(values)
        start = 0
    out[start] = round(seed, 2)
    for i in range(start + 1, len(values)):
        out[i] = round(values[i] * k + out[i - 1] * (1 - k), 2)
    return out


def ema(values: List[float], period: int) -> List[Optional[float]]:
    """Exponential moving average."""
    return _ema_numeric(_clean(values), period) if len(values) == len(_clean(values)) else _ema_with_gaps(values, period)


def _ema_with_gaps(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    numeric = _clean(values)
    e = _ema_numeric(numeric, period)
    offset = len(values) - len(numeric)
    for i, v in enumerate(e):
        out[i + offset] = v
    return out


def rsi(values: List[float], period: int = 14) -> List[Optional[float]]:
    """Relative Strength Index (Wilder's smoothing)."""
    out: List[Optional[float]] = [None] * len(values)
    if len(values) <= period:
        return out
    gains, losses = [], []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(values)):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = round(100 - (100 / (1 + rs)), 2)
    return out


def macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, List[Optional[float]]]:
    """MACD line, signal line and histogram."""
    ef = _ema_numeric(values, fast)
    es = _ema_numeric(values, slow)
    line: List[Optional[float]] = []
    for f, s in zip(ef, es):
        line.append(round(f - s, 2) if f is not None and s is not None else None)
    numeric_line = _clean(line)
    sig = _ema_numeric(numeric_line, signal)
    offset = len(line) - len(numeric_line)
    signal_line: List[Optional[float]] = [None] * len(line)
    for i, v in enumerate(sig):
        signal_line[i + offset] = v
    hist: List[Optional[float]] = []
    for l, s in zip(line, signal_line):
        hist.append(round(l - s, 2) if l is not None and s is not None else None)
    return {"macd": line, "signal": signal_line, "histogram": hist}


def bollinger(values: List[float], period: int = 20, stddev: float = 2.0) -> Dict[str, List[Optional[float]]]:
    """Bollinger bands (upper, middle, lower)."""
    middle = sma(values, period)
    upper: List[Optional[float]] = [None] * len(values)
    lower: List[Optional[float]] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1:i + 1]
        mean = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        sd = variance ** 0.5
        upper[i] = round(mean + stddev * sd, 2)
        lower[i] = round(mean - stddev * sd, 2)
    return {"upper": upper, "middle": middle, "lower": lower}


def compute_all(candles: List[Dict[str, Any]]) -> Dict[str, List[Optional[float]]]:
    """Compute the indicator bundle used by the dashboard chart and strategies."""
    closes = [c["c"] for c in candles]
    macd_data = macd(closes)
    bb = bollinger(closes)
    return {
        "sma20": sma(closes, 20),
        "ema20": ema(closes, 20),
        "ema50": ema(closes, 50) if len(closes) >= 60 else [None] * len(closes),
        "rsi14": rsi(closes, 5),
        "macd": macd_data["macd"],
        "macd_signal": macd_data["signal"],
        "macd_hist": macd_data["histogram"],
        "bb_upper": bb["upper"],
        "bb_middle": bb["middle"],
        "bb_lower": bb["lower"],
    }
