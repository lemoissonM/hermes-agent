"""Gateway memory key resolver."""

from unittest.mock import patch

from symposa.runtime.memory_key import resolve_gateway_session_key as _resolve_gateway_session_key


def test_resolve_falls_back_to_session_key():
    assert _resolve_gateway_session_key("agent:main:web:dm:1") == "agent:main:web:dm:1"


def test_resolve_uses_symposa_key_when_set():
    with patch("symposa.runtime.context.get_memory_key", return_value="symposa:co:u:conv"):
        assert _resolve_gateway_session_key("agent:main:whatsapp:dm:x") == "symposa:co:u:conv"
