"""User profile and account management endpoints."""

import asyncio
import base64
import hashlib
import hmac
import json
import struct
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field

from core.security import get_current_user
from database.profile import (
    add_activity,
    delete_account,
    ensure_profile,
    get_profile,
    list_activity,
    list_connected_services,
    list_sessions,
    revoke_all_sessions,
    revoke_connected_service,
    revoke_session,
    set_account_active,
    update_notifications,
    update_preferences,
    update_profile,
    upsert_connected_service,
)
from database.users import get_user, update_password

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _uid(current: Dict[str, Any]) -> int:
    return int(current["sub"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    username: Optional[str] = Field(default=None, max_length=40)
    email: Optional[EmailStr] = None
    mobile: Optional[str] = Field(default=None, max_length=30)
    country: Optional[str] = Field(default=None, max_length=80)
    timezone: Optional[str] = Field(default=None, max_length=80)
    bio: Optional[str] = Field(default=None, max_length=300)
    avatar_url: Optional[str] = Field(default=None, max_length=500000)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class PrefsUpdate(BaseModel):
    section: str
    preferences: Dict[str, Any]


class NotifUpdate(BaseModel):
    preferences: Dict[str, bool]


class ServiceUpsert(BaseModel):
    service_type: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    config: Dict[str, Any] = Field(default_factory=dict)
    secret_hint: str = Field(default="", max_length=40)


class ConfirmAction(BaseModel):
    confirm: str = Field(min_length=1, max_length=120)


@router.get("")
async def me_profile(current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    uid = _uid(current)
    profile = await asyncio.to_thread(get_profile, uid)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("")
async def save_profile(payload: ProfileUpdate, request: Request, current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    uid = _uid(current)
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        profile = await asyncio.to_thread(update_profile, uid, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await asyncio.to_thread(add_activity, uid, "profile", "Profile updated", ", ".join(data.keys()), _ip(request))
    return profile


@router.post("/password")
async def change_password(payload: PasswordChange, request: Request, current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    uid = _uid(current)
    try:
        ok = await asyncio.to_thread(update_password, uid, payload.current_password, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    await asyncio.to_thread(add_activity, uid, "security", "Password changed", "Account password updated", _ip(request))
    return {"ok": True}


@router.get("/preferences")
async def get_preferences(current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    profile = await asyncio.to_thread(get_profile, _uid(current))
    return profile.get("preferences", {})


@router.put("/preferences")
async def save_preferences(payload: PrefsUpdate, request: Request, current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    uid = _uid(current)
    try:
        saved = await asyncio.to_thread(update_preferences, uid, payload.section, payload.preferences)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await asyncio.to_thread(add_activity, uid, "settings", f"{payload.section.title()} preferences updated", payload.section, _ip(request))
    return {"section": payload.section, "preferences": saved}


@router.get("/notifications")
async def get_notifications(current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    profile = await asyncio.to_thread(get_profile, _uid(current))
    return profile.get("notifications", {})


@router.put("/notifications")
async def save_notifications(payload: NotifUpdate, request: Request, current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    uid = _uid(current)
    saved = await asyncio.to_thread(update_notifications, uid, payload.preferences)
    await asyncio.to_thread(add_activity, uid, "settings", "Notification preferences updated", "", _ip(request))
    return saved


@router.get("/sessions")
async def get_sessions(current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    uid = _uid(current)
    sessions = await asyncio.to_thread(list_sessions, uid)
    current_sid = current.get("sid", "")
    for s in sessions:
        s["is_current"] = bool(s.get("is_current")) or (current_sid and s.get("session_id") == current_sid)
    return {"sessions": sessions}


@router.post("/sessions/revoke-all")
async def revoke_sessions(request: Request, current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    uid = _uid(current)
    except_sid = current.get("sid", "")
    count = await asyncio.to_thread(revoke_all_sessions, uid, except_sid)
    await asyncio.to_thread(add_activity, uid, "security", "Logged out other devices", f"Revoked {count} session(s)", _ip(request))
    return {"revoked": count}


@router.post("/sessions/{session_id}/revoke")
async def revoke_one_session(session_id: str, request: Request, current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    uid = _uid(current)
    ok = await asyncio.to_thread(revoke_session, uid, session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    await asyncio.to_thread(add_activity, uid, "security", "Session revoked", session_id[:8], _ip(request))
    return {"ok": True}


@router.get("/activity")
async def get_activity(limit: int = 50, current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    uid = _uid(current)
    items = await asyncio.to_thread(list_activity, uid, limit)
    return {"activity": items}


@router.get("/services")
async def get_services(current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return {"services": await asyncio.to_thread(list_connected_services, _uid(current))}


@router.post("/services")
async def connect_service(payload: ServiceUpsert, request: Request, current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    uid = _uid(current)
    secret_hint = payload.secret_hint
    # Never persist raw secrets; keep only a hint.
    for k in list(payload.config.keys()):
        if any(s in k.lower() for s in ["key", "secret", "token", "password"]):
            val = str(payload.config.pop(k))
            secret_hint = secret_hint or (f"••••{val[-4:]}" if len(val) >= 4 else "configured")
    svc = await asyncio.to_thread(upsert_connected_service, uid, payload.service_type, payload.name, payload.config, secret_hint)
    await asyncio.to_thread(add_activity, uid, "integration", "Connected service updated", payload.name, _ip(request))
    return svc


@router.delete("/services/{service_id}")
async def disconnect_service(service_id: int, request: Request, current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    uid = _uid(current)
    ok = await asyncio.to_thread(revoke_connected_service, uid, service_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Service not found")
    await asyncio.to_thread(add_activity, uid, "integration", "Connected service removed", str(service_id), _ip(request))
    return {"ok": True}


@router.get("/export")
async def export_data(current: Dict[str, Any] = Depends(get_current_user)) -> JSONResponse:
    uid = _uid(current)
    profile = await asyncio.to_thread(get_profile, uid)
    activity = await asyncio.to_thread(list_activity, uid, 200)
    sessions = await asyncio.to_thread(list_sessions, uid)
    services = await asyncio.to_thread(list_connected_services, uid)
    payload = {
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "profile": profile,
        "activity": activity,
        "sessions": [{k: v for k, v in s.items() if k != "session_id"} for s in sessions],
        "connected_services": services,
    }
    return JSONResponse(content=payload, headers={"Content-Disposition": f'attachment; filename="smartraderai-profile-{uid}.json"'})


@router.post("/deactivate")
async def deactivate(payload: ConfirmAction, request: Request, current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    uid = _uid(current)
    if payload.confirm.strip().upper() != "DEACTIVATE":
        raise HTTPException(status_code=400, detail="Type DEACTIVATE to confirm")
    await asyncio.to_thread(set_account_active, uid, False)
    await asyncio.to_thread(add_activity, uid, "security", "Account deactivated", "", _ip(request))
    return {"ok": True}


@router.post("/reactivate")
async def reactivate(request: Request, current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    uid = _uid(current)
    await asyncio.to_thread(set_account_active, uid, True)
    await asyncio.to_thread(add_activity, uid, "security", "Account reactivated", "", _ip(request))
    return {"ok": True}


@router.delete("")
async def remove_account(payload: ConfirmAction, request: Request, current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    uid = _uid(current)
    user = await asyncio.to_thread(get_user, uid)
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")
    expected = f"DELETE {user['email']}"
    if payload.confirm.strip() != expected:
        raise HTTPException(status_code=400, detail=f"Type '{expected}' to confirm")
    await asyncio.to_thread(add_activity, uid, "security", "Account deletion requested", "Account deleted by user", _ip(request))
    await asyncio.to_thread(delete_account, uid)
    return {"ok": True}
