"""Redis cache with an automatic in-memory fallback."""

import json
from typing import Any, Optional

from config.settings import settings
from core.logger import logger


class MemoryCache:
    name = "memory"

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def init(self) -> None:
        return None

    async def get(self, key: str) -> Optional[Any]:
        return self._data.get(key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        self._data[key] = value

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def close(self) -> None:
        self._data.clear()


class RedisCache:
    name = "redis"

    def __init__(self, url: str) -> None:
        self.url = url
        self._redis: Any = None

    async def init(self) -> None:
        import redis.asyncio as redis  # type: ignore

        self._redis = redis.from_url(self.url, decode_responses=True)
        await self._redis.ping()

    async def get(self, key: str) -> Optional[Any]:
        raw = await self._redis.get(key)
        return json.loads(raw) if raw else None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        raw = json.dumps(value, default=str)
        if ttl:
            await self._redis.setex(key, ttl, raw)
        else:
            await self._redis.set(key, raw)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()


_cache: Any = None


async def get_cache() -> Any:
    global _cache
    if _cache is not None:
        return _cache
    if settings.REDIS_URL:
        try:
            candidate = RedisCache(settings.REDIS_URL)
            await candidate.init()
            _cache = candidate
            logger.info("Redis cache connected")
            return _cache
        except Exception as exc:
            logger.warning(f"Redis cache unavailable, using in-memory cache: {exc}")
    _cache = MemoryCache()
    await _cache.init()
    return _cache


async def close_cache() -> None:
    global _cache
    if _cache is not None:
        try:
            await _cache.close()
        except Exception:
            pass
        _cache = None


def cache_status() -> dict[str, Any]:
    return {
        "backend": _cache.name if _cache else "not_initialised",
        "configured": bool(settings.REDIS_URL),
        "active": _cache is not None,
    }
