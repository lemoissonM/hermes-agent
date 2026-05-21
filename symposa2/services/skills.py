"""Per-user custom skills in Postgres, mirrored to HERMES_HOME."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from symposa2.db.models import S2CompanySkill, S2UserSkill


def list_user_skills(
    session: Session,
    company_id: UUID,
    user_id: UUID,
) -> List[S2UserSkill]:
    return list(
        session.scalars(
            select(S2UserSkill).where(
                S2UserSkill.company_id == company_id,
                S2UserSkill.user_id == user_id,
            )
        )
    )


def list_company_skills(session: Session, company_id: UUID) -> List[S2CompanySkill]:
    return list(
        session.scalars(
            select(S2CompanySkill)
            .where(S2CompanySkill.company_id == company_id)
            .order_by(S2CompanySkill.skill_name.asc())
        )
    )


def enabled_company_skill_names(session: Session, company_id: UUID) -> List[str]:
    return [
        row.skill_name
        for row in list_company_skills(session, company_id)
        if row.enabled and not row.is_custom
    ]


def get_company_skill(
    session: Session,
    company_id: UUID,
    skill_name: str,
) -> Optional[S2CompanySkill]:
    return session.scalar(
        select(S2CompanySkill).where(
            S2CompanySkill.company_id == company_id,
            S2CompanySkill.skill_name == skill_name,
        )
    )


def upsert_company_skill(
    session: Session,
    company_id: UUID,
    skill_name: str,
    *,
    description: Optional[str] = None,
    body_md: Optional[str] = None,
    enabled: bool = True,
    is_custom: bool = False,
) -> S2CompanySkill:
    row = get_company_skill(session, company_id, skill_name)
    if row:
        row.description = description
        row.body_md = body_md
        row.enabled = enabled
        row.is_custom = is_custom
        session.flush()
        return row
    row = S2CompanySkill(
        company_id=company_id,
        skill_name=skill_name,
        description=description,
        body_md=body_md,
        enabled=enabled,
        is_custom=is_custom,
    )
    session.add(row)
    session.flush()
    return row


def delete_company_skill(session: Session, company_id: UUID, skill_name: str) -> bool:
    row = get_company_skill(session, company_id, skill_name)
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


def get_user_skill(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    skill_name: str,
) -> Optional[S2UserSkill]:
    return session.scalar(
        select(S2UserSkill).where(
            S2UserSkill.company_id == company_id,
            S2UserSkill.user_id == user_id,
            S2UserSkill.skill_name == skill_name,
        )
    )


def upsert_user_skill(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    skill_name: str,
    body_md: str,
    *,
    description: Optional[str] = None,
    is_custom: bool = False,
) -> S2UserSkill:
    row = get_user_skill(session, company_id, user_id, skill_name)
    if row:
        row.body_md = body_md
        if description is not None:
            row.description = description
        row.is_custom = is_custom
        session.flush()
        return row
    row = S2UserSkill(
        company_id=company_id,
        user_id=user_id,
        skill_name=skill_name,
        body_md=body_md,
        description=description,
        is_custom=is_custom,
    )
    session.add(row)
    session.flush()
    return row


def delete_user_skill(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    skill_name: str,
) -> bool:
    row = get_user_skill(session, company_id, user_id, skill_name)
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


def _skill_frontmatter(name: str, description: Optional[str], body_md: str) -> str:
    if body_md.lstrip().startswith("---"):
        return body_md
    desc = (description or f"Custom skill: {name}").replace('"', "'")[:60]
    return f"---\nname: {name}\ndescription: {desc}.\n---\n\n{body_md.lstrip()}"


def materialize_skills(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    hermes_home: Path,
) -> None:
    skills_root = hermes_home / "skills"
    overrides = skills_root / "_overrides"
    custom = skills_root / "custom"
    for sub in (overrides, custom):
        if sub.is_dir():
            shutil.rmtree(sub, ignore_errors=True)
        sub.mkdir(parents=True, exist_ok=True)

    for row in list_company_skills(session, company_id):
        if not row.enabled or not row.body_md:
            continue
        base = custom if row.is_custom else overrides
        skill_dir = base / row.skill_name.replace("/", "_")
        skill_dir.mkdir(parents=True, exist_ok=True)
        content = _skill_frontmatter(row.skill_name, row.description, row.body_md)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    for row in list_user_skills(session, company_id, user_id):
        base = custom if row.is_custom else overrides
        skill_dir = base / row.skill_name.replace("/", "_")
        skill_dir.mkdir(parents=True, exist_ok=True)
        content = _skill_frontmatter(row.skill_name, row.description, row.body_md)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
