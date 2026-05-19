"""Per-user Symposa runtime and HERMES_HOME path resolution."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from symposa.config import get_settings

_REPO_ROOT: Path | None = None


def _repo_root() -> Path:
    global _REPO_ROOT
    if _REPO_ROOT is None:
        _REPO_ROOT = Path(__file__).resolve().parents[2]
    return _REPO_ROOT


def resolve_runtime_root() -> Path:
    """Resolve SYMPOSA_RUNTIME_ROOT (absolute), relative paths against repo root."""
    raw = get_settings().runtime_root.strip()
    path = Path(raw)
    if not path.is_absolute():
        path = (_repo_root() / path).resolve()
    return path


def user_runtime_root(user_id: UUID) -> Path:
    return resolve_runtime_root() / "u" / str(user_id)


def user_hermes_home(user_id: UUID) -> Path:
    """Host path where Symposa materializes credential files."""
    return user_runtime_root(user_id) / ".hermes"


def hermes_home_for_api_server(user_id: UUID) -> str:
    """POSIX path the WSL api_server process must use for HERMES_HOME."""
    settings = get_settings()
    wsl_root = (settings.runtime_wsl_root or "").strip()
    if wsl_root:
        if wsl_root.startswith("/"):
            base = wsl_root.rstrip("/")
        else:
            base = str((_repo_root() / wsl_root).resolve()).replace("\\", "/")
        return f"{base}/u/{user_id}/.hermes"
    return str(user_hermes_home(user_id).resolve())
