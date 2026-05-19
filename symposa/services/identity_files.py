"""Load optional per-user and per-company identity markdown from runtime dirs."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from symposa.services.runtime_paths import user_runtime_root

_MAX_IDENTITY_BYTES = 32 * 1024


def load_identity_files_block(user_id: UUID) -> str:
    """Return markdown block from runtime user/ and company/ dirs, or empty string."""
    root = user_runtime_root(user_id)
    sections: list[str] = []
    total = 0

    for label, subdir in (("User", "user"), ("Company", "company")):
        dir_path = root / subdir
        if not dir_path.is_dir():
            continue
        files = sorted(dir_path.glob("*.md"))
        if not files:
            continue
        parts: list[str] = []
        for path in files:
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError:
                continue
            encoded = raw.encode("utf-8")
            if total + len(encoded) > _MAX_IDENTITY_BYTES:
                remaining = _MAX_IDENTITY_BYTES - total
                if remaining <= 0:
                    break
                raw = encoded[:remaining].decode("utf-8", errors="ignore")
            total += len(raw.encode("utf-8"))
            parts.append(f"### {path.name}\n{raw.strip()}")
            if total >= _MAX_IDENTITY_BYTES:
                break
        if parts:
            sections.append(f"### {label} identity\n" + "\n\n".join(parts))
        if total >= _MAX_IDENTITY_BYTES:
            break

    if not sections:
        return ""
    return "## Identity files\n" + "\n\n".join(sections)
