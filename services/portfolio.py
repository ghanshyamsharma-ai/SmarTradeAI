"""Broker positions and trade history.

The app never fabricates holdings. Positions appear only after a real broker
session is configured; until then every response is explicitly empty.
"""

from typing import Any, Dict, List

from config.settings import settings


def broker_status() -> Dict[str, Any]:
    configured = settings.broker_configured
    return {
        "broker": "Zerodha Kite" if configured else "Not configured",
        "configured": configured,
        "connected": False,
        "trading_enabled": settings.TRADING_ENABLED,
        "message": (
            "Kite credentials found. Complete the OAuth login and set an access token "
            "to load real positions and trades."
            if configured else
            "No broker connected. Add KITE_API_KEY and KITE_API_SECRET to .env to enable live holdings."
        ),
    }


async def get_positions() -> Dict[str, Any]:
    return {"broker": broker_status(), "positions": [], "total_pnl": 0.0}


async def get_trades() -> Dict[str, Any]:
    return {"broker": broker_status(), "trades": []}
