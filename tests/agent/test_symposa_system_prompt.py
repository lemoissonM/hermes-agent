"""Symposa platform uses Symposa identity in the system prompt."""

from types import SimpleNamespace

from agent.system_prompt import build_system_prompt_parts
from agent.prompt_builder import SYMPOSA_AGENT_IDENTITY, DEFAULT_AGENT_IDENTITY


def test_symposa_platform_identity():
    agent = SimpleNamespace(
        platform="symposa",
        load_soul_identity=False,
        skip_context_files=True,
        valid_tool_names=["skills_list", "memory"],
        model="gemma4:e4b",
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
    parts = build_system_prompt_parts(agent)
    stable = parts["stable"]
    assert "You are Symposa" in stable
    assert "You are Hermes Agent" not in stable
