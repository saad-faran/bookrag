"""BookRAG Authentication microservice (standalone FastAPI app, default port 8001).

Endpoints:
  POST /auth/register   {email, password, name?}  -> tokens + user
  POST /auth/login      {email, password}          -> tokens + user
  POST /auth/refresh    {refresh_token}            -> new access token
  GET  /auth/me         (Bearer)                   -> user
  POST /auth/logout     {refresh_token}            -> revoke session
"""
from __future__ import annotations

import re
import time

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from auth.security import (
    ACCESS_TTL, create_access_token, create_refresh_token, decode_token,
    hash_password, token_hash, verify_password,
)
from db.base import init_db, session_scope
from db.models import AuthSession, User
from server.events import log_event

app = FastAPI(title="BookRAG Auth Service")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@app.on_event("startup")
def _startup() -> None:
    init_db()


class RegisterIn(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


def _user_public(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name}


def _issue(user: User, user_agent: str = "") -> dict:
    access = create_access_token(user.id, user.email)
    refresh, exp = create_refresh_token(user.id)
    with session_scope() as s:
        s.add(AuthSession(user_id=user.id, refresh_hash=token_hash(refresh),
                          expires_at=exp, user_agent=user_agent[:255]))
    return {"access_token": access, "refresh_token": refresh,
            "token_type": "bearer", "expires_in": ACCESS_TTL, "user": _user_public(user)}


@app.post("/auth/register")
def register(body: RegisterIn, user_agent: str = Header(default="")):
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "invalid email")
    if len(body.password) < 6:
        raise HTTPException(400, "password must be at least 6 characters")
    with session_scope() as s:
        if s.query(User).filter(User.email == email).first():
            raise HTTPException(409, "email already registered")
        user = User(email=email, name=body.name.strip() or email.split("@")[0],
                    password_hash=hash_password(body.password))
        s.add(user)
        s.flush()
        s.expunge(user)
    log_event("auth.register", user_id=user.id, payload={"email": email})
    return _issue(user, user_agent)


@app.post("/auth/login")
def login(body: LoginIn, user_agent: str = Header(default="")):
    email = body.email.strip().lower()
    with session_scope() as s:
        user = s.query(User).filter(User.email == email).first()
        if not user or not verify_password(body.password, user.password_hash):
            log_event("auth.login_failed", level="warn", payload={"email": email})
            raise HTTPException(401, "invalid email or password")
        s.expunge(user)
    log_event("auth.login", user_id=user.id, payload={"email": email})
    return _issue(user, user_agent)


@app.post("/auth/refresh")
def refresh(body: RefreshIn):
    try:
        payload = decode_token(body.refresh_token)
        assert payload.get("type") == "refresh"
    except Exception:
        raise HTTPException(401, "invalid refresh token")
    rh = token_hash(body.refresh_token)
    with session_scope() as s:
        sess = s.query(AuthSession).filter(AuthSession.refresh_hash == rh).first()
        if not sess or sess.revoked or sess.expires_at < time.time():
            raise HTTPException(401, "refresh session expired or revoked")
        user = s.query(User).filter(User.id == payload["sub"]).first()
        if not user:
            raise HTTPException(401, "user not found")
        access = create_access_token(user.id, user.email)
    return {"access_token": access, "token_type": "bearer", "expires_in": ACCESS_TTL}


@app.post("/auth/logout")
def logout(body: RefreshIn):
    with session_scope() as s:
        sess = s.query(AuthSession).filter(AuthSession.refresh_hash == token_hash(body.refresh_token)).first()
        if sess:
            sess.revoked = True
    return {"ok": True}


@app.get("/auth/me")
def me(authorization: str = Header(default="")):
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    try:
        payload = decode_token(authorization.split(" ", 1)[1])
        assert payload.get("type") == "access"
    except Exception:
        raise HTTPException(401, "invalid or expired token")
    with session_scope() as s:
        user = s.query(User).filter(User.id == payload["sub"]).first()
        if not user:
            raise HTTPException(404, "user not found")
        return _user_public(user)


@app.get("/health")
def health():
    return {"ok": True, "service": "auth"}
