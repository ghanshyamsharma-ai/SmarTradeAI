"""Machine-learning direction model trained on live Yahoo Finance history.

A single RandomForest is trained across the watchlist on price/volume/technical
features. Labels are the next 3-candle direction for moves beyond ±0.2%; flat
outcomes are excluded. Predictions are genuinely out-of-sample on the most
recent 25% of every symbol's history.
"""

import asyncio
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score

from config.settings import settings
from core.logger import logger
from services.yahoo_client import yahoo

FEATURES = [
    "ret_1", "ret_5", "ma_ratio_12_26", "price_vs_sma20", "rsi14",
    "macd_hist_norm", "bb_position", "volume_ratio", "volatility_10",
    "candle_body", "candle_range", "lower_wick", "upper_wick",
]

HORIZON = 3
MOVE_THRESHOLD = 0.002
MODEL_TTL_SECONDS = 15 * 60


@dataclass
class ModelBundle:
    model: RandomForestClassifier
    accuracy: float
    precision: float
    baseline: float
    train_size: int
    test_size: int
    importance: Dict[str, float]
    trained_at: str
    symbols: List[str]


def _rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(-period, 0):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain, avg_loss = sum(gains) / period, sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return float(100 - 100 / (1 + avg_gain / avg_loss))


def _feature_rows(candles: List[Dict[str, Any]]) -> Tuple[List[List[float]], List[int], List[int]]:
    """Return (features, labels, indices) for every candle with enough history."""
    closes = [c["c"] for c in candles]
    volumes = [float(c["v"]) for c in candles]
    rows: List[List[float]] = []
    labels: List[int] = []
    idxs: List[int] = []

    for i in range(60, len(candles)):
        c = candles[i]
        o, h, l, cl = c["o"], c["h"], c["l"], c["c"]
        window = closes[i - 59:i + 1]
        recent = closes[i - 9:i + 1]
        vol_window = volumes[i - 19:i + 1]
        rets = [window[j] / window[j - 1] - 1 for j in range(1, len(window))]
        ma12 = sum(closes[i - 11:i + 1]) / 12
        ma26 = sum(closes[i - 25:i + 1]) / 26
        sma20 = sum(closes[i - 19:i + 1]) / 20
        sd20 = float(np.std(closes[i - 19:i + 1])) or 1e-9
        upper, lower = sma20 + 2 * sd20, sma20 - 2 * sd20
        avg_vol = sum(vol_window) / len(vol_window) or 1.0
        rng = max(o, 1e-9)

        rows.append([
            cl / closes[i - 1] - 1,
            cl / closes[i - 5] - 1,
            ma12 / ma26 - 1,
            cl / sma20 - 1,
            _rsi(window) / 100,
            (ma12 - ma26) / cl,
            (cl - lower) / (upper - lower),
            volumes[i] / avg_vol,
            float(np.std(rets)) or 0.0,
            (cl - o) / rng,
            (h - l) / rng,
            (min(o, cl) - l) / rng,
            (h - max(o, cl)) / rng,
        ])

        if i + HORIZON < len(candles):
            future = closes[i + HORIZON] / cl - 1
            labels.append(1 if future > MOVE_THRESHOLD else -1 if future < -MOVE_THRESHOLD else 0)
        else:
            labels.append(0)
        idxs.append(i)

    return rows, labels, idxs


class MLService:
    def __init__(self) -> None:
        self._cache: Dict[str, Tuple[float, ModelBundle]] = {}
        self._lock = asyncio.Lock()

    def _fresh(self, interval: str) -> Optional[ModelBundle]:
        item = self._cache.get(interval)
        if item and time.monotonic() - item[0] < MODEL_TTL_SECONDS:
            return item[1]
        return None

    async def bundle(self, interval: str = "5m") -> ModelBundle:
        cached = self._fresh(interval)
        if cached:
            return cached
        async with self._lock:
            cached = self._fresh(interval)
            if cached:
                return cached

            symbols = settings.watchlist
            series = await asyncio.gather(
                *(yahoo.chart(s, interval, 400) for s in symbols), return_exceptions=True
            )
            x_train, y_train, x_test, y_test, used = [], [], [], [], []
            for sym, data in zip(symbols, series):
                if isinstance(data, Exception):
                    logger.warning(f"ML skipped {sym}: {data}")
                    continue
                rows, labels, idxs = _feature_rows(data["candles"])
                # Flat outcomes carry no tradable signal; exclude them from fitting
                # and scoring so the reported baseline is a real 50/50 coin flip.
                tradable = [i for i, label in enumerate(labels) if label != 0]
                rows = [rows[i] for i in tradable]
                labels = [labels[i] for i in tradable]
                if len(rows) < 40:
                    continue
                split = int(len(rows) * 0.75)
                x_train.extend(rows[:split]); y_train.extend(labels[:split])
                x_test.extend(rows[split:]); y_test.extend(labels[split:])
                used.append(sym)

            if len(x_train) < 200 or len(x_test) < 50:
                raise RuntimeError("Not enough live market history to train the model")

            model = RandomForestClassifier(
                n_estimators=140, max_depth=6, min_samples_leaf=6,
                class_weight="balanced_subsample", random_state=42, n_jobs=-1,
            )
            model.fit(np.asarray(x_train), np.asarray(y_train))
            preds = model.predict(np.asarray(x_test))
            importance = dict(sorted(zip(FEATURES, model.feature_importances_.tolist()),
                                     key=lambda kv: kv[1], reverse=True))
            baseline = max(Counter(y_test).values()) / len(y_test) if y_test else 0.0
            bundle = ModelBundle(
                model=model,
                accuracy=round(float(accuracy_score(y_test, preds)), 4),
                precision=round(float(precision_score(y_test, preds, average="macro", zero_division=0)), 4),
                baseline=round(float(baseline), 4),
                train_size=len(x_train), test_size=len(x_test), importance=importance,
                trained_at=time.strftime("%Y-%m-%d %H:%M:%S"), symbols=used,
            )
            self._cache[interval] = (time.monotonic(), bundle)
            logger.info(f"ML model trained: acc={bundle.accuracy} symbols={len(used)}")
            return bundle

    def status(self, bundle: ModelBundle) -> Dict[str, Any]:
        return {
            "algorithm": "RandomForestClassifier",
            "features": FEATURES,
            "feature_importance": bundle.importance,
            "out_of_sample_accuracy": round(bundle.accuracy * 100, 2),
            "baseline_accuracy": round(bundle.baseline * 100, 2),
            "edge_over_baseline": round((bundle.accuracy - bundle.baseline) * 100, 2),
            "macro_precision": round(bundle.precision * 100, 2),
            "train_samples": bundle.train_size,
            "test_samples": bundle.test_size,
            "trained_at": bundle.trained_at,
            "symbols": bundle.symbols,
            "label": (
                f"Direction after {HORIZON} candles, moves beyond +/-{MOVE_THRESHOLD * 100:.1f}% "
                "(flat outcomes excluded)"
            ),
        }

    async def predict(self, symbol: str, interval: str = "5m") -> Dict[str, Any]:
        bundle = await self.bundle(interval)
        data = await yahoo.chart(symbol, interval, 400)
        rows, _, _ = _feature_rows(data["candles"])
        if not rows:
            return {"symbol": symbol, "bias": "NEUTRAL", "confidence": 0.0}
        probs = bundle.model.predict_proba(np.asarray([rows[-1]]))[0]
        pmap = {int(c): float(p) for c, p in zip(bundle.model.classes_, probs)}
        up, down, flat = pmap.get(1, 0.0), pmap.get(-1, 0.0), pmap.get(0, 0.0)
        bias = "BULLISH" if up >= down and up >= flat else "BEARISH" if down >= flat else "NEUTRAL"
        confidence = max(up, down, flat)
        return {
            "symbol": data["symbol"],
            "name": data["name"],
            "price": data["price"],
            "change_pct": data["change_pct"],
            "bias": bias,
            "confidence": round(confidence * 100, 1),
            "probability_up": round(up * 100, 1),
            "probability_down": round(down * 100, 1),
            "probability_flat": round(flat * 100, 1),
            "model": self.status(bundle),
            "market_time": data["market_time"],
        }


ml = MLService()
