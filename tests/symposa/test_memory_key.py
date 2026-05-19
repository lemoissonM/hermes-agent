"""Memory key format tests."""

from uuid import uuid4

from symposa.runtime.context import memory_key_for


def test_memory_key_format():
    c, u, conv = uuid4(), uuid4(), uuid4()
    key = memory_key_for(c, u, conv)
    assert key == f"symposa:{c}:{u}:{conv}"
