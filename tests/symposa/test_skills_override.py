"""Lazy skill override resolution."""

from symposa.services.skills import resolve_skill_body, upsert_user_skill_override


def test_user_override_wins(symposa_db):
    session, company, user_a, _ = symposa_db
    upsert_user_skill_override(
        session,
        company.id,
        user_a.id,
        "google-workspace",
        "# Custom\nbody",
        description="Custom GW",
    )
    session.commit()
    resolved = resolve_skill_body(session, company.id, user_a.id, "google-workspace")
    assert resolved is not None
    assert "Custom" in resolved[0]
