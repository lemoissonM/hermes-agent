"""symposa-workspace toolset shape."""

from toolsets import TOOLSETS


def test_symposa_workspace_includes_workspace_tools():
    ts = TOOLSETS["symposa-workspace"]
    tools = set(ts["tools"])
    for name in (
        "read_file",
        "terminal",
        "process",
        "web_search",
        "vision_analyze",
        "image_generate",
        "cronjob",
        "skills_list",
        "memory",
    ):
        assert name in tools


def test_symposa_workspace_excludes_risky_tools():
    tools = set(TOOLSETS["symposa-workspace"]["tools"])
    for name in ("browser_navigate", "delegate_task", "execute_code", "send_message"):
        assert name not in tools
