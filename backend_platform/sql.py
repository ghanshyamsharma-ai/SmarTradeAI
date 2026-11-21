"""Optional SQLAlchemy layer for PostgreSQL / MySQL / SQLite."""

from typing import Any, Optional

from config.settings import settings
from core.logger import logger

_engine: Any = None
_async_session: Any = None
_market_tick_model: Any = None


def _driver_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("mysql://"):
        return url.replace("mysql://", "mysql+aiomysql://", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


async def init_sql() -> bool:
    """Create tables when DATABASE_URL is configured. Never fail startup."""
    global _engine, _async_session, _market_tick_model
    if not settings.DATABASE_URL:
        return False
    try:
        from sqlalchemy import Column, DateTime, Float, Integer, String
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.orm import declarative_base

        Base = declarative_base()

        class MarketTick(Base):  # type: ignore[valid-type,misc]
            __tablename__ = "market_ticks"
            id = Column(Integer, primary_key=True, index=True)
            symbol = Column(String(32), index=True, nullable=False)
            price = Column(Float, nullable=False)
            change_pct = Column(Float, default=0.0)
            market_time = Column(String(40), default="")
            received_at = Column(DateTime, server_default=None)

        _market_tick_model = MarketTick
        _engine = create_async_engine(
            _driver_url(settings.DATABASE_URL), echo=settings.SQL_ECHO, future=True
        )
        _async_session = async_sessionmaker(_engine, expire_on_commit=False)
        async with _engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        logger.info("SQL database connected and tables verified")
        return True
    except Exception as exc:
        logger.warning(f"SQL database unavailable, using existing local stores: {exc}")
        _engine = None
        _async_session = None
        return False


async def store_tick(symbol: str, price: float, change_pct: float, market_time: str) -> bool:
    if _async_session is None or _market_tick_model is None:
        return False
    from datetime import datetime

    try:
        async with _async_session() as session:
            session.add(
                _market_tick_model(
                    symbol=symbol,
                    price=price,
                    change_pct=change_pct,
                    market_time=market_time,
                    received_at=datetime.utcnow(),
                )
            )
            await session.commit()
        return True
    except Exception as exc:
        logger.warning(f"SQL tick write skipped: {exc}")
        return False


async def close_sql() -> None:
    global _engine, _async_session
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _async_session = None


def sql_status() -> dict[str, Any]:
    kind = "none"
    url = settings.DATABASE_URL
    if url.startswith("postgres"):
        kind = "postgresql"
    elif url.startswith("mysql"):
        kind = "mysql"
    elif url.startswith("sqlite"):
        kind = "sqlite"
    return {
        "configured": bool(url),
        "kind": kind,
        "active": _engine is not None,
    }
