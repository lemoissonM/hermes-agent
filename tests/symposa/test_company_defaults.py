"""Company workspace defaults and harvely seed."""

from symposa.db.models import Company, CompanyAgent
from symposa.services.company_defaults import (
    DEFAULT_SKILL_ALLOWLIST,
    DEFAULT_TOOLSETS,
    ensure_company_agent,
    ensure_harvely_seed,
    get_company_workspace_config,
)


def test_ensure_company_agent_creates_defaults(symposa_db):
    session, company, _user_a, _user_b = symposa_db
    row = ensure_company_agent(session, company.id)
    session.flush()
    assert row.toolsets == DEFAULT_TOOLSETS
    assert row.preloaded_skills == DEFAULT_SKILL_ALLOWLIST


def test_get_company_workspace_config(symposa_db):
    session, company, _user_a, _user_b = symposa_db
    ensure_company_agent(session, company.id)
    toolsets, skills, soul = get_company_workspace_config(session, company.id)
    assert toolsets == DEFAULT_TOOLSETS
    assert skills == DEFAULT_SKILL_ALLOWLIST
    assert soul


def test_ensure_harvely_seed(symposa_db):
    session, company, _user_a, _user_b = symposa_db
    company.name = "harvely"
    session.flush()
    ensure_harvely_seed(session)
    agents = session.query(CompanyAgent).filter_by(company_id=company.id).all()
    assert len(agents) == 1
    assert agents[0].toolsets == DEFAULT_TOOLSETS


def test_existing_company_agent_gets_normalized_toolsets(symposa_db):
    session, company, _user_a, _user_b = symposa_db
    row = CompanyAgent(
        company_id=company.id,
        name="Legacy Symposa Workspace",
        toolsets=["symposa-workspace"],
        preloaded_skills=DEFAULT_SKILL_ALLOWLIST,
    )
    session.add(row)
    session.flush()

    toolsets, _skills, _soul = get_company_workspace_config(session, company.id)

    assert toolsets == ["symposa-web"]


def test_normalize_preserves_custom_toolset(symposa_db):
    from symposa.services.company_defaults import _normalize_toolsets

    assert _normalize_toolsets(["hermes-api-server", "memory"]) == ["symposa-web", "memory"]
