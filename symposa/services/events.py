"""Conversation event mirror (cross-channel transcript)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from symposa.db.models import ConversationEvent
from symposa.db.session import set_rls_context
from symposa.services.conversations import get_conversation


def append_event(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
    *,
    channel: str,
    direction: str,
    role: str,
    content_text: Optional[str] = None,
    content_json: Optional[Dict[str, Any]] = None,
    tool_metadata: Optional[Dict[str, Any]] = None,
) -> ConversationEvent:
    set_rls_context(session, str(company_id), str(user_id))
    if get_conversation(session, company_id, user_id, conversation_id) is None:
        raise ValueError("conversation not found")
    ev = ConversationEvent(
        conversation_id=conversation_id,
        channel=channel,
        direction=direction,
        role=role,
        content_text=content_text,
        content_json=content_json,
        tool_metadata=tool_metadata,
    )
    session.add(ev)
    session.flush()
    return ev


def list_events(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
    *,
    after: Optional[datetime] = None,
    limit: int = 100,
) -> List[ConversationEvent]:
    set_rls_context(session, str(company_id), str(user_id))
    if get_conversation(session, company_id, user_id, conversation_id) is None:
        return []
    q = (
        select(ConversationEvent)
        .where(ConversationEvent.conversation_id == conversation_id)
        .order_by(ConversationEvent.created_at.asc())
        .limit(limit)
    )
    if after is not None:
        q = q.where(ConversationEvent.created_at > after)
    return list(session.scalars(q))
