"""JWT issue and validation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import UUID

import jwt

from symposa.config import get_settings


def create_access_token(
    user_id: UUID,
    company_id: UUID,
    role: str,
    email: str,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "company_id": str(company_id),
        "role": role,
        "email": email,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: UUID, company_id: UUID) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "company_id": str(company_id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_refresh_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Dict[str, Any]:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
