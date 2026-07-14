"""Password hashing (bcrypt) + JWT access/refresh tokens (PyJWT).

Access tokens are short-lived and sent as `Authorization: Bearer`. Refresh tokens are
longer-lived; a hash of each is stored server-side (auth_sessions) so they can be revoked.
"""
from __future__ import annotations

import hashlib
import os
import time
import uuid

import bcrypt
import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-secret-change-in-production")
JWT_ALG = "HS256"
ACCESS_TTL = int(os.getenv("ACCESS_TTL", "1800"))              # 30 min
REFRESH_TTL = int(os.getenv("REFRESH_TTL", str(7 * 86400)))    # 7 days


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


def create_access_token(user_id: str, email: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": user_id, "email": email, "type": "access", "iat": now, "exp": now + ACCESS_TTL},
        JWT_SECRET, algorithm=JWT_ALG,
    )


def create_refresh_token(user_id: str) -> tuple[str, float]:
    now = int(time.time())
    exp = now + REFRESH_TTL
    token = jwt.encode(
        {"sub": user_id, "type": "refresh", "jti": uuid.uuid4().hex, "iat": now, "exp": exp},
        JWT_SECRET, algorithm=JWT_ALG,
    )
    return token, float(exp)


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
