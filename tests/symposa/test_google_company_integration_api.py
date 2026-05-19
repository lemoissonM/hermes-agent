"""Company Google OAuth client registration via OpenAPI/Swagger body schema."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from symposa.api.app import create_app
from symposa.auth.jwt import create_access_token
from symposa.db.models import Company, User
from symposa.auth.passwords import hash_password


@pytest.fixture
def api_client(symposa_db):
    session, company, user_a, _user_b = symposa_db
    admin = User(
        id=uuid4(),
        company_id=company.id,
        email="admin@test.com",
        password_hash=hash_password("password123"),
        role="admin",
    )
    session.add(admin)
    session.commit()
    app = create_app()
    client = TestClient(app)
    token = create_access_token(admin.id, company.id, admin.role, admin.email)
    return client, token, company.id, session


def test_company_google_put_and_get(api_client):
    client, token, _cid, session = api_client
    headers = {"Authorization": f"Bearer {token}"}

    with patch("symposa.api.app.session_scope") as mock_scope:
        mock_scope.return_value.__enter__ = lambda s: session
        mock_scope.return_value.__exit__ = lambda *a: None
        put = client.put(
        "/company/integrations/google",
        headers=headers,
        json={
            "client_id": "test.apps.googleusercontent.com",
            "client_secret": "secret-value",
            "redirect_uri": "http://127.0.0.1:8090/oauth/google/callback",
        },
        )
        assert put.status_code == 200, put.text
        body = put.json()
        assert body["ok"] is True
        assert body["client_id"] == "test.apps.googleusercontent.com"
        assert "redirect_uri" in body

        get = client.get("/company/integrations/google", headers=headers)
        assert get.status_code == 200, get.text
        status = get.json()
        assert status["configured"] is True
        assert status["client_id"] == "test.apps.googleusercontent.com"
        assert status["source"] == "database"


def test_google_connect_url_endpoint(api_client):
    client, token, _cid, session = api_client
    headers = {"Authorization": f"Bearer {token}"}

    with patch(
        "symposa.services.google_oauth.start_google_connect",
        return_value="https://accounts.google.com/o/oauth2/auth?test=1",
    ):
        resp = client.get("/integrations/google/connect-url", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["authorize_url"].startswith("https://accounts.google.com")


def test_company_google_put_requires_admin(symposa_db):
    session, company, user_a, _ = symposa_db
    app = create_app()
    client = TestClient(app)
    token = create_access_token(user_a.id, company.id, user_a.role, user_a.email)
    resp = client.put(
        "/company/integrations/google",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "client_id": "x.apps.googleusercontent.com",
            "client_secret": "secret",
        },
    )
    assert resp.status_code == 403
