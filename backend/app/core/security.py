from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.core.errors import Unauthenticated

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return password_hash.verify(password, hashed)
    except Exception:
        return False


def create_access_token(
    *,
    user_id: uuid.UUID,
    role: str,
    expires_delta: timedelta | None = None,
) -> tuple[str, int]:
    settings = get_settings()
    now = datetime.now(UTC)
    expires = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, int(expires.total_seconds())


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise Unauthenticated("Invalid or expired access token") from exc
    if payload.get("type") != "access":
        raise Unauthenticated("Invalid token type")
    return payload


def generate_refresh_token() -> tuple[str, str, str]:
    raw = secrets.token_urlsafe(48)
    jti = uuid.uuid4().hex
    return raw, hash_refresh_token(raw), jti


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def constant_time_compare(left: str, right: str) -> bool:
    return secrets.compare_digest(left, right)
