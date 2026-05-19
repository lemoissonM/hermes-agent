"""Lightweight insert throughput smoke test (no network)."""

from __future__ import annotations

import time
from uuid import uuid4

from symposa.db.models import ConversationEvent
from symposa.services.conversations import create_conversation


def test_conversation_events_bulk_insert(symposa_db):
    session, company, user_a, _user_b = symposa_db
    conv = create_conversation(session, company.id, user_a.id, title="load")
    session.commit()
    n = 200
    start = time.perf_counter()
    for i in range(n):
        session.add(
            ConversationEvent(
                id=uuid4(),
                conversation_id=conv.id,
                channel="web",
                direction="inbound",
                role="user",
                content_text=f"msg-{i}",
            )
        )
    session.commit()
    elapsed = time.perf_counter() - start
    count = (
        session.query(ConversationEvent)
        .filter(ConversationEvent.conversation_id == conv.id)
        .count()
    )
    assert count == n
    assert elapsed < 5.0, f"inserting {n} events took {elapsed:.2f}s"
