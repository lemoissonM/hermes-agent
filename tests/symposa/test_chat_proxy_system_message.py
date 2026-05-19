"""Chat proxy sends system message and toolset header to Hermes."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx

from symposa.api.chat_proxy import _sanitize_reply, chat_via_hermes


def test_chat_proxy_includes_system_message(symposa_db):
    session, company, user_a, _user_b = symposa_db
    company_id = company.id
    user_id = user_a.id
    conversation_id = uuid4()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "You are a@test.com"}}]}
    mock_resp.headers = {}

    captured = {}

    def fake_post(url, headers=None, json=None):
        captured["headers"] = headers
        captured["json"] = json
        return mock_resp

    mock_client = MagicMock()
    mock_client.post = fake_post
    mock_client.__enter__ = lambda s: mock_client
    mock_client.__exit__ = lambda *a: None

    with patch("symposa.api.chat_proxy.httpx.Client", return_value=mock_client), patch(
        "symposa.api.chat_proxy.bootstrap_runtime"
    ), patch("symposa.api.chat_proxy.mirror_message"), patch(
        "symposa.api.chat_proxy.session_scope"
    ) as mock_scope:
        mock_scope.return_value.__enter__ = lambda s: session
        mock_scope.return_value.__exit__ = lambda *a: None
        reply, _ = chat_via_hermes(company_id, user_id, conversation_id, "Who am I?")

    assert "a@test.com" in reply
    messages = captured["json"]["messages"]
    assert messages[0]["role"] == "system"
    assert "a@test.com" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "model" not in captured["json"]
    assert captured["headers"].get("X-Hermes-Enabled-Toolsets", "") == "symposa-web"
    assert captured["headers"].get("X-Symposa-Company-Id") == str(company_id)
    assert captured["headers"].get("X-Symposa-User-Id") == str(user_id)
    symposa_home = captured["headers"].get("X-Symposa-Hermes-Home", "")
    assert symposa_home
    assert "/.hermes" in symposa_home.replace("\\", "/")


def test_chat_proxy_symposa_backend_error_message(symposa_db):
    session, company, user_a, _user_b = symposa_db
    conversation_id = uuid4()

    mock_client = MagicMock()
    mock_client.post.side_effect = httpx.HTTPError("connection refused")
    mock_client.__enter__ = lambda s: mock_client
    mock_client.__exit__ = lambda *a: None

    with patch("symposa.api.chat_proxy.httpx.Client", return_value=mock_client), patch(
        "symposa.api.chat_proxy.bootstrap_runtime"
    ), patch("symposa.api.chat_proxy.mirror_message"), patch(
        "symposa.api.chat_proxy.session_scope"
    ) as mock_scope:
        mock_scope.return_value.__enter__ = lambda s: session
        mock_scope.return_value.__exit__ = lambda *a: None
        reply, _ = chat_via_hermes(company.id, user_a.id, conversation_id, "Hi")

    assert "Symposa" in reply
    assert "Hermes" not in reply


def test_chat_proxy_sanitizes_base_model_identity():
    out = _sanitize_reply("Hello! I am a large language model, trained by Google. I can help.")
    assert "large language model" not in out
    assert "trained by Google" not in out
    assert "I'm Symposa" in out


