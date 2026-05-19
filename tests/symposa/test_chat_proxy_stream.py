"""Streaming chat proxy forwards Hermes SSE and emits symposa.done."""

import asyncio
from unittest.mock import patch
from uuid import uuid4

from symposa.api.chat_proxy import chat_via_hermes_stream


class _FakeStreamResponse:
    def __init__(self, lines: list[bytes], headers: dict | None = None):
        self.status_code = 200
        self.headers = headers or {}
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def aiter_bytes(self):
        for chunk in self._lines:
            yield chunk


class _FakeClient:
    def __init__(self, response: _FakeStreamResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url, headers=None, json=None):
        assert method == "POST"
        assert json.get("stream") is True
        return self._response


def test_chat_via_hermes_stream_forwards_and_done(symposa_db):
    _session, company, user_a, _user_b = symposa_db
    conversation_id = uuid4()
    sse = (
        b'data: {"choices":[{"delta":{"content":"Hi "}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"there"}}]}\n\n'
        b"data: [DONE]\n\n"
    )
    fake_resp = _FakeStreamResponse([sse], headers={"X-Hermes-Session-Id": "sess-1"})
    fake_client = _FakeClient(fake_resp)

    async def _collect() -> list[bytes]:
        chunks: list[bytes] = []
        async for chunk in chat_via_hermes_stream(
            company.id, user_a.id, conversation_id, "Hello"
        ):
            chunks.append(chunk)
        return chunks

    with patch("symposa.api.chat_proxy.httpx.AsyncClient", return_value=fake_client), patch(
        "symposa.api.chat_proxy.bootstrap_runtime"
    ), patch("symposa.api.chat_proxy.mirror_message") as mirror, patch(
        "symposa.api.chat_proxy.session_scope"
    ) as mock_scope:
        mock_scope.return_value.__enter__ = lambda s: _session
        mock_scope.return_value.__exit__ = lambda *a: None
        chunks = asyncio.run(_collect())

    body = b"".join(chunks).decode("utf-8")
    assert "Hi " in body
    assert "event: symposa.done" in body
    assert "sess-1" in body
    assert '"raw_model_hint": false' in body or "raw_model_hint" in body
    mirror.assert_any_call(direction="outbound", role="assistant", content_text="Hi there")
