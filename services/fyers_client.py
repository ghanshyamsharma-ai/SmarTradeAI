"""Fyers market data provider skeleton.

This module is a safe integration skeleton for Fyers market data. It is wired
into the app's provider selection, but live Fyers quote/candle fetching must be
completed with valid Fyers credentials and API mapping before use.

Expected env vars (set in .env, never commit secrets):
  MARKET_DATA_PROVIDER=fyers
  FYERS_APP_ID=your-app-id
  FYERS_SECRET_ID=your-secret-id
  FYERS_ACCESS_TOKEN=your-access-token
  FYERS_REDIRECT_URI=http://127.0.0.1:8000/api/broker/fyers/callback
  FYERS_API_BASE=https://api-t1.fyers.in

Notes:
- Do not hardcode API keys/tokens.
- Fyers symbol format differs from Yahoo (example: NSE:SBIN-EQ). Complete
  SYMBOL_MAP / normalize_symbol() for your watchlist before production use.
- This skeleton intentionally returns clear errors instead of fake data.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import httpx

from config.settings import settings
from core.logger import logger

IST = ZoneInfo("Asia/Kolkata")


class FyersError(Exception):
    """Raised when Fyers market data cannot be served."""


# TODO: Complete symbol mapping for all symbols used by your app.
# Keys should match app symbols (Yahoo-style or canonical app symbols).
# Values should be Fyers symbols, e.g. "NSE:SBIN-EQ", "NSE:NIFTY50-INDEX".
SYMBOL_MAP: Dict[str, str] = {
    # "^NSEI": "NSE:NIFTY50-INDEX",
    # "^NSEBANK": "NSE:NIFTYBANK-INDEX",
    # "^BSESN": "BSE:SENSEX-INDEX",
    # "RELIANCE.NS": "NSE:RELIANCE-EQ",
}


class FyersClient:
    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: Dict[Any, Tuple[float, Any]] = {}
        self._lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(2)

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.REQUEST_TIMEOUT_SECONDS),
                headers={
                    "Accept": "application/json",
                    "Authorization": f"{settings.FYERS_APP_ID}:{settings.FYERS_ACCESS_TOKEN}",
                },
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
        self._cache.clear()

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        s = symbol.strip().upper()
        return SYMBOL_MAP.get(s, s)

    def _require_configured(self) -> None:
        if not settings.FYERS_APP_ID or not settings.FYERS_ACCESS_TOKEN:
            raise FyersError(
                "Fyers is selected but not configured. Set FYERS_APP_ID and FYERS_ACCESS_TOKEN in .env."
            )

    async def _request_json(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self._require_configured()
        client = await self._http()
        base = settings.FYERS_API_BASE.rstrip("/")
        url = f"{base}/{path.lstrip('/')}"
        async with self._sem:
            resp = await client.get(url, params=params)
        if resp.status_code >= 400:
            raise FyersError(f"Fyers HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            payload = resp.json()
        except Exception as exc:
            raise FyersError(f"Fyers returned invalid JSON: {exc}") from exc
        return payload

    @staticmethod
    def _quote_shape(symbol: str, price: float = 0.0, prev: float = 0.0) -> Dict[str, Any]:
        prev = prev or price or 1.0
        change = price - prev
        pct = (change / prev * 100) if prev else 0.0
        return {
            "symbol": symbol,
            "name": symbol,
            "exchange": "NSE",
            "currency": "INR",
            "price": round(float(price), 2),
            "change": round(float(change), 2),
            "change_pct": round(float(pct), 2),
            "previous_close": round(float(prev), 2),
            "day_high": round(float(price), 2),
            "day_low": round(float(price), 2),
            "volume": 0,
            "market_time": datetime.now(IST).isoformat(timespec="seconds"),
            "interval": "quote",
            "delay_note": "Fyers API · live data when provider access is configured",
        }

    async def quotes(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Fetch quotes from Fyers.

        TODO: Implement Fyers v3 quotes endpoint mapping.
        Expected behavior: return app quote dicts matching YahooClient.quotes().
        """
        self._require_configured()
        normalized = list(dict.fromkeys(s.strip().upper() for s in symbols if s and s.strip()))
        if not normalized:
            return []

        # TODO: Replace with real Fyers quotes call.
        # Example endpoint pattern (verify against current Fyers docs before enabling):
        # payload = await self._request_json("/data/quotes", {"symbols": ",".join(mapped)})
        # Then map payload fields to _quote_shape/app quote schema.
        logger.warning("Fyers quotes skeleton called; live Fyers quote mapping is not implemented yet.")
        raise FyersError(
            "Fyers provider skeleton is configured, but quotes mapping is not implemented yet. "
            "Complete services/fyers_client.py quotes() using your Fyers API access."
        )

    async def chart(self, symbol: str, interval: str = "5m", limit: int = 120) -> Dict[str, Any]:
        """Fetch OHLCV candles from Fyers.

        TODO: Implement Fyers v3 history endpoint mapping.
        Expected behavior: return dict with candles and quote fields, matching YahooClient.chart().
        """
        self._require_configured()
        symbol = symbol.strip().upper()
        _ = self.normalize_symbol(symbol)

        # TODO: Replace with real Fyers history call.
        # Example endpoint pattern (verify against current Fyers docs before enabling):
        # payload = await self._request_json("/data/history", {...})
        # Build candles [{t,o,h,l,c,v}, ...] and include quote fields + "interval".
        logger.warning("Fyers chart skeleton called; live Fyers candle mapping is not implemented yet.")
        raise FyersError(
            "Fyers provider skeleton is configured, but chart mapping is not implemented yet. "
            "Complete services/fyers_client.py chart() using your Fyers API access."
        )


fyers = FyersClient()
