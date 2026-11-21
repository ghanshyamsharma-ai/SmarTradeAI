"""Live market data facade backed by Yahoo Finance."""

from typing import Any, Dict, List, Tuple

from config.settings import settings
from indicators.technical import compute_all
from services.yahoo_client import YahooError, yahoo


async def get_quote(symbol: str) -> Dict[str, Any]:
    quotes = await yahoo.quotes([symbol])
    if not quotes:
        raise YahooError(f"No quote available for {symbol}")
    return quotes[0]


async def get_candles(symbol: str, interval: str = "5m", limit: int = 120) -> Dict[str, Any]:
    data = await yahoo.chart(symbol, interval, limit)
    data["indicators"] = compute_all(data["candles"])
    return data


async def get_watchlist() -> List[Dict[str, Any]]:
    return await yahoo.quotes(settings.watchlist)


async def get_indices() -> List[Dict[str, Any]]:
    return await yahoo.quotes(settings.indices)


async def get_feed() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (indices, watchlist) using a single batch Yahoo request."""
    all_quotes = await yahoo.quotes(settings.indices + settings.watchlist)
    index_symbols = set(settings.indices)
    indices = [q for q in all_quotes if q["symbol"] in index_symbols]
    watchlist = [q for q in all_quotes if q["symbol"] not in index_symbols]
    return indices, watchlist


def get_top_movers(quotes: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    return sorted(quotes, key=lambda q: abs(q["change_pct"]), reverse=True)[:limit]


def market_breadth(quotes: List[Dict[str, Any]]) -> Dict[str, Any]:
    up = sum(1 for q in quotes if q["change_pct"] > 0)
    down = sum(1 for q in quotes if q["change_pct"] < 0)
    flat = len(quotes) - up - down
    avg = sum(q["change_pct"] for q in quotes) / len(quotes) if quotes else 0.0
    return {
        "advances": up, "declines": down, "unchanged": flat,
        "average_change": round(avg, 2),
    }
