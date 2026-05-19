"""Conversation and active-channel pointer management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from symposa.db.models import ChannelActiveConversation, Conversation
from symposa.db.session import set_rls_context


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def list_conversations(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    *,
    include_archived: bool = False,
) -> List[Conversation]:
    set_rls_context(session, str(company_id), str(user_id))
    q = select(Conversation).where(
        Conversation.company_id == company_id,
        Conversation.user_id == user_id,
    )
    if not include_archived:
        q = q.where(Conversation.archived_at.is_(None))
    q = q.order_by(Conversation.updated_at.desc())
    return list(session.scalars(q))


def create_conversation(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    title: str = "New conversation",
) -> Conversation:
    set_rls_context(session, str(company_id), str(user_id))
    conv = Conversation(
        company_id=company_id,
        user_id=user_id,
        title=title,
    )
    session.add(conv)
    session.flush()
    return conv


def get_conversation(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
) -> Optional[Conversation]:
    set_rls_context(session, str(company_id), str(user_id))
    return session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.company_id == company_id,
            Conversation.user_id == user_id,
        )
    )


def set_active_conversation(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    channel: str,
    conversation_id: UUID,
) -> ChannelActiveConversation:
    set_rls_context(session, str(company_id), str(user_id))
    conv = get_conversation(session, company_id, user_id, conversation_id)
    if conv is None:
        raise ValueError("conversation not found")
    existing = session.scalar(
        select(ChannelActiveConversation).where(
            ChannelActiveConversation.company_id == company_id,
            ChannelActiveConversation.user_id == user_id,
            ChannelActiveConversation.channel == channel,
        )
    )
    if existing:
        existing.conversation_id = conversation_id
        existing.updated_at = _utcnow()
        session.flush()
        return existing
    row = ChannelActiveConversation(
        company_id=company_id,
        user_id=user_id,
        channel=channel,
        conversation_id=conversation_id,
    )
    session.add(row)
    session.flush()
    return row


def get_active_conversation_id(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    channel: str,
) -> Optional[UUID]:
    set_rls_context(session, str(company_id), str(user_id))
    row = session.scalar(
        select(ChannelActiveConversation).where(
            ChannelActiveConversation.company_id == company_id,
            ChannelActiveConversation.user_id == user_id,
            ChannelActiveConversation.channel == channel,
        )
    )
    return row.conversation_id if row else None


def get_or_create_active_conversation(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    channel: str,
    *,
    default_title: str = "WhatsApp",
) -> Conversation:
    """Return active conversation for channel, creating one if missing."""
    cid = get_active_conversation_id(session, company_id, user_id, channel)
    if cid:
        conv = get_conversation(session, company_id, user_id, cid)
        if conv is not None:
            return conv
    conv = create_conversation(session, company_id, user_id, title=default_title)
    set_active_conversation(session, company_id, user_id, channel, conv.id)
    return conv
