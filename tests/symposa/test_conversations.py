"""Conversation and active-pointer tests."""

from symposa.services.conversations import (
    create_conversation,
    get_active_conversation_id,
    list_conversations,
    set_active_conversation,
)
from symposa.services.events import append_event, list_events
from symposa.services.conv_commands import handle_conv_command


def test_multiple_conversations_and_active_pointer(symposa_db):
    session, company, user_a, _user_b = symposa_db
    c1 = create_conversation(session, company.id, user_a.id, title="Project A")
    c2 = create_conversation(session, company.id, user_a.id, title="Project B")
    session.commit()
    assert len(list_conversations(session, company.id, user_a.id)) == 2
    set_active_conversation(session, company.id, user_a.id, "whatsapp", c1.id)
    session.commit()
    assert get_active_conversation_id(session, company.id, user_a.id, "whatsapp") == c1.id
    set_active_conversation(session, company.id, user_a.id, "whatsapp", c2.id)
    session.commit()
    assert get_active_conversation_id(session, company.id, user_a.id, "whatsapp") == c2.id


def test_conv_list_command(symposa_db):
    session, company, user_a, _ = symposa_db
    create_conversation(session, company.id, user_a.id, title="Alpha")
    session.commit()
    result = handle_conv_command(session, company.id, user_a.id, "/conv list", channel="whatsapp")
    assert result.handled
    assert "Alpha" in (result.reply_text or "")


def test_events_isolated_per_user(symposa_db):
    session, company, user_a, user_b = symposa_db
    conv_a = create_conversation(session, company.id, user_a.id, title="A")
    conv_b = create_conversation(session, company.id, user_b.id, title="B")
    session.commit()
    append_event(
        session,
        company.id,
        user_a.id,
        conv_a.id,
        channel="web",
        direction="inbound",
        role="user",
        content_text="secret-a",
    )
    session.commit()
    events_b = list_events(session, company.id, user_b.id, conv_b.id)
    assert len(events_b) == 0
    events_a = list_events(session, company.id, user_a.id, conv_a.id)
    assert len(events_a) == 1
    assert events_a[0].content_text == "secret-a"
