"""Encrypted tenant credential storage (Postgres source of truth)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from symposa.config import get_settings
from symposa2.db.models import S2CompanyCredential, S2UserCredential
from symposa2.services.credential_registry import INTEGRATIONS, get_integration

logger = logging.getLogger(__name__)

_fernet_cache: Optional[Fernet] = None


def _fernet() -> Optional[Fernet]:
    global _fernet_cache
    key = get_settings().credential_encryption_key
    if not key:
        return None
    if _fernet_cache is not None:
        return _fernet_cache
    try:
        _fernet_cache = Fernet(key.encode() if not key.startswith("gAAAA") else key)
    except Exception:
        import hashlib
        from base64 import urlsafe_b64encode

        derived = urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
        _fernet_cache = Fernet(derived)
    return _fernet_cache


def encrypt_payload(data: Dict[str, Any]) -> bytes:
    f = _fernet()
    raw = json.dumps(data).encode("utf-8")
    if f is None:
        return raw
    return f.encrypt(raw)


def decrypt_payload(blob: bytes) -> Dict[str, Any]:
    f = _fernet()
    if f is None:
        return json.loads(blob.decode("utf-8"))
    try:
        return json.loads(f.decrypt(blob).decode("utf-8"))
    except InvalidToken:
        return json.loads(blob.decode("utf-8"))


def upsert_user_credential(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    provider: str,
    payload: Dict[str, Any],
    *,
    credential_type: str = "oauth2",
) -> S2UserCredential:
    row = session.scalar(
        select(S2UserCredential).where(
            S2UserCredential.company_id == company_id,
            S2UserCredential.user_id == user_id,
            S2UserCredential.provider == provider,
        )
    )
    enc = encrypt_payload(payload)
    if row:
        row.encrypted_payload = enc
        row.credential_type = credential_type
        row.version += 1
        session.flush()
        return row
    row = S2UserCredential(
        company_id=company_id,
        user_id=user_id,
        provider=provider,
        credential_type=credential_type,
        encrypted_payload=enc,
    )
    session.add(row)
    session.flush()
    return row


def upsert_company_credential(
    session: Session,
    company_id: UUID,
    provider: str,
    payload: Dict[str, Any],
    *,
    credential_type: str = "oauth2",
) -> S2CompanyCredential:
    row = session.scalar(
        select(S2CompanyCredential).where(
            S2CompanyCredential.company_id == company_id,
            S2CompanyCredential.provider == provider,
        )
    )
    enc = encrypt_payload(payload)
    if row:
        row.encrypted_payload = enc
        row.credential_type = credential_type
        row.version += 1
        session.flush()
        return row
    row = S2CompanyCredential(
        company_id=company_id,
        provider=provider,
        credential_type=credential_type,
        encrypted_payload=enc,
    )
    session.add(row)
    session.flush()
    return row


def delete_user_credential(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    provider: str,
) -> bool:
    row = session.scalar(
        select(S2UserCredential).where(
            S2UserCredential.company_id == company_id,
            S2UserCredential.user_id == user_id,
            S2UserCredential.provider == provider,
        )
    )
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


def resolve_provider_payload(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    provider: str,
) -> Optional[Dict[str, Any]]:
    """User row wins over company row. Falls back to legacy v1 credential tables."""
    user_row = session.scalar(
        select(S2UserCredential).where(
            S2UserCredential.company_id == company_id,
            S2UserCredential.user_id == user_id,
            S2UserCredential.provider == provider,
        )
    )
    if user_row:
        try:
            return decrypt_payload(user_row.encrypted_payload)
        except Exception as exc:
            logger.warning("decrypt s2 user credential %s failed: %s", provider, exc)
            return None
    company_row = session.scalar(
        select(S2CompanyCredential).where(
            S2CompanyCredential.company_id == company_id,
            S2CompanyCredential.provider == provider,
        )
    )
    if company_row:
        try:
            return decrypt_payload(company_row.encrypted_payload)
        except Exception as exc:
            logger.warning("decrypt s2 company credential %s failed: %s", provider, exc)
            return None
    return _resolve_v1_provider_payload(session, company_id, user_id, provider)


def _resolve_v1_provider_payload(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    provider: str,
) -> Optional[Dict[str, Any]]:
    try:
        from symposa.db.models import CompanyCredential, UserCredential
        from symposa.services.credentials import decrypt_payload as v1_decrypt

        user_row = session.scalar(
            select(UserCredential).where(
                UserCredential.company_id == company_id,
                UserCredential.user_id == user_id,
                UserCredential.provider == provider,
            )
        )
        if user_row:
            return v1_decrypt(user_row.encrypted_payload)
        company_row = session.scalar(
            select(CompanyCredential).where(
                CompanyCredential.company_id == company_id,
                CompanyCredential.provider == provider,
            )
        )
        if company_row:
            return v1_decrypt(company_row.encrypted_payload)
    except Exception as exc:
        logger.debug("v1 credential fallback skipped: %s", exc)
    return None


def list_credential_status(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    *,
    is_admin: bool = False,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for integration in INTEGRATIONS:
        if integration.scope == "company" and not is_admin:
            connected = bool(
                session.scalar(
                    select(S2CompanyCredential).where(
                        S2CompanyCredential.company_id == company_id,
                        S2CompanyCredential.provider == integration.provider_key,
                    )
                )
            )
        else:
            connected = resolve_provider_payload(
                session, company_id, user_id, integration.provider_key
            ) is not None
        out.append(
            {
                "provider": integration.provider_key,
                "label": integration.label,
                "description": integration.description,
                "scope": integration.scope,
                "connect_type": integration.connect_type,
                "connected": connected,
            }
        )
    return out


def payload_to_env_overlay(provider: str, payload: Dict[str, Any]) -> Dict[str, str]:
    """Map stored payload to env vars for a provider."""
    integration = get_integration(provider)
    if not integration:
        return {}
    overlay: Dict[str, str] = {}
    if provider == "github":
        token = payload.get("token") or payload.get("api_key") or payload.get("access_token")
        if token:
            overlay["GITHUB_TOKEN"] = str(token)
            overlay["GH_TOKEN"] = str(token)
        return overlay
    if provider == "notion":
        key = payload.get("api_key") or payload.get("token")
        if key:
            overlay["NOTION_API_KEY"] = str(key)
        return overlay
    if provider == "spotify":
        cid = payload.get("client_id")
        secret = payload.get("client_secret")
        if cid:
            overlay["SPOTIFY_CLIENT_ID"] = str(cid)
        if secret:
            overlay["SPOTIFY_CLIENT_SECRET"] = str(secret)
        return overlay
    for target in integration.targets:
        if target.kind == "env" and target.path in payload:
            overlay[target.path] = str(payload[target.path])
    return overlay


def build_integration_env_overlay(
    session: Session,
    company_id: UUID,
    user_id: UUID,
) -> Dict[str, str]:
    """All integration env vars for active tenant."""
    overlay: Dict[str, str] = {}
    for integration in INTEGRATIONS:
        payload = resolve_provider_payload(
            session, company_id, user_id, integration.provider_key
        )
        if payload:
            overlay.update(payload_to_env_overlay(integration.provider_key, payload))
    return overlay
