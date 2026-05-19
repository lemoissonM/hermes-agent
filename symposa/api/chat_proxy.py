"""Proxy chat requests to Hermes api_server.

INVARIANT: Symposa never calls an LLM provider (RunPod, Ollama, etc.) directly.
All chat traffic uses ``SYMPOSA_HERMES_API_URL`` → Hermes ``/v1/chat/completions``.
Inference is configured in the Hermes gateway ``~/.hermes/config.yaml`` only.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from uuid import UUID

import httpx

from symposa.config import get_settings
from symposa.db.session import session_scope
from symposa.runtime.bootstrap import bootstrap_runtime
from symposa.runtime.context import memory_key_for
from symposa.services.company_defaults import get_company_workspace_config
from symposa.services.mirror import mirror_message
from symposa.services.runtime_paths import hermes_home_for_api_server, user_hermes_home
from symposa.services.user_context import build_user_context_block

logger = logging.getLogger(__name__)

_GOOGLE_IDENTITY_RE = re.compile(
    r"large language model|trained by Google",
    re.IGNORECASE,
)


def _sanitize_reply(text: str) -> str:
    """Strip infrastructure leaks from assistant replies."""
    if not text:
        return text
    out = text
    identity = "I'm Symposa, your workplace assistant."
    out = re.sub(
        r"\bI\s+am\s+a\s+large\s+language\s+model,\s+trained\s+by\s+Google\.?",
        identity,
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\bI['\u2019]\s*m\s+a\s+large\s+language\s+model,\s+trained\s+by\s+Google\.?",
        identity,
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\bI\s+am\s+a\s+large\s+language\s+model\.?",
        identity,
        out,
        flags=re.IGNORECASE,
    )
    for needle, repl in (
        ("google_token.json", "your Google connection"),
        ("HERMES_HOME", "your workspace"),
        ("himalaya", "Settings -> Integrations"),
        ("Hermes", "Symposa"),
        ("hermes-agent", "Symposa"),
    ):
        out = out.replace(needle, repl)
    return out


def _looks_like_raw_base_model(text: str) -> bool:
    return bool(_GOOGLE_IDENTITY_RE.search(text or ""))


def _hermes_chat_url() -> str:
    """Hermes api_server chat completions URL (never the LLM base URL)."""
    settings = get_settings()
    return f"{settings.hermes_api_url.rstrip('/')}/chat/completions"


def _direct_gmail_enabled() -> bool:
    return os.getenv("SYMPOSA_DIRECT_GMAIL", "").strip().lower() in ("1", "true", "yes")


def _log_credential_readiness(user_id: UUID, hermes_home_wsl: str) -> None:
    home = user_hermes_home(user_id)
    token = home / "google_token.json"
    client = home / "google_client_secret.json"
    if not token.is_file() or not client.is_file():
        logger.warning(
            "Google credential files missing for user %s (host=%s wsl=%s token=%s client=%s)",
            user_id,
            home,
            hermes_home_wsl,
            token.is_file(),
            client.is_file(),
        )


_SYMPOSA_BACKEND_UNAVAILABLE = (
    "Symposa is temporarily unable to reach the assistant backend. "
    "Try again shortly, or contact your administrator."
)


def _resolve_toolsets_header(company_id: UUID) -> str:
    with session_scope() as session:
        toolsets, _, _ = get_company_workspace_config(session, company_id)
    if not toolsets:
        return os.getenv("SYMPOSA_DEFAULT_TOOLSETS", "symposa-web")
    return ",".join(toolsets)


def _prepare_chat_request(
    company_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
    message: str,
    *,
    hermes_session_id: Optional[str] = None,
) -> Tuple[Dict[str, str], Dict[str, Any], str, Optional[str]]:
    """Bootstrap runtime and build Hermes chat/completions request pieces."""
    settings = get_settings()
    bootstrap_runtime(company_id, user_id, conversation_id, channel="web")

    with session_scope() as session:
        system_block = build_user_context_block(
            session,
            company_id,
            user_id,
            conversation_id=conversation_id,
            channel="web",
        )

    memory_key = memory_key_for(company_id, user_id, conversation_id)
    hermes_home = hermes_home_for_api_server(user_id)
    _log_credential_readiness(user_id, hermes_home)
    headers = {
        "Authorization": f"Bearer {settings.hermes_api_key or 'symposa-internal'}",
        "Content-Type": "application/json",
        "X-Hermes-Session-Key": memory_key,
        "X-Hermes-Enabled-Toolsets": _resolve_toolsets_header(company_id),
        "X-Symposa-Hermes-Home": hermes_home,
        "X-Symposa-Company-Id": str(company_id),
        "X-Symposa-User-Id": str(user_id),
        "X-Symposa-Conversation-Id": str(conversation_id),
    }
    if hermes_session_id:
        headers["X-Hermes-Session-Id"] = hermes_session_id

    messages: List[Dict[str, str]] = []
    if system_block:
        messages.append({"role": "system", "content": system_block})
    messages.append({"role": "user", "content": message})

    body = {
        "messages": messages,
    }
    return headers, body, _hermes_chat_url(), system_block


def _extract_delta_content(line: str) -> str:
    """Parse OpenAI SSE data line for delta content."""
    if not line.startswith("data:"):
        return ""
    payload = line[5:].strip()
    if payload == "[DONE]":
        return ""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    choices = data.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    return str(delta.get("content") or "")


async def chat_via_hermes_stream(
    company_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
    message: str,
    *,
    hermes_session_id: Optional[str] = None,
) -> AsyncIterator[bytes]:
    """Stream Hermes SSE to the client; emit symposa.done when complete."""
    headers, body, url, _system_block = _prepare_chat_request(
        company_id,
        user_id,
        conversation_id,
        message,
        hermes_session_id=hermes_session_id,
    )
    mirror_message(direction="inbound", role="user", content_text=message)
    body["stream"] = True

    accumulated: List[str] = []
    new_sid = hermes_session_id
    raw_buffer = ""

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code >= 400:
                    err = json.dumps(
                        {"message": _SYMPOSA_BACKEND_UNAVAILABLE},
                        ensure_ascii=False,
                    )
                    yield f"event: symposa.error\ndata: {err}\n\n".encode()
                    mirror_message(
                        direction="outbound",
                        role="assistant",
                        content_text=_SYMPOSA_BACKEND_UNAVAILABLE,
                    )
                    return
                new_sid = resp.headers.get("X-Hermes-Session-Id") or hermes_session_id
                async for chunk in resp.aiter_bytes():
                    if not chunk:
                        continue
                    yield chunk
                    try:
                        raw_buffer += chunk.decode("utf-8", errors="replace")
                    except Exception:
                        continue
                    while "\n" in raw_buffer:
                        line, raw_buffer = raw_buffer.split("\n", 1)
                        piece = _extract_delta_content(line.strip())
                        if piece:
                            accumulated.append(piece)
    except httpx.HTTPError as exc:
        logger.warning("symposa assistant stream error: %s", exc)
        err = json.dumps({"message": _SYMPOSA_BACKEND_UNAVAILABLE}, ensure_ascii=False)
        yield f"event: symposa.error\ndata: {err}\n\n".encode()
        mirror_message(
            direction="outbound",
            role="assistant",
            content_text=_SYMPOSA_BACKEND_UNAVAILABLE,
        )
        return

    reply = _sanitize_reply("".join(accumulated))
    if reply:
        mirror_message(direction="outbound", role="assistant", content_text=reply)
    done = json.dumps(
        {
            "hermes_session_id": new_sid,
            "reply": reply,
            "raw_model_hint": _looks_like_raw_base_model(reply),
        },
        ensure_ascii=False,
    )
    yield f"event: symposa.done\ndata: {done}\n\n".encode()


def chat_via_hermes(
    company_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
    message: str,
    *,
    hermes_session_id: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    headers, body, url, _system_block = _prepare_chat_request(
        company_id,
        user_id,
        conversation_id,
        message,
        hermes_session_id=hermes_session_id,
    )
    mirror_message(direction="inbound", role="user", content_text=message)
    body["stream"] = False

    try:
        with httpx.Client(timeout=300.0) as client:
            resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("symposa assistant backend error: %s", exc)
        mirror_message(direction="outbound", role="assistant", content_text=_SYMPOSA_BACKEND_UNAVAILABLE)
        return _SYMPOSA_BACKEND_UNAVAILABLE, hermes_session_id

    reply = ""
    choices = data.get("choices") or []
    if choices:
        msg = choices[0].get("message") or {}
        reply = msg.get("content") or ""
    new_sid = resp.headers.get("X-Hermes-Session-Id") or hermes_session_id
    if reply:
        reply = _sanitize_reply(reply)
        mirror_message(direction="outbound", role="assistant", content_text=reply)
    return reply, new_sid


def resolve_clarify_response(clarify_id: str, response: str) -> bool:
    """Proxy clarify resolution to Hermes api_server (clarify state lives in gateway)."""
    settings = get_settings()
    base = settings.hermes_api_url.rstrip("/")
    if base.endswith("/v1"):
        url = f"{base}/symposa/clarify"
    else:
        url = f"{base}/v1/symposa/clarify"
    headers = {
        "Authorization": f"Bearer {settings.hermes_api_key or 'symposa-internal'}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                url,
                headers=headers,
                json={"clarify_id": clarify_id, "response": response},
            )
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        data = resp.json()
        return bool(data.get("ok"))
    except httpx.HTTPError as exc:
        logger.warning("clarify resolve proxy failed: %s", exc)
        return False
