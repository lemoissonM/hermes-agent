"""Symposa workspace skill allowlist and explicit denylists."""

from __future__ import annotations

from typing import List

# Empty policy means Symposa exposes the normal Hermes skill surface.
SYMPOSA_SKILL_ALLOWLIST: List[str] = []
SYMPOSA_SKILL_DENYLIST: List[str] = []


def filter_skill_allowlist(skills: List[str] | None) -> List[str]:
    """Return the provided skills unchanged; Symposa no longer filters skills."""
    return list(skills or [])


def is_skill_allowed(skill_name: str) -> bool:
    return True
