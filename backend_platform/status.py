"""Single status view for the polyglot backend platform."""

from typing import Any, Dict

from config.settings import settings
from backend_platform import cache, events, sql, storage
from database.mongodb import client as mongo_client


def platform_status() -> Dict[str, Any]:
    return {
        "languages": ["Python", "Java", "Node.js"],
        "frameworks": {
            "FastAPI": "core api",
            "Django": "admin sidecar" if settings.DJANGO_ADMIN_URL else "admin sidecar (optional)",
            "Spring Boot": "stream sidecar" if settings.SPRING_STREAM_URL else "stream sidecar (optional)",
            "Express.js": "gateway sidecar" if settings.NODE_GATEWAY_URL else "gateway sidecar (optional)",
        },
        "databases": {
            "sql": sql.sql_status(),
            "mongodb": {
                "configured": bool(settings.MONGO_URI),
                "active": mongo_client is not None,
            },
        },
        "cache": cache.cache_status(),
        "apis": ["REST API", "WebSocket API"],
        "authentication": {
            "jwt": True,
            "oauth2": bool(settings.oauth_clients),
        },
        "streaming": events.event_bus_status(),
        "storage": storage.storage_status(),
        "deployment": ["Docker", "AWS", "Azure"],
    }
