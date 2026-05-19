"""Subprocess env bridges ContextVar HERMES_HOME override."""

from pathlib import Path

from hermes_constants import get_hermes_home, reset_hermes_home_override, set_hermes_home_override
from tools.environments.local import _make_run_env


def test_make_run_env_includes_hermes_home_override(tmp_path):
    override = tmp_path / "symposa-user"
    override.mkdir()
    token = set_hermes_home_override(override)
    try:
        run_env = _make_run_env({})
        assert run_env["HERMES_HOME"] == str(override)
        assert get_hermes_home() == override
    finally:
        reset_hermes_home_override(token)
