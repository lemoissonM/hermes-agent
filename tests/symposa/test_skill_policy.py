"""Symposa skill policy."""

from symposa.services.skill_policy import (
    SYMPOSA_SKILL_DENYLIST,
    SYMPOSA_SKILL_ALLOWLIST,
    filter_skill_allowlist,
    is_skill_allowed,
)


def test_no_symposa_skill_exclusions():
    assert SYMPOSA_SKILL_ALLOWLIST == []
    assert SYMPOSA_SKILL_DENYLIST == []
    assert is_skill_allowed("himalaya") is True
    assert is_skill_allowed("google-workspace") is True


def test_filter_preserves_input_skills():
    skills = filter_skill_allowlist(["google-workspace", "himalaya", "nano-pdf"])
    assert skills == ["google-workspace", "himalaya", "nano-pdf"]
