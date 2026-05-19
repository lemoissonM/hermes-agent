"""Preload user-authored Symposa skills into ephemeral session prompts."""

from __future__ import annotations

import logging
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from symposa.services.company_defaults import get_company_workspace_config

logger = logging.getLogger(__name__)

MAX_PRELOAD_SKILLS = 8
MAX_PRELOAD_CHARS = 32_000

_USER_SKILL_DIRECTIVE = (
    "## User skills (priority)\n"
    "The skills below were authored for this user or company. They override generic "
    "or bundled guidance when they conflict. Follow them actively; use "
    "`skill_view(name)` for linked references, templates, or scripts.\n"
)


def collect_user_skill_identifiers(
    session: Session,
    company_id: UUID,
    user_id: UUID,
) -> List[str]:
    """Return skill names to preload, highest priority first."""
    _, company_preloaded, _ = get_company_workspace_config(session, company_id)

    custom: List[str] = []
    overrides: List[str] = []
    try:
        from symposa2.services.skills import list_user_skills

        for row in list_user_skills(session, company_id, user_id):
            name = (row.skill_name or "").strip()
            if not name:
                continue
            if row.is_custom:
                custom.append(name)
            else:
                overrides.append(name)
    except Exception as exc:
        logger.debug("list_user_skills unavailable: %s", exc)

    seen: set[str] = set()
    ordered: List[str] = []

    def _add(names: List[str]) -> None:
        for raw in names:
            n = (raw or "").strip()
            if not n or n in seen:
                continue
            seen.add(n)
            ordered.append(n)

    _add(custom)
    _add(overrides)
    _add(list(company_preloaded or []))
    return ordered[:MAX_PRELOAD_SKILLS]


def build_user_skills_preload_block(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    *,
    task_id: str | None = None,
) -> str:
    """Embed full SKILL.md bodies for user/company skills (session-start preload)."""
    identifiers = collect_user_skill_identifiers(session, company_id, user_id)
    if not identifiers:
        return ""

    try:
        from agent.skill_commands import build_preloaded_skills_prompt

        prompt_text, loaded, missing = build_preloaded_skills_prompt(
            identifiers,
            task_id=task_id,
        )
    except Exception as exc:
        logger.debug("build_preloaded_skills_prompt failed: %s", exc)
        return ""

    if not prompt_text:
        return ""

    if len(prompt_text) > MAX_PRELOAD_CHARS:
        prompt_text = prompt_text[: MAX_PRELOAD_CHARS - 3] + "..."

    parts = [_USER_SKILL_DIRECTIVE.strip()]
    if loaded:
        parts.append(f"Loaded: {', '.join(loaded)}.")
    if missing:
        parts.append(f"Could not load on disk yet: {', '.join(missing)}.")
    parts.append(prompt_text)
    return "\n\n".join(parts)
