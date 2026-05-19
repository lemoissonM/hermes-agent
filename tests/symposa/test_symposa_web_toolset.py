"""symposa-web toolset shape."""

from toolsets import TOOLSETS


def test_symposa_web_includes_clarify_and_api_server_tools():
    web = set(TOOLSETS["symposa-web"]["tools"])
    api = set(TOOLSETS["hermes-api-server"]["tools"])
    assert "clarify" in web
    assert api - {"execute_code", "delegate_task"} <= web


def test_symposa_web_excludes_coding_tools():
    tools = set(TOOLSETS["symposa-web"]["tools"])
    assert "execute_code" not in tools
    assert "delegate_task" not in tools
