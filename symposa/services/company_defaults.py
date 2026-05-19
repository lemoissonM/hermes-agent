"""Default Symposa workspace toolsets and skill allowlists per company."""

from __future__ import annotations

from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from symposa.db.models import Company, CompanyAgent, User
from symposa.services.skill_policy import filter_skill_allowlist

DEFAULT_TOOLSETS: List[str] = ["symposa-web"]

_LEGACY_TOOLSET_ALIASES = {
    "symposa-workspace": "symposa-web",
    "hermes-api-server": "symposa-web",
}

DEFAULT_SKILL_ALLOWLIST: List[str] = []

DEFAULT_SOUL_TEXT = (
    "You are Symposa, a workplace assistant. Speak as Symposa only — never mention Hermes, "
    "api_server, or internal tooling. For Gmail, Calendar, Drive, Sheets, and Docs, always use "
    "the `google-workspace` skill (see skills/productivity/google-workspace/SKILL.md). "
    "If Google access fails, direct users to Settings → Integrations. Use the full Hermes "
    "tool surface available through the API server."
)


def get_company_workspace_config(
    session: Session, company_id: UUID
) -> Tuple[List[str], List[str], Optional[str]]:
    """Return (toolsets, preloaded_skills, soul_text) from the default company agent."""
    row = session.scalar(
        select(CompanyAgent)
        .where(CompanyAgent.company_id == company_id)
        .order_by(CompanyAgent.created_at.asc())
        .limit(1)
    )
    if row is None:
        return (
            list(DEFAULT_TOOLSETS),
            filter_skill_allowlist(DEFAULT_SKILL_ALLOWLIST),
            DEFAULT_SOUL_TEXT,
        )
    toolsets = _normalize_toolsets(row.toolsets or DEFAULT_TOOLSETS)
    skills = filter_skill_allowlist(list(row.preloaded_skills or DEFAULT_SKILL_ALLOWLIST))
    return toolsets, skills, row.soul_text or DEFAULT_SOUL_TEXT


def _normalize_toolsets(toolsets: List[str] | None) -> List[str]:
    """Normalize company toolset names (upgrade legacy aliases, dedupe)."""
    raw = [str(t).strip() for t in (toolsets or DEFAULT_TOOLSETS) if str(t).strip()]
    if not raw:
        raw = list(DEFAULT_TOOLSETS)
    out: List[str] = []
    for name in raw:
        mapped = _LEGACY_TOOLSET_ALIASES.get(name, name)
        if mapped not in out:
            out.append(mapped)
    return out or list(DEFAULT_TOOLSETS)


def ensure_company_agent(session: Session, company_id: UUID) -> CompanyAgent:
    """Create default company agent preset if missing."""
    existing = session.scalar(
        select(CompanyAgent).where(CompanyAgent.company_id == company_id).limit(1)
    )
    if existing:
        normalized_toolsets = _normalize_toolsets(list(existing.toolsets or []))
        if normalized_toolsets != list(existing.toolsets or []):
            existing.toolsets = normalized_toolsets
        filtered = filter_skill_allowlist(list(existing.preloaded_skills or []))
        if filtered != list(existing.preloaded_skills or []):
            existing.preloaded_skills = filtered
            session.flush()
        return existing
    row = CompanyAgent(
        company_id=company_id,
        name="Symposa Workspace",
        soul_text=DEFAULT_SOUL_TEXT,
        toolsets=list(DEFAULT_TOOLSETS),
        preloaded_skills=filter_skill_allowlist(DEFAULT_SKILL_ALLOWLIST),
    )
    session.add(row)
    session.flush()
    return row


def ensure_harvely_seed(session: Session) -> None:
    """Idempotent seed for harvely company + default agent."""
    company = session.scalar(select(Company).where(Company.name == "harvely"))
    if company is None:
        return
    ensure_company_agent(session, company.id)
