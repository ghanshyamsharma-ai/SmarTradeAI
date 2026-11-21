"""Event publishing with Kafka, Redis Streams or an in-process bus."""

import json
from collections import deque
from typing import Any, Deque, Optional

from config.settings import settings
from core.logger import logger


class InMemoryBus:
    name = "memory"

    def __init__(self) -> None:
        self._events: Deque[dict[str, Any]] = deque(maxlen=200)

    async def init(self) -> None:
        return None

    async def publish(self, topic: str, payload: Any) -> None:
        self._events.append({"topic": topic, "payload": payload})

    async def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        return list(self._events)[-limit:]

    async def close(self) -> None:
        self._events.clear()


class RedisStreamBus:
    name = "redis_streams"

    def __init__(self, url: str, stream: str) -> None:
        self.url = url
        self.stream = stream
        self._redis: Any = None

    async def init(self) -> None:
        import redis.asyncio as redis  # type: ignore

        self._redis = redis.from_url(self.url, decode_responses=True)
        await self._redis.ping()

    async def publish(self, topic: str, payload: Any) -> None:
        await self._redis.xadd(
            self.stream,
            {"topic": topic, "payload": json.dumps(payload, default=str)},
            maxlen=10000,
            approximate=True,
        )

    async def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        entries = await self._redis.xrevrange(self.stream, count=limit)
        return [{"id": eid, **fields} for eid, fields in entries]

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()


class KafkaBus:
    name = "kafka"

    def __init__(self, bootstrap: str) -> None:
        self.bootstrap = bootstrap
        self._producer: Any = None

    async def init(self) -> None:
        from aiokafka import AIOKafkaProducer  # type: ignore

        self._producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap)
        await self._producer.start()

    async def publish(self, topic: str, payload: Any) -> None:
        await self._producer.send_and_wait(
            topic, json.dumps(payload, default=str).encode("utf-8")
        )

    async def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        return [{"note": "Kafka history requires a consumer", "limit": limit}]

    async def close(self) -> None:
        if self._producer is not None:
            await self._producer.stop()


_bus: Any = None


async def get_bus() -> Any:
    global _bus
    if _bus is not None:
        return _bus
    mode = settings.EVENT_BUS.strip().lower()
    try:
        if mode == "kafka" and settings.KAFKA_BOOTSTRAP_SERVERS:
            candidate = KafkaBus(settings.KAFKA_BOOTSTRAP_SERVERS)
            await candidate.init()
            _bus = candidate
        elif mode == "redis" and settings.REDIS_URL:
            candidate = RedisStreamBus(settings.REDIS_URL, settings.REDIS_STREAM)
            await candidate.init()
            _bus = candidate
        else:
            raise RuntimeError("using in-process event bus")
    except Exception as exc:
        logger.warning(f"Event bus '{mode}' unavailable, using in-memory bus: {exc}")
        _bus = InMemoryBus()
        await _bus.init()
    return _bus


async def publish(topic: str, payload: Any) -> None:
    bus = await get_bus()
    try:
        await bus.publish(topic, payload)
    except Exception as exc:
        logger.warning(f"Event publish failed ({topic}): {exc}")


async def recent(limit: int = 20) -> list[dict[str, Any]]:
    bus = await get_bus()
    return await bus.recent(limit)


async def close_bus() -> None:
    global _bus
    if _bus is not None:
        try:
            await _bus.close()
        except Exception:
            pass
        _bus = None


def event_bus_status() -> dict[str, Any]:
    return {
        "configured": settings.EVENT_BUS,
        "backend": _bus.name if _bus else "not_initialised",
        "active": _bus is not None,
        "kafka_configured": bool(settings.KAFKA_BOOTSTRAP_SERVERS),
        "redis_stream_configured": bool(settings.REDIS_URL),
    }
