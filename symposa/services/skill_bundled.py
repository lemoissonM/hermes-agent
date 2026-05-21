"""Allowlisted bundled skill materialization for Symposa tenants."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Iterable, List, Set
from uuid import UUID

from sqlalchemy.orm import Session

from symposa.services.company_defaults import get_company_workspace_config
from symposa.services.inference_config import _bundled_skills_dir

logger = logging.getLogger(__name__)

SYMPOSA_ESSENTIAL_SKILLS: List[str] = ["google-workspace"]

_FRONTMATTER_NAME_RE = re.compile(
    r"^name:\s*(.+)$",
    re.MULTILINE | re.IGNORECASE,
)


def compute_symposa_bundled_allowlist(
    session: Session,
    company_id: UUID,
    user_id: UUID,
) -> List[str]:
    """Bundled repo skills to copy for this tenant (not user custom skills)."""
    _, company_preloaded, _ = get_company_workspace_config(session, company_id)
    names: List[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        n = (raw or "").strip()
        if not n or n in seen:
            return
        seen.add(n)
        names.append(n)

    for essential in SYMPOSA_ESSENTIAL_SKILLS:
        _add(essential)
    for item in company_preloaded or []:
        _add(str(item))
    try:
        from symposa2.services.skills import enabled_company_skill_names, list_user_skills

        for skill_name in enabled_company_skill_names(session, company_id):
            _add(skill_name)

        for row in list_user_skills(session, company_id, user_id):
            if not row.is_custom:
                _add(row.skill_name)
    except Exception as exc:
        logger.debug("list_user_skills for allowlist: %s", exc)
    return names


def _skill_names_in_file(skill_md: Path) -> Set[str]:
    names: Set[str] = set()
    names.add(skill_md.parent.name)
    try:
        head = skill_md.read_text(encoding="utf-8")[:2048]
        match = _FRONTMATTER_NAME_RE.search(head)
        if match:
            names.add(match.group(1).strip().strip("'\""))
    except OSError:
        pass
    return {n for n in names if n}


def find_bundled_skill_dirs(bundled_dir: Path, skill_names: Iterable[str]) -> List[Path]:
    """Resolve bundled skill directories matching any of *skill_names*."""
    wanted = {(n or "").strip() for n in skill_names if (n or "").strip()}
    if not wanted or not bundled_dir.is_dir():
        return []

    found: List[Path] = []
    seen_dirs: set[Path] = set()
    for skill_md in bundled_dir.rglob("SKILL.md"):
        if not _skill_names_in_file(skill_md) & wanted:
            continue
        skill_dir = skill_md.parent
        try:
            key = skill_dir.resolve()
        except OSError:
            key = skill_dir
        if key in seen_dirs:
            continue
        seen_dirs.add(key)
        found.append(skill_dir)
    return found
