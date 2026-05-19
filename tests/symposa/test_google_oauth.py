"""Google OAuth credential storage and refresh."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from symposa.db.models import CompanyCredential, UserCredential
from symposa.services.credentials import decrypt_payload, materialize_user_credentials
from symposa.services.google_oauth import (
    GOOGLE_CLIENT_PROVIDER,
    GOOGLE_TOKEN_PROVIDER,
    google_workspace_status,
    refresh_google_token_if_needed,
    upsert_company_google_client,
)
from symposa.services.credentials import encrypt_payload, upsert_user_credential


def test_google_status_disconnected(symposa_db):
    session, company, user_a, _ = symposa_db
    status = google_workspace_status(session, company.id, user_a.id)
    assert status["connected"] is False


def test_materialize_writes_client_and_token(symposa_db, tmp_path, monkeypatch):
    session, company, user_a, _ = symposa_db
    monkeypatch.setenv("SYMPOSA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    upsert_company_google_client(
        session,
        company.id,
        "cid.apps.googleusercontent.com",
        "secret",
        "http://127.0.0.1:8090/oauth/google/callback",
    )
    upsert_user_credential(
        session,
        company.id,
        user_a.id,
        GOOGLE_TOKEN_PROVIDER,
        {
            "type": "authorized_user",
            "token": "tok",
            "refresh_token": "ref",
            "client_id": "cid.apps.googleusercontent.com",
            "client_secret": "secret",
            "scopes": ["https://www.googleapis.com/auth/drive"],
            "expiry": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
    )
    session.commit()

    hermes_home = tmp_path / "runtime" / "u" / str(user_a.id) / ".hermes"
    with patch("symposa.db.session.session_scope") as mock_scope:
        mock_scope.return_value.__enter__ = lambda s: session
        mock_scope.return_value.__exit__ = lambda *a: None
        materialize_user_credentials(company.id, user_a.id, hermes_home)
    assert (hermes_home / "google_client_secret.json").is_file()
    assert (hermes_home / "google_token.json").is_file()


def test_refresh_skips_valid_token(symposa_db):
    session, company, user_a, _ = symposa_db
    payload = {
        "token": "tok",
        "refresh_token": "ref",
        "expiry": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
    }
    updated = refresh_google_token_if_needed(session, company.id, user_a.id, payload)
    assert updated["token"] == "tok"


def test_refresh_updates_db(symposa_db):
    import sys
    from types import ModuleType

    session, company, user_a, _ = symposa_db
    upsert_company_google_client(
        session,
        company.id,
        "cid.apps.googleusercontent.com",
        "secret",
        "http://127.0.0.1:8090/oauth/google/callback",
    )
    payload = {
        "type": "authorized_user",
        "token": "old",
        "refresh_token": "ref",
        "client_id": "cid.apps.googleusercontent.com",
        "client_secret": "secret",
        "scopes": ["https://www.googleapis.com/auth/drive"],
        "expiry": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    }
    upsert_user_credential(session, company.id, user_a.id, GOOGLE_TOKEN_PROVIDER, payload)
    session.commit()

    mock_creds = MagicMock()
    mock_creds.token = "new"
    mock_creds.refresh_token = "ref"
    mock_creds.expiry = datetime.now(timezone.utc) + timedelta(hours=1)

    oauth2_mod = ModuleType("google.oauth2.credentials")
    oauth2_mod.Credentials = MagicMock(return_value=mock_creds)
    auth_transport = ModuleType("google.auth.transport.requests")
    auth_transport.Request = MagicMock()
    google_pkg = ModuleType("google")
    google_pkg.oauth2 = ModuleType("google.oauth2")
    google_pkg.oauth2.credentials = oauth2_mod
    google_pkg.auth = ModuleType("google.auth")
    google_pkg.auth.transport = ModuleType("google.auth.transport")
    google_pkg.auth.transport.requests = auth_transport

    with patch.dict(
        sys.modules,
        {
            "google": google_pkg,
            "google.oauth2": google_pkg.oauth2,
            "google.oauth2.credentials": oauth2_mod,
            "google.auth": google_pkg.auth,
            "google.auth.transport": google_pkg.auth.transport,
            "google.auth.transport.requests": auth_transport,
        },
    ):
        updated = refresh_google_token_if_needed(session, company.id, user_a.id, payload)

    assert updated["token"] == "new"
    row = session.query(UserCredential).filter_by(
        company_id=company.id, user_id=user_a.id, provider=GOOGLE_TOKEN_PROVIDER
    ).one()
    stored = decrypt_payload(row.encrypted_payload)
    assert stored["token"] == "new"
    assert row.version >= 2
