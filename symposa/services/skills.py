"""Lazy skill overrides in Postgres."""

from __future__ import annotations

from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from symposa.db.models import CompanySkillOverride, UserSkillOverride


def resolve_skill_body(
    session: Session,
    company_id: UUID,
    user_id: Optional[UUID],
    skill_name: str,
) -> Optional[Tuple[str, Optional[str]]]:
    """Return (body_md, description) if an override exists. User wins over company."""
    bare = (skill_name or "").split(":")[-1].strip()
    if not bare:
        return None

    try:
        from symposa2.services.skills import get_user_skill

        if user_id is not None:
            s2_row = get_user_skill(session, company_id, user_id, bare)
            if s2_row is not None:
                return s2_row.body_md, s2_row.description
    except Exception:
        pass

    if user_id is not None:
        user_row = session.scalar(
            select(UserSkillOverride).where(
                UserSkillOverride.company_id == company_id,
                UserSkillOverride.user_id == user_id,
                UserSkillOverride.skill_name == bare,
            )
        )
        if user_row:
            return user_row.body_md, user_row.description
    company_row = session.scalar(
        select(CompanySkillOverride).where(
            CompanySkillOverride.company_id == company_id,
            CompanySkillOverride.skill_name == bare,
        )
    )
    if company_row:
        return company_row.body_md, company_row.description
    return None


def upsert_user_skill_override(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    skill_name: str,
    body_md: str,
    description: Optional[str] = None,
) -> UserSkillOverride:
    row = session.scalar(
        select(UserSkillOverride).where(
            UserSkillOverride.company_id == company_id,
            UserSkillOverride.user_id == user_id,
            UserSkillOverride.skill_name == skill_name,
        )
    )
    if row:
        row.body_md = body_md
        if description is not None:
            row.description = description
        session.flush()
        return row
    row = UserSkillOverride(
        company_id=company_id,
        user_id=user_id,
        skill_name=skill_name,
        body_md=body_md,
        description=description,
    )
    session.add(row)
    session.flush()
    return row
