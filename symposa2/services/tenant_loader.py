"""Bridge Symposa2 DB credentials into agent/tenant_credentials loader."""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from symposa.db.session import session_scope, set_rls_context
from symposa2.services.credentials import (
    build_integration_env_overlay,
    resolve_provider_payload,
)
from symposa2.services.credential_registry import provider_for_env, provider_for_file


def _loader(company_id: UUID, user_id: UUID):
    def load_provider(provider_key: str) -> Optional[Dict[str, Any]]:
        with session_scope() as session:
            set_rls_context(session, str(company_id), str(user_id))
            return resolve_provider_payload(session, company_id, user_id, provider_key)

    def load_file(relative_path: str) -> Optional[Dict[str, Any]]:
        provider = provider_for_file(relative_path)
        if not provider:
            return None
        return load_provider(provider)

    def load_env(env_name: str) -> Optional[str]:
        provider = provider_for_env(env_name)
        if not provider:
            return None
        payload = load_provider(provider)
        if not payload:
            return None
        from symposa2.services.credentials import payload_to_env_overlay

        overlay = payload_to_env_overlay(provider, payload)
        return overlay.get(env_name)

    def env_overlay() -> Dict[str, str]:
        with session_scope() as session:
            set_rls_context(session, str(company_id), str(user_id))
            return build_integration_env_overlay(session, company_id, user_id)

    return load_provider, load_file, load_env, env_overlay


def install_tenant_credential_loader(company_id: UUID, user_id: UUID) -> None:
    from agent.tenant_credentials import (
        TenantCredentialContext,
        register_tenant_loader,
        set_tenant_context,
    )

    load_provider, load_file, load_env, env_overlay = _loader(company_id, user_id)
    set_tenant_context(TenantCredentialContext(company_id=company_id, user_id=user_id))
    register_tenant_loader(
        load_provider=load_provider,
        load_file=load_file,
        load_env=load_env,
        env_overlay=env_overlay,
    )
