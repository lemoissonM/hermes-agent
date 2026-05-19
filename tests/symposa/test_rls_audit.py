"""RLS-oriented isolation checks (SQLite mirrors policy intent; Postgres enforces RLS)."""

from __future__ import annotations

from uuid import uuid4

from symposa.db.models import Conversation, ConversationEvent
from symposa.services.conversations import create_conversation
from symposa.services.events import list_events


def test_user_cannot_read_other_users_events(symposa_db):
    session, company, user_a, user_b = symposa_db
    conv_a = create_conversation(session, company.id, user_a.id, title="A thread")
    conv_b = create_conversation(session, company.id, user_b.id, title="B thread")
    session.add(
        ConversationEvent(
            id=uuid4(),
            conversation_id=conv_a.id,
            channel="web",
            direction="inbound",
            role="user",
            content_text="secret from A",
        )
    )
    session.add(
        ConversationEvent(
            id=uuid4(),
            conversation_id=conv_b.id,
            channel="web",
            direction="inbound",
            role="user",
            content_text="secret from B",
        )
    )
    session.commit()

    events_a = list_events(session, company.id, user_a.id, conv_a.id)
    events_b = list_events(session, company.id, user_b.id, conv_b.id)
    assert len(events_a) == 1
    assert events_a[0].content_text == "secret from A"
    assert len(events_b) == 1
    assert events_b[0].content_text == "secret from B"

    # Cross-user read must not return the other user's events.
    cross = list_events(session, company.id, user_a.id, conv_b.id)
    assert cross == []


def test_conversation_belongs_to_owner(symposa_db):
    session, company, user_a, user_b = symposa_db
    conv = create_conversation(session, company.id, user_a.id, title="owned by A")
    row = session.get(Conversation, conv.id)
    assert row is not None
    assert row.user_id == user_a.id
    assert row.user_id != user_b.id
