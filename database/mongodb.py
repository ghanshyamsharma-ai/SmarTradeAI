from urllib.parse import urlparse

from motor.motor_asyncio import AsyncIOMotorClient
from config.settings import settings
from core.logger import logger


def _create_client():
    """Create a Mongo client only for a valid URI. Mongo is optional."""
    uri = (settings.MONGO_URI or "").strip()
    if not uri:
        logger.warning("MongoDB offline - no MONGO_URI configured; optional persistence disabled")
        return None
    try:
        parsed = urlparse(uri)
        if parsed.scheme not in ("mongodb", "mongodb+srv") or not parsed.hostname:
            raise ValueError("unsupported or incomplete MONGO_URI")
        if parsed.username and not parsed.password:
            raise ValueError("MONGO_URI has a username but no password")
        return AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    except Exception as exc:
        # Never log the URI itself — it can contain credentials.
        logger.warning(f"MongoDB offline - invalid MONGO_URI ({exc}); optional persistence disabled")
        return None


client = _create_client()
db = client[settings.DATABASE_NAME] if client else None


async def connect_to_mongodb():
    if client is None:
        return
    try:
        await client.admin.command("ping")
        logger.info("MongoDB Connected Successfully")
        print("[OK] MongoDB Connected Successfully")
    except Exception as e:
        logger.warning(f"MongoDB offline - optional persistence disabled: {e}")
        print("[INFO] MongoDB offline - optional persistence disabled")


async def close_mongodb_connection():
    if client is not None:
        client.close()
        logger.info("MongoDB Connection Closed")


def get_database():
    return db
