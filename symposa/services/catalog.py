"""Expose Hermes skills and tools for Symposa clients."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from symposa.config import get_settings


def list_skills_catalog(allowlist: Optional[List[str]] = None) -> Dict[str, Any]:
    """Bundled + user skills metadata (same as agent skills_list)."""
    from pathlib import Path

    import tools.skills_tool as skills_tool
    from tools.skills_tool import skills_list

    raw = skills_list()
    data = json.loads(raw)
    # Monorepo dev: ~/.hermes/skills may be empty until `hermes skills` sync.
    if not (data.get("skills") or []) and (data.get("count") or 0) == 0:
        bundled = Path(__file__).resolve().parents[2] / "skills"
        if bundled.is_dir():
            prev = skills_tool.SKILLS_DIR
            try:
                skills_tool.SKILLS_DIR = bundled
                raw = skills_list()
                data = json.loads(raw)
            finally:
                skills_tool.SKILLS_DIR = prev
    if not data.get("success", True):
        return {"skills": [], "categories": [], "error": data.get("error")}
    skills = data.get("skills") or []
    if allowlist:
        wanted = set(allowlist)
        skills = [s for s in skills if (s.get("name") or s.get("skill") or "") in wanted]
    return {
        "skills": skills,
        "categories": data.get("categories") or [],
        "count": len(skills),
    }


def list_tools_catalog(
    platform: str = "api_server",
    toolsets_override: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Tools available to the Hermes api_server platform (Symposa chat proxy)."""
    from hermes_cli.config import load_config
    from hermes_cli.tools_config import _get_platform_tools
    from model_tools import get_tool_definitions, get_toolset_for_tool

    cfg = load_config()
    if toolsets_override:
        toolsets = sorted(toolsets_override)
    else:
        toolsets = sorted(_get_platform_tools(cfg, platform))
    definitions = get_tool_definitions(enabled_toolsets=toolsets, quiet_mode=True)
    tools: List[Dict[str, Any]] = []
    for item in definitions:
        fn = item.get("function") or {}
        name = fn.get("name") or ""
        if not name:
            continue
        desc = fn.get("description") or ""
        tools.append(
            {
                "name": name,
                "description": desc[:500] if desc else "",
                "toolset": get_toolset_for_tool(name),
            }
        )
    tools.sort(key=lambda t: (t.get("toolset") or "", t["name"]))
    return {
        "platform": platform,
        "toolsets": toolsets,
        "tools": tools,
        "count": len(tools),
    }


def hermes_health() -> Dict[str, Any]:
    """Probe Hermes api_server reachability."""
    import httpx

    settings = get_settings()
    base = settings.hermes_api_url.rstrip("/")
    headers = {}
    if settings.hermes_api_key:
        headers["Authorization"] = f"Bearer {settings.hermes_api_key}"
    try:
        with httpx.Client(timeout=10.0) as client:
            health = client.get(f"{base.replace('/v1', '')}/health", headers=headers)
            models = client.get(f"{base}/models", headers=headers)
        return {
            "reachable": health.status_code == 200,
            "health_status": health.status_code,
            "models_status": models.status_code,
            "models": models.json() if models.status_code == 200 else None,
            "api_url": settings.hermes_api_url,
        }
    except Exception as exc:
        return {
            "reachable": False,
            "error": str(exc),
            "api_url": settings.hermes_api_url,
        }
