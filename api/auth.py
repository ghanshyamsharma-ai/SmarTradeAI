"""Authentication endpoints."""

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from core.security import create_token, get_current_user
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
    return {"id": user["id"], "email": user["email"], "name": user["name"]}


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterIn) -> Dict[str, Any]:
    try:
        user = await asyncio.to_thread(create_user, payload.email, payload.name, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"user": _public(user), "token": create_token(user)}


@router.post("/login")
async def login(payload: LoginIn) -> Dict[str, Any]:
    user = await asyncio.to_thread(authenticate, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return {"user": _public(user), "token": create_token(user)}


@router.get("/me")
async def me(current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    user = await asyncio.to_thread(get_user, int(current["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    return _public(user)
