"""Symposa Hermes plugin — gateway identity, conversation routing, mirroring."""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

_COMPANY_ENV = "SYMPOSA_COMPANY_ID"


def _default_company_id() -> Optional[UUID]:
    raw = os.getenv(_COMPANY_ENV, "").strip()
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


def register(ctx) -> None:
    ctx.register_hook("pre_gateway_dispatch", _pre_gateway_dispatch)
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("on_session_end", _on_session_end)
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("transform_tool_result", _transform_tool_result)
    ctx.register_hook("post_llm_call", _post_llm_call)
    logger.info("Symposa plugin registered")


def _pre_gateway_dispatch(event=None, gateway=None, session_store=None, **kwargs) -> Optional[Dict[str, Any]]:
    if event is None or not getattr(event, "text", None):
        return None
    company_id = _default_company_id()
    if company_id is None:
        return None
    source = event.source
    platform = source.platform.value if source.platform else ""
    if platform != "whatsapp":
        return None

    from symposa.db.session import session_scope
    from symposa.services.conv_commands import handle_conv_command
    from symposa.services.identity import canonical_whatsapp_external_id, resolve_user_by_channel
    from symposa.services.conversations import get_or_create_active_conversation
    from symposa.runtime.bootstrap import bootstrap_runtime
    from symposa.config import get_settings

    ext = canonical_whatsapp_external_id(source.user_id or source.chat_id or "")
    if not ext:
        return {"action": "skip", "reason": "no whatsapp identity"}

    with session_scope() as session:
        user = resolve_user_by_channel(session, company_id, "whatsapp", ext)
        if user is None:
            link = get_settings().link_base_url
            return {
                "action": "skip",
                "reason": "unknown whatsapp user",
                "send_reply": (
                    f"This number is not linked to a Symposa account. "
                    f"Link it in the web app: {link}/settings/channels"
                ),
            }
        conv_result = handle_conv_command(
            session, company_id, user.id, event.text, channel="whatsapp"
        )
        if conv_result.handled:
            return {
                "action": "skip",
                "reason": "conv command",
                "send_reply": conv_result.reply_text or "OK",
            }
        conv = get_or_create_active_conversation(
            session, company_id, user.id, "whatsapp", default_title="WhatsApp"
        )
        conversation_id = conv.id

    bootstrap_runtime(company_id, user.id, conversation_id, channel="whatsapp")
    try:
        from symposa.services.mirror import mirror_message

        if event.text and not event.text.strip().lower().startswith("/conv"):
            mirror_message(direction="inbound", role="user", content_text=event.text)
    except Exception:
        pass
    return None


def _on_session_start(session_id: str = "", **kwargs) -> None:
    ctx = None
    try:
        from symposa.runtime.context import get_context

        ctx = get_context()
    except ImportError:
        return
    if ctx is None:
        return
    try:
        from symposa.db.session import session_scope
        from symposa.services.channel_sessions import upsert_channel_session

        platform = kwargs.get("platform") or "unknown"
        session_key = kwargs.get("session_key") or ""
        with session_scope() as session:
            from symposa.services.user_context import build_user_context_block

            block = build_user_context_block(
                session,
                ctx.company_id,
                ctx.user_id,
                conversation_id=ctx.conversation_id,
                channel=ctx.channel or platform,
            )
            if session_key:
                upsert_channel_session(
                    session,
                    ctx.conversation_id,
                    platform,
                    session_key,
                    session_id or None,
                )
        if block:
            os.environ["HERMES_EPHEMERAL_SYSTEM_PROMPT"] = block
    except Exception as exc:
        logger.debug("on_session_start symposa: %s", exc)


def _on_session_end(session_id: str = "", messages=None, **kwargs) -> None:
    try:
        from symposa.runtime.context import get_context
        from symposa.services.mirror import mirror_message

        ctx = get_context()
        if ctx is None or not messages:
            return
        for msg in messages or []:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            if role != "assistant":
                continue
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                mirror_message(direction="outbound", role="assistant", content_text=content)
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("on_session_end mirror: %s", exc)


def _sanitize_user_facing_text(text: str) -> str:
    """Light guard against infrastructure leaks in mirrored assistant text."""
    if not text:
        return text
    out = text
    out = re.sub(
        r"\bI\s+am\s+a\s+large\s+language\s+model,\s+trained\s+by\s+Google\.?",
        "I’m Symposa, your workplace assistant.",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\bI['’]m\s+a\s+large\s+language\s+model,\s+trained\s+by\s+Google\.?",
        "I’m Symposa, your workplace assistant.",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\bI\s+am\s+a\s+large\s+language\s+model\.?",
        "I’m Symposa, your workplace assistant.",
        out,
        flags=re.IGNORECASE,
    )
    for needle, repl in (
        ("google_token.json", "your Google connection"),
        ("HERMES_HOME", "your workspace"),
        ("himalaya", "Settings → Integrations"),
        ("Hermes", "Symposa"),
        ("hermes-agent", "Symposa"),
    ):
        out = out.replace(needle, repl)
    out = out.replace("I\u2019m Symposa, your workplace assistant.", "I'm Symposa, your workplace assistant.")
    out = out.replace("I\u00e2\u20ac\u2122m Symposa, your workplace assistant.", "I'm Symposa, your workplace assistant.")
    out = out.replace("Settings \u00e2\u2020\u2019 Integrations", "Settings -> Integrations")
    return out


def _post_llm_call(response: Any = None, **kwargs) -> None:
    try:
        from symposa.runtime.context import get_context
        from symposa.services.mirror import mirror_message

        ctx = get_context()
        if ctx is None or response is None:
            return
        text = None
        if isinstance(response, dict):
            choices = response.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                text = msg.get("content")
        elif isinstance(response, str):
            text = response
        if text:
            mirror_message(
                direction="outbound",
                role="assistant",
                content_text=_sanitize_user_facing_text(text),
            )
    except ImportError:
        pass


def _pre_tool_call(tool_name: str = "", arguments: Optional[Dict[str, Any]] = None, **kwargs) -> Optional[Dict[str, Any]]:
    try:
        from symposa.runtime.path_guard import check_tool_path

        return check_tool_path(tool_name, arguments or {})
    except ImportError:
        return None


def _transform_tool_result(
    tool_name: str = "",
    args: Optional[Dict[str, Any]] = None,
    result: Any = None,
    **kwargs,
) -> Optional[str]:
    """Register workspace files and inject view/share URLs into tool results."""
    if tool_name not in ("write_file", "patch"):
        return None
    try:
        from symposa.runtime.context import get_context
        from symposa.db.session import session_scope, set_rls_context
        from symposa.services.files import file_to_dict, register_workspace_file
    except ImportError:
        return None

    ctx = get_context()
    if ctx is None:
        return None

    arguments = args or {}
    path_str = arguments.get("path") or arguments.get("file_path")
    if not isinstance(path_str, str) or not path_str.strip():
        return None

    if isinstance(result, str):
        try:
            import json

            parsed = json.loads(result)
        except json.JSONDecodeError:
            return None
    elif isinstance(result, dict):
        parsed = result
    else:
        return None

    if not parsed.get("success", True):
        return None

    written = parsed.get("path") or path_str
    try:
        from pathlib import Path

        resolved = Path(written).expanduser()
        if not resolved.is_absolute():
            resolved = (Path.cwd() / resolved).resolve()
        if not resolved.is_file():
            return None
    except OSError:
        return None

    try:
        with session_scope() as session:
            set_rls_context(session, str(ctx.company_id), str(ctx.user_id))
            row = register_workspace_file(
                session,
                ctx.company_id,
                ctx.user_id,
                resolved,
            )
            urls = file_to_dict(row, include_share=True)
    except (ImportError, FileNotFoundError, PermissionError, ValueError) as exc:
        logger.debug("symposa file register skipped: %s", exc)
        return None
    except Exception as exc:
        logger.warning("symposa file register failed: %s", exc)
        return None

    merged = dict(parsed)
    merged["file_id"] = urls["id"]
    merged["view_url"] = urls["view_url"]
    merged["download_url"] = urls["download_url"]
    merged["share_url"] = urls.get("share_url")
    import json

    return json.dumps(merged)
