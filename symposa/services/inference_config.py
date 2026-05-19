"""Per-user Hermes runtime materialization (skills/credentials only — not LLM routing).

Symposa chat never calls an LLM endpoint directly. Inference is configured in the
Hermes gateway ``~/.hermes/config.yaml``. Per-user ``.hermes`` trees hold
credentials, skills, and memory only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _bundled_skills_dir() -> Path:
    return _repo_root() / "skills"


def build_skills_config() -> Dict[str, Any]:
    """Return skill config that clears prior Symposa exclusions."""
    return {"disabled": []}


def _bundled_skills_stamp_path(hermes_home: Path) -> Path:
    return hermes_home / ".symposa" / "bundled_skills_stamp.json"


def _bundled_allowlist_revision(allowlist: List[str]) -> str:
    payload = {"allowlist": sorted({(n or "").strip() for n in allowlist if (n or "").strip()})}
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def materialize_workspace_skills(
    hermes_home: Path,
    allowlist: Optional[List[str]] = None,
) -> None:
    """Mirror bundled skills into a user's HERMES_HOME.

    When *allowlist* is provided, only those skills are copied and a stamp file
    skips repeat work until the allowlist changes. When *allowlist* is ``None``,
    copies the entire bundled tree (legacy behavior).
    """
    bundled_dir = _bundled_skills_dir()
    if not bundled_dir.is_dir():
        logger.debug("Bundled skills directory not found: %s", bundled_dir)
        return

    target_root = hermes_home / "skills"
    target_root.mkdir(parents=True, exist_ok=True)

    if allowlist is None:
        for skill_md in bundled_dir.rglob("SKILL.md"):
            rel_dir = skill_md.parent.relative_to(bundled_dir)
            shutil.copytree(skill_md.parent, target_root / rel_dir, dirs_exist_ok=True)
        return

    from symposa.services.skill_bundled import find_bundled_skill_dirs

    normalized = sorted({(n or "").strip() for n in allowlist if (n or "").strip()})
    revision = _bundled_allowlist_revision(normalized)
    stamp_path = _bundled_skills_stamp_path(hermes_home)
    if stamp_path.is_file():
        try:
            stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
            if isinstance(stamp, dict) and stamp.get("revision") == revision:
                return
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Could not read bundled skills stamp: %s", exc)

    old_allowlist: List[str] = []
    if stamp_path.is_file():
        try:
            stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
            if isinstance(stamp, dict):
                old_allowlist = list(stamp.get("allowlist") or [])
        except (json.JSONDecodeError, OSError):
            pass

    removed = set(old_allowlist) - set(normalized)
    if removed:
        for skill_dir in find_bundled_skill_dirs(bundled_dir, removed):
            rel_dir = skill_dir.relative_to(bundled_dir)
            dest = target_root / rel_dir
            if dest.is_dir() and rel_dir.parts[:1] not in (("custom",), ("_overrides",)):
                shutil.rmtree(dest, ignore_errors=True)

    for skill_dir in find_bundled_skill_dirs(bundled_dir, normalized):
        rel_dir = skill_dir.relative_to(bundled_dir)
        shutil.copytree(skill_dir, target_root / rel_dir, dirs_exist_ok=True)

    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text(
        json.dumps({"revision": revision, "allowlist": normalized}, indent=2),
        encoding="utf-8",
    )


def materialize_inference_config(hermes_home: Path) -> bool:
    """Write skills config into per-user HERMES_HOME (no model block).

    Gateway-owned inference: do not materialize ``SYMPOSA_HERMES_BASE_URL`` into
    per-user config. Stale ``model:`` keys from older Symposa versions are removed.
    """
    skills_cfg = build_skills_config()
    hermes_home.mkdir(parents=True, exist_ok=True)
    path = hermes_home / "config.yaml"
    existing: Dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                existing = loaded
        except Exception as exc:
            logger.debug("Could not read existing config at %s: %s", path, exc)
    merged = dict(existing)
    merged.pop("model", None)
    current_skills = merged.get("skills")
    if not isinstance(current_skills, dict):
        current_skills = {}
    current_skills = dict(current_skills)
    current_skills["disabled"] = skills_cfg["disabled"]
    merged["skills"] = current_skills
    path.write_text(yaml.safe_dump(merged, default_flow_style=False), encoding="utf-8")
    return True


def sanitize_auth_json(hermes_home: Path) -> bool:
    """Remove credential_pool from per-user auth.json."""
    path = hermes_home / "auth.json"
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("Could not read auth.json at %s: %s", path, exc)
        return False
    if not isinstance(data, dict) or "credential_pool" not in data:
        return False
    del data["credential_pool"]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return True


def sanitize_all_runtime_auth_files() -> int:
    """Strip credential_pool from every per-user runtime auth.json (one-shot / startup)."""
    from symposa.services.runtime_paths import resolve_runtime_root

    root = resolve_runtime_root() / "u"
    if not root.is_dir():
        return 0
    changed = 0
    for auth_path in root.glob("*/.hermes/auth.json"):
        if sanitize_auth_json(auth_path.parent):
            changed += 1
    return changed
