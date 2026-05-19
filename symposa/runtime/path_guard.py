"""Restrict file tools to Symposa runtime roots."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from symposa.runtime.context import get_context

_FILE_TOOLS = frozenset(
    {
        "read_file",
        "write_file",
        "patch",
        "search_files",
    }
)


def _allowed_roots(ctx_runtime_root: str) -> list[Path]:
    root = Path(ctx_runtime_root).resolve()
    return [
        root,
        (root / ".hermes").resolve(),
        (root / "user").resolve(),
        (root / "company").resolve(),
    ]


def _path_allowed(path_str: str, roots: list[Path]) -> bool:
    try:
        p = Path(path_str).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        else:
            p = p.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            p.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def check_tool_path(tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ctx = get_context()
    if ctx is None or tool_name not in _FILE_TOOLS:
        return None
    roots = _allowed_roots(ctx.runtime_root)
    cwd = os.getenv("TERMINAL_CWD")
    if cwd and _path_allowed(cwd, roots):
        roots.append(Path(cwd).resolve())
    for key in ("path", "file_path", "target", "directory"):
        val = arguments.get(key)
        if isinstance(val, str) and val.strip() and not _path_allowed(val, roots):
            return {
                "action": "block",
                "message": f"Path not allowed outside Symposa workspace: {val}",
            }
    return None
