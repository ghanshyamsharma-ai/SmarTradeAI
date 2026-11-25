"""Authentication endpoints."""

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from core.security import create_token, get_current_user
from database.profile import add_activity, create_session, ensure_profile, get_profile
from database.users import authenticate, create_user, get_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(default="", max_length=80)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def _public(user: Dict[str, Any]) -> Dict[str, Any]:
    profile = get_profile(int(user["id"]))
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "username": profile.get("username", ""),
        "avatar_url": profile.get("avatar_url", ""),
        "membership_plan": profile.get("membership_plan", "Free"),
    }


def _client_meta(request: Request) -> Dict[str, str]:
    ua = (request.headers.get("user-agent") or "")[:300]
    ip = request.client.host if request.client else ""
    device = "Mobile" if any(x in ua.lower() for x in ["android", "iphone", "ipad", "mobile"]) else "Desktop"
    return {"user_agent": ua, "ip_address": ip, "device": device}


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterIn, request: Request) -> Dict[str, Any]:
    try:
        user = await asyncio.to_thread(create_user, payload.email, payload.name, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await asyncio.to_thread(ensure_profile, int(user["id"]), user["email"], user["name"])
    meta = _client_meta(request)
    session = await asyncio.to_thread(create_session, int(user["id"]), "", meta["device"], meta["ip_address"], meta["user_agent"])
    await asyncio.to_thread(add_activity, int(user["id"]), "account", "Account created", f"Registered with {user['email']}", meta["ip_address"])
    token = create_token(user, session_id=session["session_id"])
    return {"user": _public(user), "token": token, "session_id": session["session_id"]}


@router.post("/login")
async def login(payload: LoginIn, request: Request) -> Dict[str, Any]:
    user = await asyncio.to_thread(authenticate, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    await asyncio.to_thread(ensure_profile, int(user["id"]), user["email"], user["name"])
    meta = _client_meta(request)
    session = await asyncio.to_thread(create_session, int(user["id"]), "", meta["device"], meta["ip_address"], meta["user_agent"])
    await asyncio.to_thread(add_activity, int(user["id"]), "security", "Login successful", f"{meta['device']} login", meta["ip_address"])
    token = create_token(user, session_id=session["session_id"])
    return {"user": _public(user), "token": token, "session_id": session["session_id"]}


@router.get("/me")
async def me(current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    user = await asyncio.to_thread(get_user, int(current["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    return _public(user)
