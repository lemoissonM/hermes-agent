"""Symposa per-user SOUL.md identity in api_server agent runs."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent.system_prompt import build_system_prompt_parts
from hermes_constants import get_hermes_home, reset_hermes_home_override, set_hermes_home_override


def test_load_soul_identity_from_symposa_home(tmp_path, monkeypatch):
    user_home = tmp_path / "user-a" / ".hermes"
    user_home.mkdir(parents=True)
    (user_home / "SOUL.md").write_text(
        "You are Aria.\n\nBe warm and concise.",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "gateway"))

    token = set_hermes_home_override(user_home)
    try:
        agent = SimpleNamespace(
            platform="api_server",
            load_soul_identity=True,
            skip_context_files=True,
            valid_tool_names=["skills_list"],
            model="test/model",
            provider="custom",
            _tool_use_enforcement="auto",
            ephemeral_system_prompt=None,
            _memory_store=None,
            _memory_enabled=False,
            _user_profile_enabled=False,
            _memory_manager=None,
            pass_session_id=False,
            session_id=None,
        )
        stable = build_system_prompt_parts(agent)["stable"]
        assert "You are Aria." in stable
        assert "You are Hermes Agent, an intelligent AI assistant" not in stable
    finally:
        reset_hermes_home_override(token)

    assert get_hermes_home() == Path(tmp_path / "gateway")
