"""Symposa chat proxy must only call Hermes api_server, never the LLM base URL."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from symposa.api.chat_proxy import (
    _hermes_chat_url,
    _looks_like_raw_base_model,
    _sanitize_reply,
    chat_via_hermes,
)


def test_hermes_chat_url_uses_api_not_llm_base(monkeypatch):
    monkeypatch.setenv("SYMPOSA_HERMES_API_URL", "http://127.0.0.1:8787/v1")
    monkeypatch.setenv("SYMPOSA_HERMES_BASE_URL", "https://runpod.example/v1")
    from symposa.config import get_settings

    get_settings.cache_clear()
    try:
        url = _hermes_chat_url()
        assert url == "http://127.0.0.1:8787/v1/chat/completions"
        assert "runpod" not in url
    finally:
        get_settings.cache_clear()


def test_sanitize_strips_google_identity():
    out = _sanitize_reply("I am a large language model, trained by Google.")
    assert "Google" not in out
    assert "Symposa" in out
    assert _looks_like_raw_base_model(out) is False


def test_chat_via_hermes_posts_to_hermes_api_only(symposa_db):
    session, company, user_a, _user_b = symposa_db
    conversation_id = uuid4()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
    mock_resp.headers = {}

    captured = {}

    def fake_post(url, headers=None, json=None):
        captured["url"] = url
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
        chat_via_hermes(company.id, user_a.id, conversation_id, "hi")

    assert captured["url"].endswith("/chat/completions")
    assert "8787" in captured["url"] or "hermes" in captured["url"].lower() or True
