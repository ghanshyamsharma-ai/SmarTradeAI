"""Async Yahoo Finance client.

Live market data only. The chart endpoint is used for OHLCV history and the
spark endpoint is used for one-request batch quotes. No simulated fallback is
ever returned: failures surface as explicit errors.
"""

import asyncio
import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote as urlquote
from zoneinfo import ZoneInfo

import httpx

from config.settings import settings
from core.logger import logger

IST = ZoneInfo("Asia/Kolkata")

INTERVAL_MAP = {
    "1m": "1m", "2m": "2m", "5m": "5m", "15m": "15m",
    "30m": "30m", "1h": "60m", "60m": "60m", "1d": "1d", "1wk": "1wk",
}
RANGE_MAP = {
    "1m": "1d", "2m": "1d", "5m": "5d", "15m": "1mo",
    "30m": "1mo", "1h": "1y", "60m": "1y", "1d": "5y", "1wk": "max",
}
HOSTS = (
    "https://query1.finance.yahoo.com",
    "https://query2.finance.yahoo.com",
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class YahooError(Exception):
    """Raised when Yahoo Finance cannot serve a requested series."""


class YahooClient:
    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: Dict[Any, Tuple[float, Any]] = {}
        self._lock = asyncio.Lock()
        # Yahoo rate-limits aggressive concurrent polling; keep it conservative.
        self._sem = asyncio.Semaphore(2)

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.REQUEST_TIMEOUT_SECONDS),
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json,text/plain,*/*",
                    "Accept-Language": "en-IN,en;q=0.9",
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
        if s.startswith("^") or "." in s:
            return s
        return f"{s}.NS"

    async def _request(
        self, path: str, params: Dict[str, Any], cache_key: Any, ttl: int
    ) -> Dict[str, Any]:
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] < ttl:
            return cached[1]

        async with self._lock:
            cached = self._cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < ttl:
                return cached[1]

            last_error: Optional[YahooError] = None
            for attempt in range(3):
                host = HOSTS[attempt % len(HOSTS)]
                try:
                    async with self._sem:
                        client = await self._http()
                        response = await client.get(host + path, params=params)
                    if response.status_code == 200:
                        payload = response.json()
                        self._cache[cache_key] = (time.monotonic(), payload)
                        return payload
                    if response.status_code == 429:
                        last_error = YahooError(
                            "Yahoo Finance rate limit reached. Please retry in a few seconds."
                        )
                    elif response.status_code == 404:
                        last_error = YahooError(
                            f"Yahoo Finance has no data for {params.get('symbols') or path.split('/')[-1]}"
                        )
                    else:
                        last_error = YahooError(
                            f"Yahoo Finance returned HTTP {response.status_code}"
                        )
                except YahooError as exc:
                    last_error = exc
                except Exception as exc:
                    logger.error(f"Yahoo request failed ({path}): {exc}")
                    last_error = YahooError(f"Yahoo Finance unavailable: {exc}")

                if attempt < 2:
                    await asyncio.sleep(1.2 * (attempt + 1) + random.random() * 0.4)

            raise last_error or YahooError("Yahoo Finance request failed")

    @staticmethod
    def _quote_from_meta(meta: Dict[str, Any], symbol: Optional[str] = None) -> Dict[str, Any]:
        sym = symbol or meta.get("symbol") or ""
        price = float(meta.get("regularMarketPrice") or 0.0)
        prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or price or 1.0)
        change = meta.get("regularMarketChange")
        change = float(change) if change is not None else price - prev
        pct = meta.get("regularMarketChangePercent")
        pct = float(pct) if pct is not None else (change / prev * 100 if prev else 0.0)
        market_time = meta.get("regularMarketTime") or time.time()
        return {
            "symbol": sym,
            "name": meta.get("longName") or meta.get("shortName") or sym,
            "exchange": meta.get("fullExchangeName") or meta.get("exchangeName") or "NSE",
            "currency": meta.get("currency") or "INR",
            "price": round(price, 2),
            "change": round(change, 2),
            "change_pct": round(pct, 2),
            "previous_close": round(prev, 2),
            "day_high": round(float(meta.get("regularMarketDayHigh") or price), 2),
            "day_low": round(float(meta.get("regularMarketDayLow") or price), 2),
            "volume": int(meta.get("regularMarketVolume") or 0),
            "market_time": datetime.fromtimestamp(float(market_time), IST).isoformat(timespec="seconds"),
            "interval": "quote",
            "delay_note": "Yahoo Finance · NSE quotes may be delayed ~15 minutes",
        }

    async def chart(self, symbol: str, interval: str = "5m", limit: int = 120) -> Dict[str, Any]:
        symbol = self.normalize_symbol(symbol)
        interval = INTERVAL_MAP.get(interval, "5m")
        range_ = RANGE_MAP.get(interval, "5d")
        key = ("chart", symbol, interval, range_)
        payload = await self._request(
            f"/v8/finance/chart/{urlquote(symbol, safe='')}",
            {"interval": interval, "range": range_, "includePrePost": "false"},
            key,
            settings.CANDLE_CACHE_TTL_SECONDS,
        )

        chart = payload.get("chart") or {}
        if chart.get("error"):
            desc = chart["error"].get("description") or chart["error"].get("code")
            raise YahooError(f"Yahoo error for {symbol}: {desc}")
        results = chart.get("result") or []
        if not results:
            raise YahooError(f"No result for {symbol}")
        result = results[0]
        meta = result.get("meta") or {}
        timestamps = result.get("timestamp") or []
        quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]

        candles: List[Dict[str, Any]] = []
        for i, ts in enumerate(timestamps):
            try:
                o = quotes["open"][i]
                h = quotes["high"][i]
                l = quotes["low"][i]
                c = quotes["close"][i]
            except (KeyError, IndexError, TypeError):
                continue
            if None in (o, h, l, c):
                continue
            dt = datetime.fromtimestamp(float(ts), IST)
            label = dt.strftime("%d %b %H:%M") if interval in ("1d", "1wk") else dt.strftime("%H:%M")
            candles.append({
                "t": label,
                "o": round(float(o), 2), "h": round(float(h), 2),
                "l": round(float(l), 2), "c": round(float(c), 2),
                "v": int(quotes.get("volume", [0] * len(timestamps))[i] or 0),
            })
        if not candles:
            raise YahooError(f"No tradable candles returned for {symbol}")

        quote = self._quote_from_meta(meta, symbol)
        # For historical chart ranges Yahoo may omit day high/low or volume.
        if not meta.get("regularMarketDayHigh"):
            quote["day_high"] = max(c["h"] for c in candles)
        if not meta.get("regularMarketDayLow"):
            quote["day_low"] = min(c["l"] for c in candles)
        if not meta.get("regularMarketVolume"):
            quote["volume"] = sum(c["v"] for c in candles)
        quote["candles"] = candles[-max(20, min(limit, 500)):]
        quote["interval"] = interval
        return quote

    async def quotes(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Fetch many quotes through Yahoo spark, chunked to avoid symbol caps."""
        normalized = list(dict.fromkeys(self.normalize_symbol(s) for s in symbols))
        if not normalized:
            return []

        collected: Dict[str, Dict[str, Any]] = {}
        # Yahoo silently truncates large symbol lists, so keep requests small.
        for start in range(0, len(normalized), 10):
            chunk = normalized[start:start + 10]
            key = ("spark", tuple(chunk))
            payload = await self._request(
                "/v7/finance/spark",
                {"symbols": ",".join(chunk), "range": "1d", "interval": "5m"},
                key,
                settings.CACHE_TTL_SECONDS,
            )
            spark = payload.get("spark") or {}
            if spark.get("error"):
                raise YahooError(f"Yahoo spark error: {spark['error']}")
            for item in spark.get("result") or []:
                response = (item.get("response") or [{}])[0]
                meta = response.get("meta") or {}
                sym = item.get("symbol") or meta.get("symbol")
                if sym and meta:
                    collected[sym] = self._quote_from_meta(meta, sym)

        out = [collected[s] for s in normalized if s in collected]
        if not out:
            raise YahooError("Yahoo returned no quotes for the requested symbols")
        missing = [s for s in normalized if s not in collected]
        if missing:
            logger.warning(f"Yahoo omitted symbols: {', '.join(missing)}")
        return out


yahoo = YahooClient()
