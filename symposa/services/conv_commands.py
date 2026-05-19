"""Parse /conv slash commands for WhatsApp and gateway."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from symposa.services.conversations import (
    create_conversation,
    list_conversations,
    set_active_conversation,
)


@dataclass
class ConvCommandResult:
    handled: bool
    reply_text: Optional[str] = None


_CONV_RE = re.compile(r"^/conv(?:\s+(.+))?$", re.IGNORECASE | re.DOTALL)


def handle_conv_command(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    text: str,
    *,
    channel: str = "whatsapp",
) -> ConvCommandResult:
    m = _CONV_RE.match((text or "").strip())
    if not m:
        return ConvCommandResult(handled=False)
    arg = (m.group(1) or "").strip()
    if not arg or arg.lower() == "list":
        convs = list_conversations(session, company_id, user_id)
        if not convs:
            return ConvCommandResult(
                handled=True,
                reply_text="No conversations yet. Use `/conv new My topic` to create one.",
            )
        lines = ["Conversations:"]
        for c in convs[:20]:
            short = str(c.id).split("-")[0]
            lines.append(f"• {short} — {c.title}")
        lines.append("\nUse `/conv <short-id or title>` to switch.")
        return ConvCommandResult(handled=True, reply_text="\n".join(lines))
    if arg.lower().startswith("new"):
        title = arg[3:].strip() or "New conversation"
        conv = create_conversation(session, company_id, user_id, title=title)
        set_active_conversation(session, company_id, user_id, channel, conv.id)
        short = str(conv.id).split("-")[0]
        return ConvCommandResult(
            handled=True,
            reply_text=f"Created and activated: {title} ({short})",
        )
    convs = list_conversations(session, company_id, user_id)
    target = None
    arg_lower = arg.lower()
    for c in convs:
        if str(c.id).startswith(arg) or c.title.lower() == arg_lower:
            target = c
            break
    if target is None:
        for c in convs:
            if arg_lower in c.title.lower():
                target = c
                break
    if target is None:
        return ConvCommandResult(
            handled=True,
            reply_text=f"No conversation matching '{arg}'. Try `/conv list`.",
        )
    set_active_conversation(session, company_id, user_id, channel, target.id)
    short = str(target.id).split("-")[0]
    return ConvCommandResult(
        handled=True,
        reply_text=f"Active conversation: {target.title} ({short})",
    )
