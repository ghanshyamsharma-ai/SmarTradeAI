"""EMA + RSI momentum strategy with candlestick confirmation."""

from typing import Any, Dict, List, Optional

from indicators.technical import compute_all
from patterns.candlestick import latest_signal
from strategy.base import BaseStrategy


class MomentumStrategy(BaseStrategy):
    id = "momentum"
    name = "EMA Momentum"
    description = "EMA 20/50 crossover confirmed by RSI and price action."
    risk = "MEDIUM"

    def analyze(
        self,
        candles: List[Dict[str, Any]],
        indicators: Optional[Dict[str, List[Optional[float]]]] = None,
    ) -> Optional[Dict[str, Any]]:
        ind = indicators or compute_all(candles)
        if len(candles) < 21:
            return None

        last = candles[-1]
        price = last["c"]
        ema20 = ind["ema20"][-1]
        ema50 = ind["ema50"][-1]
        rsi = ind["rsi14"][-1]
        pattern = latest_signal(candles[-6:])

        if ema20 is None or rsi is None:
            return None

        score = 0
        reasons: List[str] = []
        side = None

        if ema50 is not None:
            if ema20 > ema50 and price > ema20:
                score += 34
                side = "BUY"
                reasons.append("Price above EMA 20 & 50")
            elif ema20 < ema50 and price < ema20:
                score += 34
                side = "SELL"
                reasons.append("Price below EMA 20 & 50")

        if rsi < 32:
            score += 22
            side = "BUY" if side is None or side == "BUY" else side
            reasons.append(f"RSI oversold ({rsi})")
        elif rsi > 68:
            score += 22
            side = "SELL" if side is None or side == "SELL" else side
            reasons.append(f"RSI overbought ({rsi})")
        elif 45 <= rsi <= 58:
            score += 10
            reasons.append(f"RSI neutral ({rsi})")

        if pattern and pattern["side"] == side and side is not None:
            score += 24
            reasons.append(f"{pattern['name']} confirmation")
        elif pattern:
            score += 8
            reasons.append(f"{pattern['name']} seen")

        if side is None or score < 45:
            return None

        confidence = min(96, max(52, score))
        direction = 1 if side == "BUY" else -1
        atr = max((last["h"] - last["l"]) * 0.6, price * 0.004)
        return {
            "strategy": self.name,
            "strategy_id": self.id,
            "side": side,
            "confidence": confidence,
            "reason": " • ".join(reasons),
            "entry": round(price, 2),
            "target": round(price + direction * atr * 3.2, 2),
            "stoploss": round(price - direction * atr * 1.4, 2),
        }


class MeanReversionStrategy(BaseStrategy):
    id = "mean_reversion"
    name = "Mean Reversion"
    description = "Bollinger band extremes with RSI exhaustion filter."
    risk = "LOW"

    def analyze(
        self,
        candles: List[Dict[str, Any]],
        indicators: Optional[Dict[str, List[Optional[float]]]] = None,
    ) -> Optional[Dict[str, Any]]:
        ind = indicators or compute_all(candles)
        if len(candles) < 21:
            return None
        price = candles[-1]["c"]
        upper, lower, rsi = ind["bb_upper"][-1], ind["bb_lower"][-1], ind["rsi14"][-1]
        if upper is None or lower is None or rsi is None:
            return None

        if price <= lower and rsi < 20:
            side, score = "BUY", 80
            reason = f"Price at lower band • RSI {rsi}"
        elif price >= upper and rsi > 80:
            side, score = "SELL", 20
            reason = f"Price at upper band • RSI {rsi}"
        else:
            return None

        direction = 1 if side == "BUY" else -1
        atr = max((candles[-1]["h"] - candles[-1]["l"]) * 0.5, price * 0.003)
        return {
            "strategy": self.name,
            "strategy_id": self.id,
            "side": side,
            "confidence": score,
            "reason": reason,
            "entry": round(price, 2),
            "target": round(price + direction * atr * 2.6, 2),
            "stoploss": round(price - direction * atr * 1.2, 2),
        }


STRATEGIES = [MomentumStrategy(), MeanReversionStrategy()]


def get_strategy(strategy_id: str) -> Optional[BaseStrategy]:
    for strategy in STRATEGIES:
        if strategy.id == strategy_id:
            return strategy
    return None
