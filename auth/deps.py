"""FastAPI dependency that authenticates a request from its Bearer access token.

Used by the core-api to protect every chat/project endpoint. Validation is local
(shared JWT secret) — no network call to the auth service per request.
"""
from __future__ import annotations

from fastapi import Header, HTTPException

from auth.security import decode_token


def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="wrong token type")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="malformed token")
    return sub
