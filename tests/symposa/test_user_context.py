"""User context block for Hermes ephemeral prompts."""

from uuid import uuid4

from symposa.db.models import ChannelIdentity, CompanyAgent, Conversation
from symposa.services.user_context import build_user_context_block


def test_user_context_contains_identity(symposa_db):
    session, company, user_a, _user_b = symposa_db
    conv = Conversation(
        id=uuid4(),
        company_id=company.id,
        user_id=user_a.id,
        title="Test",
    )
    session.add(conv)
    session.add(
        ChannelIdentity(
            company_id=company.id,
            user_id=user_a.id,
            channel="web",
            external_id=str(user_a.id),
        )
    )
    session.add(
        CompanyAgent(
            company_id=company.id,
            name="Workspace",
            soul_text="Be helpful.",
            toolsets=["symposa-workspace"],
            preloaded_skills=["google-workspace"],
        )
    )
    session.commit()

    block = build_user_context_block(
        session, company.id, user_a.id, conversation_id=conv.id, channel="web"
    )
    assert "a@test.com" in block
    assert "Test Co" in block
    assert str(conv.id) in block
    assert "Be helpful." in block
    assert "Symposa assistant rules" in block
    assert "Never identify as the base model provider" in block
    assert "what can you do" in block
    assert "generic model" in block
    assert "Settings → Integrations" in block
    assert "GET /integrations" not in block
    assert "himalaya" not in block
