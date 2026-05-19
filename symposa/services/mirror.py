"""Mirror agent turns into conversation_events using active context."""

from __future__ import annotations

from typing import Any, Dict, Optional

from symposa.db.session import session_scope
from symposa.runtime.context import get_context
from symposa.services.events import append_event


def mirror_message(
    *,
    direction: str,
    role: str,
    content_text: Optional[str] = None,
    content_json: Optional[Dict[str, Any]] = None,
) -> None:
    ctx = get_context()
    if ctx is None or not content_text:
        return
    with session_scope() as session:
        append_event(
            session,
            ctx.company_id,
            ctx.user_id,
            ctx.conversation_id,
            channel=ctx.channel,
            direction=direction,
            role=role,
            content_text=content_text,
            content_json=content_json,
        )
