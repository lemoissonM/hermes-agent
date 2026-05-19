"""Company and user agent presets for system prompt injection."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from symposa.db.models import CompanyAgent, UserAgent


def build_agent_prompt_block(
    session: Session,
    company_id: UUID,
    user_id: UUID,
) -> str:
    parts: List[str] = []
    for row in session.scalars(
        select(CompanyAgent).where(CompanyAgent.company_id == company_id)
    ):
        if row.soul_text:
            parts.append(f"## Company agent: {row.name}\n{row.soul_text}")
    for row in session.scalars(
        select(UserAgent).where(
            UserAgent.company_id == company_id,
            UserAgent.user_id == user_id,
        )
    ):
        if row.soul_text:
            parts.append(f"## Your agent: {row.name}\n{row.soul_text}")
    return "\n\n".join(parts)
