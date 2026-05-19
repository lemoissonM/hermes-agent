"""Install Symposa2 tenant context for gateway messaging sessions."""

from __future__ import annotations

import logging
from typing import Optional, Tuple
from uuid import UUID

logger = logging.getLogger(__name__)


def try_install_from_session_key(session_key: Optional[str]) -> bool:
    if not session_key:
        return False
    try:
        from symposa2.services.tenant_context import resolve_tenant_from_session_key
        from symposa2.services.tenant_loader import install_tenant_credential_loader

        resolved = resolve_tenant_from_session_key(session_key)
        if resolved is None:
            return False
        company_id, user_id = resolved
        install_tenant_credential_loader(company_id, user_id)
        return True
    except Exception as exc:
        logger.debug("symposa2 session_key tenant install skipped: %s", exc)
        return False


def try_install_from_platform_user(
    platform: str,
    external_id: Optional[str],
) -> bool:
    if not external_id:
        return False
    try:
        from symposa2.services.bootstrap import bootstrap_user_home
        from symposa2.services.tenant_context import resolve_tenant_from_channel

        resolved = resolve_tenant_from_channel(platform, external_id)
        if resolved is None:
            return False
        company_id, user_id = resolved
        bootstrap_user_home(company_id, user_id, channel=platform)
        return True
    except Exception as exc:
        logger.debug("symposa2 platform tenant install skipped: %s", exc)
        return False


def clear_tenant() -> None:
    try:
        from agent.tenant_credentials import clear_tenant_context

        clear_tenant_context()
    except Exception:
        pass
