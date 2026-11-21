"""Dependency-free password hashing and signed session tokens."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

PBKDF2_ROUNDS = 210_000
TOKEN_TTL_SECONDS = 60 * 60 * 12
SECRET_FILE = Path(__file__).resolve().parent.parent / "data" / ".jwt_secret"


def _secret_key() -> bytes:
    env = os.getenv("JWT_SECRET")
    if env:
        return env.encode("utf-8")
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(secrets.token_hex(32), encoding="utf-8")
    return SECRET_FILE.read_text(encoding="utf-8").strip().encode("utf-8")


SECRET_KEY = _secret_key()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=True)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign_payload(payload: Dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    head = _b64(json.dumps(header, separators=(",", ":")).encode())
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{head}.{body}".encode()
    signature = _b64(hmac.new(SECRET_KEY, signing_input, hashlib.sha256).digest())
    return f"{head}.{body}.{signature}"


def create_token(user: Dict[str, Any], scopes: Optional[Any] = None) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "name": user.get("name", ""),
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
        "scope": " ".join(scopes or []),
    }
    return _sign_payload(payload)


def create_service_token(client_id: str, scopes: Any) -> str:
    now = int(time.time())
    payload = {
        "sub": client_id,
        "client_id": client_id,
        "token_use": "service",
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
        "scope": " ".join(scopes or []),
    }
    return _sign_payload(payload)


def decode_token(token: str) -> Dict[str, Any]:
    try:
        head, body, signature = token.split(".")
        expected = _b64(hmac.new(SECRET_KEY, f"{head}.{body}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        payload = json.loads(_unb64(body))
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("token expired")
        return payload
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    return decode_token(token)


def require_scope(required: str):
    """FastAPI dependency enforcing an OAuth 2.0 scope.

    User sessions and legacy tokens without scopes keep full access; only
    service tokens that explicitly carry scopes are restricted.
    """

    async def _checker(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
        payload = decode_token(token)
        scope_value = str(payload.get("scope", "")).strip()
        if not scope_value:  # user sessions and legacy tokens keep full access
            return payload
        scopes = set(scope_value.split())
        if "*" in scopes or required in scopes:
            return payload
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required scope: {required}",
        )

    return _checker
