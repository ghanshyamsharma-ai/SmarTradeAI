"""In-memory state with optional MongoDB persistence.

Only real signals produced from live Yahoo data are stored here.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from core.logger import logger

try:
    from database.mongodb import get_database
except Exception:
    get_database = None


class Store:
    def __init__(self) -> None:
        self._signals: List[Dict[str, Any]] = []
        self._strategies: List[Dict[str, Any]] = [
            {"id": "momentum", "name": "EMA Momentum", "type": "Trend",
             "description": "EMA 20/50 structure confirmed by RSI and candlestick patterns.",
             "risk": "MEDIUM", "enabled": True, "status": "ACTIVE"},
            {"id": "mean_reversion", "name": "Mean Reversion", "type": "Contrarian",
             "description": "Bollinger band extremes with RSI exhaustion filter.",
             "risk": "LOW", "enabled": True, "status": "ACTIVE"},
            {"id": "ml_filter", "name": "ML Direction Filter", "type": "Machine Learning",
             "description": "RandomForest direction probability gates every technical setup.",
             "risk": "MEDIUM", "enabled": True, "status": "ACTIVE"},
        ]
        self._alerts: List[Dict[str, Any]] = []
        self._last_scan = ""

    def get_signals(self) -> List[Dict[str, Any]]:
        return self._signals

    def set_signals(self, signals: List[Dict[str, Any]]) -> None:
        self._signals = signals
        self._last_scan = datetime.now().isoformat(timespec="seconds")

    def get_strategies(self) -> List[Dict[str, Any]]:
        return self._strategies

    def toggle_strategy(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        for s in self._strategies:
            if s["id"] == strategy_id:
                s["enabled"] = not s["enabled"]
                s["status"] = "ACTIVE" if s["enabled"] else "PAUSED"
                return s
        return None

    def add_alerts_for_signals(self, signals: List[Dict[str, Any]]) -> None:
        existing = {(a["symbol"], a["message"]) for a in self._alerts}
        for sig in signals[:5]:
            msg = f"{sig['side']} setup at {sig['price']} - ML {sig['ml_bias']} {sig['confidence']}%"
            if (sig["symbol"], msg) in existing:
                continue
            self._alerts.insert(0, {
                "id": len(self._alerts) + 1,
                "symbol": sig["symbol"], "type": sig["side"], "message": msg,
                "time": datetime.now().strftime("%H:%M:%S"), "read": False,
            })
        self._alerts = self._alerts[:30]

    def get_alerts(self) -> List[Dict[str, Any]]:
        return self._alerts

    def mark_all_read(self) -> int:
        n = 0
        for a in self._alerts:
            if not a["read"]:
                a["read"] = True
                n += 1
        return n

    @property
    def last_scan(self) -> str:
        return self._last_scan

    async def persist_signals(self) -> bool:
        if get_database is None:
            return False
        try:
            db = get_database()
            if db is None:
                return False
            if self._signals:
                await db["signals"].delete_many({})
                await db["signals"].insert_many([dict(s) for s in self._signals])
            return True
        except Exception as exc:
            logger.warning(f"MongoDB persistence skipped: {exc}")
            return False


store = Store()
