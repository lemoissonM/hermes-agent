"""Basic Symposa2 tests."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from symposa2.services.credential_registry import provider_for_env, provider_for_file
from symposa2.services.profile import build_soul_md, materialize_soul


def test_credential_registry_mappings():
    assert provider_for_file("google_token.json") == "google_workspace"
    assert provider_for_env("GITHUB_TOKEN") == "github"


def test_profile_materialize_soul(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from symposa.db.base import Base
    from symposa.db.models import Company, User
    from symposa2.db.models import S2UserProfile  # noqa: F401 — register tables
    from symposa2.services.profile import upsert_profile

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    company_id = uuid4()
    user_id = uuid4()
    with Session() as session:
        session.add(Company(id=company_id, name="Test Co"))
        session.add(
            User(
                id=user_id,
                company_id=company_id,
                email="t@test.com",
                password_hash="x",
                role="admin",
            )
        )
        session.commit()
        upsert_profile(
            session,
            company_id,
            user_id,
            display_name="Aria",
            soul_md="Be helpful.",
        )
        session.commit()
        home = tmp_path / ".hermes"
        materialize_soul(session, company_id, user_id, home)
        text = (home / "SOUL.md").read_text(encoding="utf-8")
        assert "You are Aria." in text
        assert "Be helpful." in text
        assert "Hermes Agent" not in text.split("not as Hermes Agent")[0]


def test_tenant_credentials_ephemeral_file(tmp_path, monkeypatch):
    from agent.tenant_credentials import (
        TenantCredentialContext,
        clear_tenant_context,
        register_tenant_loader,
        set_tenant_context,
        ensure_credential_file,
    )
    from hermes_constants import set_hermes_home_override

    home = tmp_path / "hermes"
    home.mkdir()
    token = set_hermes_home_override(str(home))
    set_tenant_context(TenantCredentialContext(company_id=uuid4(), user_id=uuid4()))

    payload = {"type": "authorized_user", "client_id": "x", "refresh_token": "y"}

    register_tenant_loader(
        load_provider=lambda _k: payload,
        load_file=lambda path: payload if path == "google_token.json" else None,
        load_env=lambda _e: None,
        env_overlay=lambda: {},
    )
    path = ensure_credential_file("google_token.json")
    assert path is not None
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["client_id"] == "x"
    clear_tenant_context()
    from hermes_constants import reset_hermes_home_override

    reset_hermes_home_override(token)
