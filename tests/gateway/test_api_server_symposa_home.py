"""api_server and hermes_constants Symposa HERMES_HOME override."""

import asyncio
import contextvars
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hermes_constants import (
    get_hermes_home,
    reset_hermes_home_override,
    set_hermes_home_override,
)


def test_get_hermes_home_context_override(tmp_path, monkeypatch):
    override = tmp_path / "symposa-user-hermes"
    override.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "env-home"))

    token = set_hermes_home_override(override)
    try:
        assert get_hermes_home() == override
    finally:
        reset_hermes_home_override(token)

    assert get_hermes_home() == Path(tmp_path / "env-home")


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("aiohttp"),
    reason="aiohttp required",
)
def test_parse_symposa_hermes_home_header():
    from gateway.platforms.api_server import APIServerAdapter

    adapter = APIServerAdapter.__new__(APIServerAdapter)
    adapter._api_key = "test-key"

    req = MagicMock()
    req.headers = {"X-Symposa-Hermes-Home": "/mnt/c/symposa/runtime/u/abc/.hermes"}
    path, err = adapter._parse_symposa_hermes_home_header(req)
    assert err is None
    assert path == "/mnt/c/symposa/runtime/u/abc/.hermes"

    req.headers = {"X-Symposa-Hermes-Home": "relative/path"}
    path, err = adapter._parse_symposa_hermes_home_header(req)
    assert path is None
    assert err is not None

    req.headers = {"X-Symposa-Hermes-Home": "/mnt/c/../etc/passwd"}
    path, err = adapter._parse_symposa_hermes_home_header(req)
    assert path is None
    assert err is not None


def test_run_executor_preserves_hermes_home_override(tmp_path, monkeypatch):
    """/v1/runs must propagate HERMES_HOME override into the worker thread."""
    override = tmp_path / "symposa-user"
    override.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "gateway-home"))
    seen: list[Path] = []

    def worker():
        token = set_hermes_home_override(override)
        try:
            seen.append(get_hermes_home())
        finally:
            reset_hermes_home_override(token)

    async def _run():
        ctx = contextvars.copy_context()
        await asyncio.get_running_loop().run_in_executor(None, ctx.run, worker)

    asyncio.run(_run())
    assert seen == [override]


def test_session_db_for_home_isolated(tmp_path):
    from gateway.platforms.api_server import APIServerAdapter

    adapter = APIServerAdapter.__new__(APIServerAdapter)
    adapter._session_db = None
    adapter._session_db_by_home = {}
    adapter._session_db_by_home_lock = __import__("threading").Lock()

    home_a = tmp_path / "user-a" / ".hermes"
    home_b = tmp_path / "user-b" / ".hermes"
    home_a.mkdir(parents=True)
    home_b.mkdir(parents=True)

    db_a = adapter._session_db_for_home(str(home_a))
    db_b = adapter._session_db_for_home(str(home_b))
    gateway_db = adapter._ensure_session_db()

    assert db_a is not None
    assert db_b is not None
    assert db_a.db_path != db_b.db_path
    assert db_a.db_path == home_a / "state.db"
    assert db_b.db_path == home_b / "state.db"
    assert gateway_db is not None
    assert gateway_db.db_path != db_a.db_path
