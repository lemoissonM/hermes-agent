"""Per-user runtime materialization for Symposa (skills only — gateway owns inference)."""

from pathlib import Path

import yaml

from symposa.services.inference_config import (
    build_skills_config,
    materialize_inference_config,
    materialize_workspace_skills,
    sanitize_all_runtime_auth_files,
    sanitize_auth_json,
)


def test_materialize_inference_config_skills_only(tmp_path, monkeypatch):
    monkeypatch.setenv("SYMPOSA_HERMES_BASE_URL", "https://example.runpod.net/v1")
    monkeypatch.setenv("SYMPOSA_LLM_API_KEY", "key")
    from symposa.config import get_settings

    get_settings.cache_clear()
    try:
        home = tmp_path / ".hermes"
        home.mkdir()
        (home / "config.yaml").write_text(
            "model:\n  provider: custom\n  base_url: https://stale.example/v1\n",
            encoding="utf-8",
        )
        assert materialize_inference_config(home) is True
        data = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
        assert "model" not in data
        assert data["skills"]["disabled"] == []
    finally:
        get_settings.cache_clear()


def test_build_skills_config_disables_no_skills():
    cfg = build_skills_config()

    assert cfg["disabled"] == []


def test_materialize_workspace_skills_copies_bundled_skills(tmp_path):
    home = tmp_path / ".hermes"

    materialize_workspace_skills(home)

    assert (
        home / "skills" / "productivity" / "google-workspace" / "SKILL.md"
    ).is_file()


def test_sanitize_all_runtime_auth_files(tmp_path, monkeypatch):
    monkeypatch.setenv("SYMPOSA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    from symposa.config import get_settings

    get_settings.cache_clear()
    try:
        u1 = tmp_path / "runtime" / "u" / "aaa" / ".hermes"
        u2 = tmp_path / "runtime" / "u" / "bbb" / ".hermes"
        for home in (u1, u2):
            home.mkdir(parents=True)
            (home / "auth.json").write_text('{"credential_pool": {"x": []}}', encoding="utf-8")
        assert sanitize_all_runtime_auth_files() == 2
        assert "credential_pool" not in (u1 / "auth.json").read_text(encoding="utf-8")
    finally:
        get_settings.cache_clear()
