"""Symposa2 uses Hermes /v1/runs, not raw chat/completions."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from symposa2.services.chat import _prepare_run_request, chat_via_hermes_stream


def test_prepare_run_request_uses_runs_api_shape(monkeypatch):
    monkeypatch.setenv("SYMPOSA_HERMES_API_URL", "http://127.0.0.1:8787/v1")
    from symposa.config import get_settings

    get_settings.cache_clear()
    try:
        company_id = uuid4()
        user_id = uuid4()
        conversation_id = uuid4()
        with patch("symposa2.services.chat.bootstrap_runtime"), patch(
            "symposa2.services.chat.hermes_home_for_api_server",
            return_value="/mnt/wsl/runtime/.hermes",
        ):
            headers, body = _prepare_run_request(
                company_id, user_id, conversation_id, "hello", hermes_session_id="sess-1"
            )
        assert headers["X-Hermes-Enabled-Toolsets"] == "hermes-cli"
        assert headers["X-Symposa2-Hermes-Home"] == "/mnt/wsl/runtime/.hermes"
        assert headers["X-Hermes-Session-Id"] == "sess-1"
        assert body == {"input": "hello", "session_id": "sess-1"}
        assert "chat/completions" not in json.dumps(body)
    finally:
        get_settings.cache_clear()


def test_stream_run_translates_message_delta():
    company_id = uuid4()
    user_id = uuid4()
    conversation_id = uuid4()

    start_resp = MagicMock()
    start_resp.status_code = 202
    start_resp.json.return_value = {"run_id": "run_abc", "session_id": "sess-xyz"}
    start_resp.headers = {"X-Hermes-Session-Id": "sess-xyz"}

    events_lines = [
        'data: {"event": "message.delta", "delta": "Hi"}\n\n',
        'data: {"event": "run.completed", "output": "Hi"}\n\n',
        ": stream closed\n\n",
    ]

    async def fake_aiter_bytes():
        for line in events_lines:
            yield line.encode()

    events_resp = AsyncMock()
    events_resp.status_code = 200
    events_resp.aiter_bytes = fake_aiter_bytes
    events_resp.__aenter__ = AsyncMock(return_value=events_resp)
    events_resp.__aexit__ = AsyncMock(return_value=None)

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=start_resp)
    mock_client.stream = MagicMock(return_value=events_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    async def _collect() -> list[bytes]:
        chunks: list[bytes] = []
        async for chunk in chat_via_hermes_stream(
            company_id, user_id, conversation_id, "hello"
        ):
            chunks.append(chunk)
        return chunks

    with patch("symposa2.services.chat.httpx.AsyncClient", return_value=mock_client), patch(
        "symposa2.services.chat.bootstrap_runtime"
    ), patch("symposa2.services.chat.mirror_message"), patch(
        "symposa2.services.chat.clear_runtime_credentials"
    ), patch(
        "symposa2.services.chat.hermes_home_for_api_server",
        return_value="/mnt/wsl/runtime/.hermes",
    ):
        chunks = asyncio.run(_collect())

    payload = b"".join(chunks).decode()
    assert "Hi" in payload
    assert "symposa.done" in payload
    assert "sess-xyz" in payload
    assert "run_abc" in payload
    mock_client.post.assert_awaited_once()
    assert mock_client.post.await_args.args[0].endswith("/runs")


def test_stream_auto_resolves_approval_without_ui_event():
    company_id = uuid4()
    user_id = uuid4()
    conversation_id = uuid4()

    start_resp = MagicMock()
    start_resp.status_code = 202
    start_resp.json.return_value = {"run_id": "run_abc", "session_id": "sess-xyz"}
    start_resp.headers = {"X-Hermes-Session-Id": "sess-xyz"}

    events_lines = [
        'data: {"event": "approval.request", "run_id": "run_abc", "command": "pip install x"}\n\n',
        'data: {"event": "message.delta", "delta": "Done"}\n\n',
        'data: {"event": "run.completed", "output": "Done"}\n\n',
    ]

    async def fake_aiter_bytes():
        for line in events_lines:
            yield line.encode()

    events_resp = AsyncMock()
    events_resp.status_code = 200
    events_resp.aiter_bytes = fake_aiter_bytes
    events_resp.__aenter__ = AsyncMock(return_value=events_resp)
    events_resp.__aexit__ = AsyncMock(return_value=None)

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=start_resp)
    mock_client.stream = MagicMock(return_value=events_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    async def _collect() -> list[bytes]:
        chunks: list[bytes] = []
        async for chunk in chat_via_hermes_stream(
            company_id, user_id, conversation_id, "hello"
        ):
            chunks.append(chunk)
        return chunks

    with patch("symposa2.services.chat.httpx.AsyncClient", return_value=mock_client), patch(
        "symposa2.services.chat.bootstrap_runtime"
    ), patch("symposa2.services.chat.mirror_message"), patch(
        "symposa2.services.chat.clear_runtime_credentials"
    ), patch(
        "symposa2.services.chat.hermes_home_for_api_server",
        return_value="/mnt/wsl/runtime/.hermes",
    ), patch(
        "symposa2.services.chat.resolve_run_approval", return_value=True
    ) as mock_resolve:
        chunks = asyncio.run(_collect())

    payload = b"".join(chunks).decode()
    assert "symposa.approval" not in payload
    assert "Done" in payload
    mock_resolve.assert_called_once_with("run_abc", "once")
