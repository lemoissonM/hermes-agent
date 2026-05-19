"""Task-local Symposa tenancy context (mirrors gateway.session_context pattern)."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass(frozen=True)
class SymposaContext:
    company_id: UUID
    user_id: UUID
    conversation_id: UUID
    memory_key: str
    runtime_root: str
    channel: str = "web"


_CTX: ContextVar[Optional[SymposaContext]] = ContextVar("symposa_ctx", default=None)


def memory_key_for(company_id: UUID, user_id: UUID, conversation_id: UUID) -> str:
    return f"symposa:{company_id}:{user_id}:{conversation_id}"


def set_context(ctx: SymposaContext) -> None:
    _CTX.set(ctx)


def get_context() -> Optional[SymposaContext]:
    return _CTX.get()


def get_memory_key() -> Optional[str]:
    ctx = get_context()
    return ctx.memory_key if ctx else None


def clear_context() -> None:
    _CTX.set(None)
