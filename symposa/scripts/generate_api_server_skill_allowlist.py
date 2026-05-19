#!/usr/bin/env python3
"""Emit Symposa skill policy diagnostics."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "skills"

def _bundled_skill_names() -> list[str]:
    names: list[str] = []
    if not SKILLS_DIR.is_dir():
        return names
    for skill_md in SKILLS_DIR.rglob("SKILL.md"):
        rel = skill_md.relative_to(SKILLS_DIR)
        if len(rel.parts) >= 2:
            names.append(rel.parts[-2])
    return sorted(set(names))


def main() -> int:
    bundled = _bundled_skill_names()
    print("# Symposa exposes the normal Hermes skill surface.")
    print("skills:")
    print("  disabled: []")
    print()
    print(f"# bundled={len(bundled)} disabled=[]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
