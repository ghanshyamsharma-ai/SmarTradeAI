"""OAuth 2.0 client-credentials token endpoint."""

import hmac
from typing import Any, Dict
from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException, Request

from config.settings import settings
from core.security import TOKEN_TTL_SECONDS, create_service_token, decode_token

router = APIRouter(prefix="/api/oauth", tags=["oauth"])

DEFAULT_SCOPES = {"market:read", "market:stream", "signals:read", "catalog:read"}
PRIVILEGED_CLIENT = "admin"
ALL_SCOPES = DEFAULT_SCOPES | {"*"}


async def _payload(request: Request) -> Dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "json" in content_type:
        try:
            return await request.json()
        except Exception:
            return {}
    raw = (await request.body()).decode("utf-8", errors="replace")
    return dict(parse_qsl(raw, keep_blank_values=True))


@router.post("/token")
async def token(request: Request) -> Dict[str, Any]:
    data = await _payload(request)
    if data.get("grant_type") != "client_credentials":
        raise HTTPException(status_code=400, detail="Only client_credentials is supported")
    client_id = str(data.get("client_id", ""))
    client_secret = str(data.get("client_secret", ""))
    expected = settings.oauth_clients.get(client_id)
    if not expected or not hmac.compare_digest(client_secret, expected):
        raise HTTPException(status_code=401, detail="Invalid client credentials")

    requested = str(data.get("scope", "")).split()
    allowed = set(ALL_SCOPES) if client_id == PRIVILEGED_CLIENT else DEFAULT_SCOPES
    scopes = requested or sorted(allowed)
    if not set(scopes) <= allowed:
        raise HTTPException(status_code=400, detail="Requested scope is not allowed")
    return {
        "access_token": create_service_token(client_id, scopes),
        "token_type": "Bearer",
        "expires_in": TOKEN_TTL_SECONDS,
        "scope": " ".join(scopes),
    }


@router.post("/introspect")
async def introspect(request: Request) -> Dict[str, Any]:
    data = await _payload(request)
    token_value = str(data.get("token", ""))
    try:
        payload = decode_token(token_value)
    except Exception:
        return {"active": False}
    return {
        "active": True,
        "scope": payload.get("scope", ""),
        "client_id": payload.get("client_id"),
        "sub": payload.get("sub"),
        "exp": payload.get("exp"),
    }
