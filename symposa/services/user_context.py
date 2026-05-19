"""Build per-user identity blocks for Symposa ephemeral system prompts."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from symposa.db.models import ChannelIdentity, Company, User
from symposa.services.agents import build_agent_prompt_block
from symposa.services.branding import SYMPOSA_AGENT_RULES
from symposa.services.google_oauth import google_workspace_status
from symposa.services.identity_files import load_identity_files_block
from symposa.services.user_skills_prompt import build_user_skills_preload_block


def build_user_context_block(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    *,
    conversation_id: Optional[UUID] = None,
    channel: str = "web",
) -> str:
    """Stable identity + integration status for the active Symposa user."""
    company = session.get(Company, company_id)
    user = session.get(User, user_id)
    if company is None or user is None:
        return ""

    identities = list(
        session.scalars(
            select(ChannelIdentity).where(
                ChannelIdentity.company_id == company_id,
                ChannelIdentity.user_id == user_id,
            )
        )
    )
    channel_lines = []
    for ident in identities:
        channel_lines.append(f"- {ident.channel}: {ident.external_id}")

    g_status = google_workspace_status(session, company_id, user_id)

    parts = [
        SYMPOSA_AGENT_RULES.strip(),
        "## Symposa session context (internal)",
        f"- Company: {company.name} (id: {company_id})",
        f"- User: {user.email} (id: {user_id}, role: {user.role})",
    ]
    if conversation_id:
        parts.append(f"- Active conversation: {conversation_id}")
    parts.append(f"- Active channel: {channel}")
    if channel_lines:
        parts.append("### Linked channels")
        parts.extend(channel_lines)
    parts.append(f"### Google Workspace: {g_status.get('summary', 'unknown')}")
    if g_status.get("connected"):
        parts.append(
            "- Credentials are loaded from Symposa for this user on each request. "
            "Use the `google-workspace` skill (GAPI) immediately — do not check the "
            "filesystem for token files or suggest other email tools."
        )
    parts.extend(
        [
            "### Behavior",
            "- Address this user by their email or name from this block.",
            '- For "who am I" / identity questions, answer ONLY from this Symposa context.',
            '- For "what can you do" / capability questions, answer as Symposa and mention workspace/tool actions; do not describe yourself as a generic model.',
            "- Do not invent a different user, company, or email.",
            "### Email and Google Workspace",
            "- Use the `google-workspace` skill for Gmail, Calendar, Drive, Sheets, and Docs.",
            "- Other Hermes tools remain available when they fit the task.",
            "- If Google is not connected, direct the user to Settings → Integrations → Connect Google.",
        ]
    )
    agent_block = build_agent_prompt_block(session, company_id, user_id)
    if agent_block:
        parts.append(agent_block)
    identity_block = load_identity_files_block(user_id)
    if identity_block:
        parts.append(identity_block)
    skills_block = build_user_skills_preload_block(
        session,
        company_id,
        user_id,
        task_id=str(conversation_id) if conversation_id else None,
    )
    if skills_block:
        parts.append(skills_block)
    return "\n".join(parts)
