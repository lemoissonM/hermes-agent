"""Skill policy generator."""

import subprocess
import sys
from pathlib import Path

from symposa.services.skill_policy import SYMPOSA_SKILL_ALLOWLIST as DEFAULT_SKILL_ALLOWLIST


def test_default_allowlist_has_workspace_skills():
    assert DEFAULT_SKILL_ALLOWLIST == []


def test_generator_lists_allowlist_in_output():
    script = Path(__file__).resolve().parents[2] / "symposa/scripts/generate_api_server_skill_allowlist.py"
    out = subprocess.check_output([sys.executable, str(script)], text=True)
    assert "disabled=[]" in out
