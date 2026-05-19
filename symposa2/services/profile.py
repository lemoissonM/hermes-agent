"""Per-user Hermes soul (SOUL.md) from database."""

from __future__ import annotations

from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from symposa2.db.models import S2UserProfile

DEFAULT_SOUL = (
    "You are a helpful workplace assistant powered by Hermes Agent. "
    "Use available tools and skills when they help complete the user's request."
)


def get_profile(
    session: Session,
    company_id: UUID,
    user_id: UUID,
) -> Optional[S2UserProfile]:
    return session.scalar(
        select(S2UserProfile).where(
            S2UserProfile.company_id == company_id,
            S2UserProfile.user_id == user_id,
        )
    )


def upsert_profile(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    *,
    display_name: str,
    soul_md: Optional[str] = None,
) -> S2UserProfile:
    row = get_profile(session, company_id, user_id)
    if row:
        row.display_name = display_name
        if soul_md is not None:
            row.soul_md = soul_md
        session.flush()
        return row
    row = S2UserProfile(
        company_id=company_id,
        user_id=user_id,
        display_name=display_name,
        soul_md=soul_md,
    )
    session.add(row)
    session.flush()
    return row


def build_soul_md(
    session: Session,
    company_id: UUID,
    user_id: UUID,
) -> Tuple[str, str]:
    """Return (display_name, full SOUL.md body)."""
    row = get_profile(session, company_id, user_id)
    display_name = (row.display_name if row else None) or "Assistant"
    soul = (row.soul_md if row else None) or DEFAULT_SOUL
    body = (
        f"You are {display_name}.\n\n"
        f"{soul.strip()}\n\n"
        "When asked who you are, describe yourself according to this profile — "
        "not as Hermes Agent, Symposa, or a generic large language model."
    )
    return display_name, body


def materialize_soul(session: Session, company_id: UUID, user_id: UUID, hermes_home) -> None:
    from pathlib import Path

    _, body = build_soul_md(session, company_id, user_id)
    path = Path(hermes_home) / "SOUL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
