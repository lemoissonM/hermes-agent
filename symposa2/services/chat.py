"""Hermes gateway agent runs for Symposa2 — terminal-equivalent, not raw chat/completions."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from uuid import UUID

import httpx

from symposa.config import get_settings
from symposa.services.mirror import mirror_message
from symposa.services.runtime_paths import hermes_home_for_api_server, user_hermes_home
from symposa2.services.bootstrap import bootstrap_runtime, clear_runtime_credentials

logger = logging.getLogger(__name__)

# Same core tool surface as `hermes` in the terminal.
_CLI_TOOLSETS = "hermes-cli"

_SYMPOSA2_BACKEND_UNAVAILABLE = (
    "The assistant is temporarily unavailable. Please try again shortly."
)


def _hermes_api_base() -> str:
    return get_settings().hermes_api_url.rstrip("/")


def _auth_headers() -> Dict[str, str]:
    settings = get_settings()
    return {
        "Authorization": f"Bearer {settings.hermes_api_key or 'symposa-internal'}",
        "Content-Type": "application/json",
    }


def _prepare_run_request(
    company_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
    message: str,
    *,
    hermes_session_id: Optional[str] = None,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Bootstrap tenant runtime and build POST /v1/runs request."""
    bootstrap_runtime(company_id, user_id, conversation_id, channel="web")

    hermes_home = hermes_home_for_api_server(user_id)
    memory_key = f"symposa2:{company_id}:{user_id}:{conversation_id}"
    headers = {
        **_auth_headers(),
        "X-Hermes-Session-Key": memory_key,
        "X-Hermes-Enabled-Toolsets": _CLI_TOOLSETS,
        "X-Symposa2-Hermes-Home": hermes_home,
        "X-Symposa2-Company-Id": str(company_id),
        "X-Symposa2-User-Id": str(user_id),
        "X-Symposa2-Conversation-Id": str(conversation_id),
    }
    if hermes_session_id:
        headers["X-Hermes-Session-Id"] = hermes_session_id

    body: Dict[str, Any] = {"input": message}
    if hermes_session_id:
        body["session_id"] = hermes_session_id
    return headers, body


def _openai_role_chunk(stream_id: str, created: int) -> bytes:
    payload = {
        "id": stream_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": "hermes-agent",
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }
    return f"data: {json.dumps(payload)}\n\n".encode()


def _openai_delta_chunk(stream_id: str, created: int, content: str) -> bytes:
    payload = {
        "id": stream_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": "hermes-agent",
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }
    return f"data: {json.dumps(payload)}\n\n".encode()


def _openai_finish_chunk(stream_id: str, created: int) -> bytes:
    payload = {
        "id": stream_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": "hermes-agent",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return f"data: {json.dumps(payload)}\n\n".encode()


def _sse_event(name: str, data: Dict[str, Any]) -> bytes:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


def _parse_run_event_block(block: str) -> Optional[Dict[str, Any]]:
    data_line = ""
    for line in block.split("\n"):
        if line.startswith("data:"):
            data_line += line[5:].strip()
    if not data_line:
        return None
    try:
        parsed = json.loads(data_line)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _tool_progress_bytes(event: Dict[str, Any]) -> Optional[bytes]:
    name = str(event.get("event") or "")
    if name == "tool.started":
        tool = event.get("tool") or ""
        label = event.get("preview") or tool
        payload = {
            "tool": tool,
            "label": label,
            "status": "running",
        }
        return _sse_event("hermes.tool.progress", payload)
    if name == "tool.completed":
        tool = event.get("tool") or ""
        payload = {
            "tool": tool,
            "status": "completed",
            "error": bool(event.get("error")),
        }
        return _sse_event("hermes.tool.progress", payload)
    return None


async def chat_via_hermes_stream(
    company_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
    message: str,
    *,
    hermes_session_id: Optional[str] = None,
) -> AsyncIterator[bytes]:
    """Stream a full Hermes agent run via POST /v1/runs + GET /v1/runs/{id}/events."""
    headers, body = _prepare_run_request(
        company_id, user_id, conversation_id, message, hermes_session_id=hermes_session_id
    )
    mirror_message(direction="inbound", role="user", content_text=message)

    base = _hermes_api_base()
    stream_id = f"chatcmpl-{uuid.uuid4().hex[:29]}"
    created = int(time.time())
    accumulated: List[str] = []
    new_sid = hermes_session_id
    run_id: Optional[str] = None
    sse_buffer = ""

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            start_resp = await client.post(f"{base}/runs", headers=headers, json=body)
            if start_resp.status_code >= 400:
                detail = _SYMPOSA2_BACKEND_UNAVAILABLE
                try:
                    err_body = start_resp.json()
                    detail = (
                        err_body.get("error", {}).get("message")
                        or detail
                    )
                except Exception:
                    pass
                yield _sse_event("symposa.error", {"message": detail})
                mirror_message(direction="outbound", role="assistant", content_text=detail)
                return

            start_data = start_resp.json()
            run_id = start_data.get("run_id")
            new_sid = (
                start_resp.headers.get("X-Hermes-Session-Id")
                or start_data.get("session_id")
                or hermes_session_id
                or run_id
            )
            if not run_id:
                yield _sse_event("symposa.error", {"message": _SYMPOSA2_BACKEND_UNAVAILABLE})
                mirror_message(
                    direction="outbound",
                    role="assistant",
                    content_text=_SYMPOSA2_BACKEND_UNAVAILABLE,
                )
                return

            yield _openai_role_chunk(stream_id, created)

            async with client.stream(
                "GET",
                f"{base}/runs/{run_id}/events",
                headers=headers,
            ) as events_resp:
                if events_resp.status_code >= 400:
                    yield _sse_event("symposa.error", {"message": _SYMPOSA2_BACKEND_UNAVAILABLE})
                    mirror_message(
                        direction="outbound",
                        role="assistant",
                        content_text=_SYMPOSA2_BACKEND_UNAVAILABLE,
                    )
                    return

                async for chunk in events_resp.aiter_bytes():
                    if not chunk:
                        continue
                    sse_buffer += chunk.decode("utf-8", errors="replace")
                    while "\n\n" in sse_buffer:
                        block, sse_buffer = sse_buffer.split("\n\n", 1)
                        if not block.strip() or block.strip().startswith(":"):
                            continue
                        event = _parse_run_event_block(block)
                        if not event:
                            continue

                        event_name = str(event.get("event") or "")
                        if event_name == "message.delta":
                            delta = str(event.get("delta") or "")
                            if delta:
                                accumulated.append(delta)
                                yield _openai_delta_chunk(stream_id, created, delta)
                            continue

                        tool_bytes = _tool_progress_bytes(event)
                        if tool_bytes:
                            yield tool_bytes
                            continue

                        if event_name == "approval.request":
                            rid = str(event.get("run_id") or run_id)
                            try:
                                await asyncio.to_thread(
                                    resolve_run_approval, rid, "once"
                                )
                            except Exception as exc:
                                logger.warning(
                                    "symposa2 auto-approval failed for %s: %s", rid, exc
                                )
                                yield _sse_event(
                                    "symposa.approval",
                                    {
                                        "run_id": rid,
                                        "command": event.get("command")
                                        or event.get("preview")
                                        or "",
                                        "choices": event.get("choices")
                                        or ["once", "session", "always", "deny"],
                                    },
                                )
                            continue

                        if event_name == "run.failed":
                            err_text = str(event.get("error") or _SYMPOSA2_BACKEND_UNAVAILABLE)
                            yield _sse_event("symposa.error", {"message": err_text})
                            mirror_message(direction="outbound", role="assistant", content_text=err_text)
                            return

                        if event_name == "run.completed":
                            output = str(event.get("output") or "")
                            streamed = "".join(accumulated)
                            if output and not streamed:
                                accumulated.append(output)
                                yield _openai_delta_chunk(stream_id, created, output)
                            elif output and output != streamed and output.startswith(streamed):
                                remainder = output[len(streamed) :]
                                if remainder:
                                    accumulated.append(remainder)
                                    yield _openai_delta_chunk(stream_id, created, remainder)
                            continue

                if sse_buffer.strip() and not sse_buffer.strip().startswith(":"):
                    event = _parse_run_event_block(sse_buffer)
                    if event and event.get("event") == "run.completed":
                        output = str(event.get("output") or "")
                        streamed = "".join(accumulated)
                        if output and not streamed:
                            accumulated.append(output)
                            yield _openai_delta_chunk(stream_id, created, output)

    except httpx.HTTPError as exc:
        logger.warning("symposa2 run stream error: %s", exc)
        yield _sse_event("symposa.error", {"message": _SYMPOSA2_BACKEND_UNAVAILABLE})
        mirror_message(
            direction="outbound",
            role="assistant",
            content_text=_SYMPOSA2_BACKEND_UNAVAILABLE,
        )
        return
    finally:
        try:
            clear_runtime_credentials(user_hermes_home(user_id))
            from agent.tenant_credentials import clear_tenant_context

            clear_tenant_context()
        except Exception:
            pass

    reply = "".join(accumulated)
    if not reply:
        yield _sse_event("symposa.error", {"message": _SYMPOSA2_BACKEND_UNAVAILABLE})
        mirror_message(
            direction="outbound",
            role="assistant",
            content_text=_SYMPOSA2_BACKEND_UNAVAILABLE,
        )
        return

    mirror_message(direction="outbound", role="assistant", content_text=reply)
    yield _openai_finish_chunk(stream_id, created)
    yield b"data: [DONE]\n\n"
    done_payload = {
        "reply": reply,
        "run_id": run_id,
    }
    if new_sid:
        done_payload["hermes_session_id"] = new_sid
    yield _sse_event("symposa.done", done_payload)


def chat_via_hermes(
    company_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
    message: str,
    *,
    hermes_session_id: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    """Non-streaming chat via POST /v1/runs + poll GET /v1/runs/{id}."""
    headers, body = _prepare_run_request(
        company_id, user_id, conversation_id, message, hermes_session_id=hermes_session_id
    )
    mirror_message(direction="inbound", role="user", content_text=message)

    base = _hermes_api_base()
    reply = ""
    new_sid = hermes_session_id

    try:
        with httpx.Client(timeout=300.0) as client:
            start_resp = client.post(f"{base}/runs", headers=headers, json=body)
            start_resp.raise_for_status()
            start_data = start_resp.json()
            run_id = start_data.get("run_id")
            new_sid = (
                start_resp.headers.get("X-Hermes-Session-Id")
                or start_data.get("session_id")
                or hermes_session_id
                or run_id
            )
            if not run_id:
                reply = _SYMPOSA2_BACKEND_UNAVAILABLE
            else:
                for _ in range(600):
                    status_resp = client.get(f"{base}/runs/{run_id}", headers=headers)
                    status_resp.raise_for_status()
                    status = status_resp.json()
                    state = status.get("status")
                    if state == "completed":
                        reply = str(status.get("output") or "")
                        break
                    if state in ("failed", "cancelled"):
                        reply = str(status.get("error") or _SYMPOSA2_BACKEND_UNAVAILABLE)
                        break
                    time.sleep(0.5)
                else:
                    reply = _SYMPOSA2_BACKEND_UNAVAILABLE
    except httpx.HTTPError as exc:
        logger.warning("symposa2 run error: %s", exc)
        reply = _SYMPOSA2_BACKEND_UNAVAILABLE
    finally:
        try:
            clear_runtime_credentials(user_hermes_home(user_id))
            from agent.tenant_credentials import clear_tenant_context

            clear_tenant_context()
        except Exception:
            pass

    if reply:
        mirror_message(direction="outbound", role="assistant", content_text=reply)
    return reply or _SYMPOSA2_BACKEND_UNAVAILABLE, new_sid


def resolve_clarify_response(clarify_id: str, response: str) -> bool:
    settings = get_settings()
    base = settings.hermes_api_url.rstrip("/")
    url = f"{base}/symposa/clarify" if base.endswith("/v1") else f"{base}/v1/symposa/clarify"
    headers = _auth_headers()
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
        return bool(resp.json().get("ok"))
    except httpx.HTTPError as exc:
        logger.warning("clarify resolve failed: %s", exc)
        return False


def resolve_run_approval(run_id: str, choice: str) -> bool:
    """Resolve a pending /v1/runs approval (terminal-equivalent sudo flow)."""
    base = _hermes_api_base()
    headers = _auth_headers()
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{base}/runs/{run_id}/approval",
                headers=headers,
                json={"choice": choice},
            )
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        return bool(resp.json().get("ok", True))
    except httpx.HTTPError as exc:
        logger.warning("run approval failed: %s", exc)
        return False
