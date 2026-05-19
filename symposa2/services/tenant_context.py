"""Resolve Symposa2 tenant from gateway session sources."""

from __future__ import annotations

import logging
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import select

from symposa.db.models import ChannelIdentity, User
from symposa.db.session import session_scope

logger = logging.getLogger(__name__)

_PLATFORM_CHANNEL = {
    "telegram": "telegram",
    "whatsapp": "whatsapp",
    "slack": "slack",
    "discord": "discord",
    "matrix": "matrix",
    "web": "web",
    "api_server": "web",
}


def resolve_tenant_from_channel(
    platform: str,
    external_id: str,
) -> Optional[Tuple[UUID, UUID]]:
    """Map messaging platform identity to (company_id, user_id)."""
    channel = _PLATFORM_CHANNEL.get(platform.lower(), platform.lower())
    ext = external_id.strip()
    if not ext:
        return None
    try:
        with session_scope() as session:
            row = session.scalar(
                select(ChannelIdentity).where(
                    ChannelIdentity.channel == channel,
                    ChannelIdentity.external_id == ext,
                )
            )
            if row:
                return row.company_id, row.user_id
    except Exception as exc:
        logger.debug("channel identity lookup failed: %s", exc)
    return None


def resolve_tenant_from_session_key(session_key: str) -> Optional[Tuple[UUID, UUID]]:
    """Parse symposa2:company:user:conversation session keys."""
    if not session_key.startswith("symposa2:"):
        return None
    parts = session_key.split(":")
    if len(parts) < 3:
        return None
    try:
        return UUID(parts[1]), UUID(parts[2])
    except ValueError:
        return None


def resolve_tenant_from_user_email(email: str) -> Optional[Tuple[UUID, UUID]]:
    """Best-effort lookup when only email is known (single-company dev setups)."""
    try:
        with session_scope() as session:
            user = session.scalar(select(User).where(User.email == email.lower()))
            if user:
                return user.company_id, user.id
    except Exception as exc:
        logger.debug("email tenant lookup failed: %s", exc)
    return None
