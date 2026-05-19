"""Resolve gateway_session_key for cross-channel Symposa memory."""

from __future__ import annotations


def resolve_gateway_session_key(session_key: str) -> str:
    """Use Symposa cross-channel memory key when the sidecar has set context."""
    try:
        from symposa.runtime.context import get_memory_key

        memory_key = get_memory_key()
        if memory_key:
            return memory_key
    except ImportError:
        pass
    return session_key
