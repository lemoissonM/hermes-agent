"""Channel identity resolution (WhatsApp phone → Symposa user)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from symposa.db.models import ChannelIdentity, User


def resolve_user_by_channel(
    session: Session,
    company_id: UUID,
    channel: str,
    external_id: str,
) -> Optional[User]:
    row = session.scalar(
        select(ChannelIdentity).where(
            ChannelIdentity.company_id == company_id,
            ChannelIdentity.channel == channel,
            ChannelIdentity.external_id == external_id,
        )
    )
    if row is None:
        return None
    return session.get(User, row.user_id)


def link_channel_identity(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    channel: str,
    external_id: str,
) -> ChannelIdentity:
    existing = session.scalar(
        select(ChannelIdentity).where(
            ChannelIdentity.company_id == company_id,
            ChannelIdentity.channel == channel,
            ChannelIdentity.external_id == external_id,
        )
    )
    if existing:
        if existing.user_id != user_id:
            raise ValueError("external_id already linked to another user")
        return existing
    row = ChannelIdentity(
        company_id=company_id,
        user_id=user_id,
        channel=channel,
        external_id=external_id,
        verified_at=datetime.now(timezone.utc),
    )
    session.add(row)
    if channel != "web":
        web_row = session.scalar(
            select(ChannelIdentity).where(
                ChannelIdentity.company_id == company_id,
                ChannelIdentity.user_id == user_id,
                ChannelIdentity.channel == "web",
            )
        )
        if web_row is None:
            session.add(
                ChannelIdentity(
                    company_id=company_id,
                    user_id=user_id,
                    channel="web",
                    external_id=str(user_id),
                    verified_at=datetime.now(timezone.utc),
                )
            )
    session.flush()
    return row


def canonical_whatsapp_external_id(identifier: str) -> str:
    try:
        from gateway.whatsapp_identity import canonical_whatsapp_identifier

        return canonical_whatsapp_identifier(identifier) or identifier
    except Exception:
        return identifier.split("@")[0] if "@" in identifier else identifier
