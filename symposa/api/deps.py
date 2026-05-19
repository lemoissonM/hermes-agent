"""FastAPI dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from symposa.auth.jwt import decode_token
from symposa.db.models import User
from symposa.db.session import get_session_factory, set_rls_context

_bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    user_id: UUID
    company_id: UUID
    role: str
    email: str


def get_auth(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    try:
        payload = decode_token(creds.credentials)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    return AuthContext(
        user_id=UUID(payload["sub"]),
        company_id=UUID(payload["company_id"]),
        role=str(payload.get("role", "member")),
        email=str(payload.get("email", "")),
    )


def get_db_user(auth: Annotated[AuthContext, Depends(get_auth)]) -> User:
    factory = get_session_factory()
    session = factory()
    try:
        user = session.get(User, auth.user_id)
        if user is None or user.company_id != auth.company_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        set_rls_context(session, str(auth.company_id), str(auth.user_id))
        return user
    finally:
        session.close()
