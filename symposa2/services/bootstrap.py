"""Minimal per-user HERMES_HOME bootstrap for Symposa2."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from uuid import UUID

from symposa.db.session import session_scope, set_rls_context
from symposa.runtime.context import SymposaContext, memory_key_for, set_context
from symposa.services.inference_config import sanitize_auth_json
from symposa.services.runtime_paths import user_hermes_home, user_runtime_root
from symposa2.services.profile import materialize_soul
from symposa2.services.skills import materialize_skills
from symposa2.services.tenant_loader import install_tenant_credential_loader

logger = logging.getLogger(__name__)


def _repo_bundled_skills_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "skills"


def bootstrap_user_home(company_id: UUID, user_id: UUID, *, channel: str = "web") -> None:
    """Materialize soul/skills/credentials for a user without a chat conversation."""
    from uuid import uuid5, NAMESPACE_DNS

    conv_id = uuid5(NAMESPACE_DNS, f"{company_id}:{user_id}:home")
    bootstrap_runtime(company_id, user_id, conv_id, channel=channel)


def bootstrap_runtime(
    company_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
    *,
    channel: str = "web",
) -> SymposaContext:
    """Create runtime dirs, materialize soul/skills, set tenant context."""
    runtime_root = user_runtime_root(user_id)
    hermes_home = user_hermes_home(user_id)
    for sub in ("memories", "skills", "logs", ".runtime/credentials"):
        (hermes_home / sub).mkdir(parents=True, exist_ok=True)
    (runtime_root / "company").mkdir(parents=True, exist_ok=True)
    (runtime_root / "user").mkdir(parents=True, exist_ok=True)

    mk = f"symposa2:{company_id}:{user_id}:{conversation_id}"

    ctx = SymposaContext(
        company_id=company_id,
        user_id=user_id,
        conversation_id=conversation_id,
        memory_key=mk,
        runtime_root=str(runtime_root),
        channel=channel,
    )
    set_context(ctx)
    os.environ["HERMES_HOME"] = str(hermes_home)

    with session_scope() as session:
        set_rls_context(session, str(company_id), str(user_id))
        materialize_soul(session, company_id, user_id, hermes_home)
        materialize_skills(session, company_id, user_id, hermes_home)
        from symposa.services.skill_bundled import compute_symposa_bundled_allowlist

        allowlist = compute_symposa_bundled_allowlist(session, company_id, user_id)
        materialize_workspace_skills(hermes_home, allowlist=allowlist)
    sanitize_auth_json(hermes_home)
    install_tenant_credential_loader(company_id, user_id)
    return ctx


def clear_runtime_credentials(hermes_home: Path) -> None:
    cred_dir = hermes_home / ".runtime" / "credentials"
    if cred_dir.is_dir():
        shutil.rmtree(cred_dir, ignore_errors=True)
