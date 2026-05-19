"""Materialize per-user HERMES_HOME and credential files for an agent run."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from uuid import UUID

from symposa.runtime.context import SymposaContext, memory_key_for, set_context
from symposa.services.runtime_paths import user_hermes_home, user_runtime_root

logger = logging.getLogger(__name__)


def _log_google_credential_gaps(
    company_id: UUID,
    user_id: UUID,
    hermes_home: Path,
) -> None:
    """Log when DB says Google is connected but credential files are missing on disk."""
    try:
        from symposa.db.session import session_scope
        from symposa.services.google_oauth import google_workspace_status

        with session_scope() as session:
            status = google_workspace_status(session, company_id, user_id)
        if not status.get("connected"):
            return
        token_path = hermes_home / "google_token.json"
        client_path = hermes_home / "google_client_secret.json"
        missing = []
        if not token_path.is_file():
            missing.append("google_token.json")
        if not client_path.is_file():
            missing.append("google_client_secret.json")
        if missing:
            logger.info(
                "Google connected for user %s but missing on disk under %s: %s",
                user_id,
                hermes_home,
                ", ".join(missing),
            )
    except Exception as exc:
        logger.debug("google credential gap check skipped: %s", exc)


def bootstrap_runtime(
    company_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
    *,
    channel: str = "web",
) -> SymposaContext:
    """Create runtime directories and set process context."""
    runtime_root = user_runtime_root(user_id)
    hermes_home = user_hermes_home(user_id)
    for sub in (
        "memories",
        "skills",
        "logs",
        "company",
        "user",
    ):
        (hermes_home / sub).mkdir(parents=True, exist_ok=True)
    (runtime_root / "company").mkdir(parents=True, exist_ok=True)
    (runtime_root / "user").mkdir(parents=True, exist_ok=True)
    (runtime_root / "user" / "outputs").mkdir(parents=True, exist_ok=True)

    mk = memory_key_for(company_id, user_id, conversation_id)
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

    try:
        from symposa.db.session import session_scope, set_rls_context
        from symposa.services.credentials import materialize_user_credentials
        from symposa.services.inference_config import (
            materialize_inference_config,
            materialize_workspace_skills,
            sanitize_auth_json,
        )
        from symposa.services.skill_bundled import compute_symposa_bundled_allowlist
        from symposa2.services.skills import materialize_skills

        materialize_user_credentials(company_id, user_id, hermes_home)
        with session_scope() as session:
            set_rls_context(session, str(company_id), str(user_id))
            materialize_skills(session, company_id, user_id, hermes_home)
            allowlist = compute_symposa_bundled_allowlist(session, company_id, user_id)
            materialize_workspace_skills(hermes_home, allowlist=allowlist)
        materialize_inference_config(hermes_home)
        sanitize_auth_json(hermes_home)
        _log_google_credential_gaps(company_id, user_id, hermes_home)
    except Exception as exc:
        logger.debug("credential materialize skipped: %s", exc)

    return ctx
