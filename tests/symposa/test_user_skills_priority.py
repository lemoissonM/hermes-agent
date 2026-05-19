"""User skill priority: preload, resolver, bundled allowlist, gateway context."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from symposa.services.inference_config import materialize_workspace_skills
from symposa.services.skill_bundled import compute_symposa_bundled_allowlist, find_bundled_skill_dirs
from symposa.services.skills import resolve_skill_body
from symposa.services.user_context import build_user_context_block
from symposa.services.user_skills_prompt import collect_user_skill_identifiers
from symposa2.services.skills import materialize_skills, upsert_user_skill


def test_collect_user_skill_identifiers_custom_before_override(symposa_db):
    session, company, user_a, _ = symposa_db
    upsert_user_skill(
        session,
        company.id,
        user_a.id,
        "my-custom",
        "# Custom skill\n",
        is_custom=True,
    )
    upsert_user_skill(
        session,
        company.id,
        user_a.id,
        "google-workspace",
        "# Override\n",
        is_custom=False,
    )
    session.commit()
    names = collect_user_skill_identifiers(session, company.id, user_a.id)
    assert names[0] == "my-custom"
    assert "google-workspace" in names


def test_resolve_skill_body_s2_user_skill(symposa_db):
    session, company, user_a, _ = symposa_db
    upsert_user_skill(
        session,
        company.id,
        user_a.id,
        "acme-workflow",
        "# ACME\nAlways say SYMPOSA_SKILL_OK.\n",
        description="ACME workflow",
        is_custom=True,
    )
    session.commit()
    resolved = resolve_skill_body(session, company.id, user_a.id, "acme-workflow")
    assert resolved is not None
    assert "SYMPOSA_SKILL_OK" in resolved[0]
    assert resolved[1] == "ACME workflow"


def test_user_skills_preload_in_context_block(symposa_db, monkeypatch, tmp_path):
    session, company, user_a, _ = symposa_db
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    upsert_user_skill(
        session,
        company.id,
        user_a.id,
        "priority-skill",
        "---\nname: priority-skill\ndescription: Priority test.\n---\n\nAlways SYMPOSA_PRELOAD_OK.\n",
        description="Priority test.",
        is_custom=True,
    )
    session.commit()
    materialize_skills(session, company.id, user_a.id, hermes_home)

    block = build_user_context_block(
        session,
        company.id,
        user_a.id,
        conversation_id=uuid4(),
    )
    assert "User skills (priority)" in block
    assert "SYMPOSA_PRELOAD_OK" in block or "priority-skill" in block


def test_skills_prompt_lists_custom_first(monkeypatch, tmp_path):
    from agent.prompt_builder import build_skills_system_prompt, clear_skills_system_prompt_cache

    clear_skills_system_prompt_cache(clear_snapshot=True)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    skills_root = tmp_path / "skills"
    custom = skills_root / "custom" / "user-skill"
    custom.mkdir(parents=True)
    (custom / "SKILL.md").write_text(
        "---\nname: user-skill\ndescription: User authored.\n---\n",
        encoding="utf-8",
    )
    other = skills_root / "mlops" / "other-skill"
    other.mkdir(parents=True)
    (other / "SKILL.md").write_text(
        "---\nname: other-skill\ndescription: Bundled example.\n---\n",
        encoding="utf-8",
    )

    result = build_skills_system_prompt()
    clear_skills_system_prompt_cache(clear_snapshot=True)

    priority_pos = result.find("Your skills (priority)")
    mlops_pos = result.find("mlops")
    assert priority_pos != -1
    assert mlops_pos != -1
    assert priority_pos < mlops_pos
    assert "user-skill" in result


def test_materialize_workspace_skills_allowlist(monkeypatch, tmp_path):
    bundled = tmp_path / "repo_skills"
    gw = bundled / "productivity" / "google-workspace"
    gw.mkdir(parents=True)
    (gw / "SKILL.md").write_text(
        "---\nname: google-workspace\ndescription: Google apps.\n---\n",
        encoding="utf-8",
    )
    other = bundled / "mlops" / "other-skill"
    other.mkdir(parents=True)
    (other / "SKILL.md").write_text(
        "---\nname: other-skill\ndescription: Other.\n---\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "symposa.services.inference_config._bundled_skills_dir",
        lambda: bundled,
    )
    monkeypatch.setattr(
        "symposa.services.skill_bundled._bundled_skills_dir",
        lambda: bundled,
    )

    hermes_home = tmp_path / "user_hermes"
    materialize_workspace_skills(hermes_home, allowlist=["google-workspace"])
    assert (hermes_home / "skills" / "productivity" / "google-workspace" / "SKILL.md").is_file()
    assert not (hermes_home / "skills" / "mlops" / "other-skill" / "SKILL.md").exists()

    materialize_workspace_skills(hermes_home, allowlist=["google-workspace"])
    assert (hermes_home / ".symposa" / "bundled_skills_stamp.json").is_file()


def test_compute_symposa_bundled_allowlist_includes_essentials(symposa_db):
    session, company, user_a, _ = symposa_db
    allowlist = compute_symposa_bundled_allowlist(session, company.id, user_a.id)
    assert "google-workspace" in allowlist


def test_find_bundled_skill_dirs_by_name(tmp_path):
    bundled = tmp_path / "skills"
    skill_dir = bundled / "productivity" / "google-workspace"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: google-workspace\ndescription: GW.\n---\n",
        encoding="utf-8",
    )
    found = find_bundled_skill_dirs(bundled, ["google-workspace"])
    assert len(found) == 1
    assert found[0].name == "google-workspace"


def test_api_server_sets_symposa_context_symposa2():
    from gateway.platforms.api_server import APIServerAdapter

    adapter = APIServerAdapter.__new__(APIServerAdapter)
    company_id = str(uuid4())
    user_id = str(uuid4())
    conv_id = str(uuid4())

    with patch("symposa.runtime.context.set_context") as mock_set:
        adapter._set_symposa_context(
            company_id=company_id,
            user_id=user_id,
            conversation_id=conv_id,
            session_key="sess-key",
            symposa_hermes_home="/tmp/hermes",
        )
        mock_set.assert_called_once()
        ctx = mock_set.call_args[0][0]
        assert str(ctx.company_id) == company_id
        assert str(ctx.user_id) == user_id
