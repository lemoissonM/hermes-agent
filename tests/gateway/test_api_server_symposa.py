"""api_server Symposa request handling."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gateway.platforms.api_server import APIServerAdapter


def test_symposa_home_missing_returns_502():
    adapter = APIServerAdapter.__new__(APIServerAdapter)
    adapter._api_key = "test-key"
    adapter._override_enabled_toolsets = None

    request = MagicMock()
    request.headers = {
        "Authorization": "Bearer test-key",
        "X-Symposa-Hermes-Home": "/nonexistent/symposa/runtime/u/x/.hermes",
    }

    with patch.object(adapter, "_check_auth", return_value=None), patch.object(
        adapter, "_parse_symposa_hermes_home_header",
        return_value=("/nonexistent/symposa/runtime/u/x/.hermes", None),
    ):
        import asyncio

        resp = asyncio.run(adapter._handle_chat_completions(request))

    assert resp.status == 502


def test_create_agent_symposa_platform_and_no_pool():
    adapter = APIServerAdapter.__new__(APIServerAdapter)
    adapter._override_enabled_toolsets = ["symposa-web"]
    adapter._session_db = None

    runtime = {
        "api_key": "k",
        "base_url": "http://localhost/v1",
        "provider": "custom",
        "credential_pool": object(),
    }

    with patch("run_agent.AIAgent") as mock_agent_cls, patch(
        "gateway.run._resolve_runtime_agent_kwargs", return_value=dict(runtime)
    ), patch(
        "gateway.run._resolve_gateway_model", return_value="gemma4:e4b"
    ), patch(
        "gateway.run._load_gateway_config", return_value={}
    ), patch(
        "hermes_cli.tools_config._get_platform_tools", return_value=["symposa-web"]
    ), patch(
        "gateway.run.GatewayRunner._load_reasoning_config", return_value=None
    ), patch(
        "gateway.run.GatewayRunner._load_fallback_model", return_value=None
    ):
        adapter._create_agent(platform="symposa", inference_runtime=dict(runtime))

    assert mock_agent_cls.call_args.kwargs["platform"] == "symposa"
    passed_runtime = {k: v for k, v in mock_agent_cls.call_args.kwargs.items() if k not in (
        "model", "max_iterations", "quiet_mode", "verbose_logging", "ephemeral_system_prompt",
        "enabled_toolsets", "session_id", "stream_delta_callback", "tool_progress_callback",
        "tool_start_callback", "tool_complete_callback", "session_db", "fallback_model",
        "reasoning_config", "gateway_session_key", "clarify_callback", "platform",
    )}
    assert "credential_pool" not in passed_runtime
