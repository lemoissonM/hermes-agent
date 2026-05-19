"""Map Hermes platform session keys to Symposa conversations."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from symposa.db.models import ConversationChannelSession


def upsert_channel_session(
    session: Session,
    conversation_id: UUID,
    platform: str,
    hermes_session_key: str,
    hermes_session_id: str | None = None,
) -> ConversationChannelSession:
    row = session.scalar(
        select(ConversationChannelSession).where(
            ConversationChannelSession.platform == platform,
            ConversationChannelSession.hermes_session_key == hermes_session_key,
        )
    )
    now = datetime.now(timezone.utc)
    if row:
        row.conversation_id = conversation_id
        row.hermes_session_id = hermes_session_id or row.hermes_session_id
        row.last_active_at = now
        session.flush()
        return row
    row = ConversationChannelSession(
        conversation_id=conversation_id,
        platform=platform,
        hermes_session_key=hermes_session_key,
        hermes_session_id=hermes_session_id,
        last_active_at=now,
    )
    session.add(row)
    session.flush()
    return row
