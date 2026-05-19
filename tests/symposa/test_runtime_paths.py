"""Runtime path resolution for Symposa per-user HERMES_HOME."""

from uuid import uuid4

import symposa.services.runtime_paths as runtime_paths
from symposa.config import get_settings
from symposa.services.runtime_paths import (
    hermes_home_for_api_server,
    resolve_runtime_root,
    user_hermes_home,
    user_runtime_root,
)


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_resolve_relative_runtime_root(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    runtime = repo / ".symposa" / "runtime"
    runtime.mkdir(parents=True)
    monkeypatch.setenv("SYMPOSA_RUNTIME_ROOT", ".symposa/runtime")
    monkeypatch.delenv("SYMPOSA_RUNTIME_WSL_ROOT", raising=False)
    monkeypatch.setattr(runtime_paths, "_REPO_ROOT", repo)
    _clear_settings_cache()

    root = resolve_runtime_root()
    assert root == runtime.resolve()


def test_hermes_home_for_api_server_wsl_mapping(monkeypatch, tmp_path):
    user_id = uuid4()
    monkeypatch.setenv("SYMPOSA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("SYMPOSA_RUNTIME_WSL_ROOT", "/mnt/c/test/.symposa/runtime")
    _clear_settings_cache()

    path = hermes_home_for_api_server(user_id)
    assert path == f"/mnt/c/test/.symposa/runtime/u/{user_id}/.hermes"


def test_user_hermes_home_without_wsl(monkeypatch, tmp_path):
    user_id = uuid4()
    monkeypatch.setenv("SYMPOSA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.delenv("SYMPOSA_RUNTIME_WSL_ROOT", raising=False)
    _clear_settings_cache()

    host = user_hermes_home(user_id)
    assert host == user_runtime_root(user_id) / ".hermes"
