"""User registration, login, and interview history endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.storage import sessions as store

router = APIRouter()


class UserIn(BaseModel):
    user_id: str | None = None
    display_name: str | None = None


class AuthIn(BaseModel):
    email: str
    password: str
    display_name: str | None = None


def _token_from_header(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="请先登录")
    return authorization.split(" ", 1)[1].strip()


def require_user(authorization: str | None = Header(None)) -> dict[str, str]:
    token = _token_from_header(authorization)
    user = store.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return user


@router.post("/users/ensure")
def ensure_user(payload: UserIn):
    return store.ensure_user(payload.user_id, payload.display_name)


@router.post("/auth/register")
def register(payload: AuthIn):
    try:
        user = store.create_user(payload.email, payload.password, payload.display_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = store.create_token(user["id"])
    return {"token": token, "user": user}


@router.post("/auth/login")
def login(payload: AuthIn):
    user = store.authenticate_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    token = store.create_token(user["id"])
    return {"token": token, "user": user}


@router.get("/auth/me")
def me(authorization: str | None = Header(None)):
    return require_user(authorization)


@router.post("/auth/logout")
def logout(authorization: str | None = Header(None)):
    token = _token_from_header(authorization)
    store.delete_token(token)
    return {"ok": True}


@router.get("/users/me/sessions")
def my_sessions(authorization: str | None = Header(None)):
    user = require_user(authorization)
    return {"items": store.list_user_sessions(user["id"])}
