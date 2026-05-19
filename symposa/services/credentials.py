"""Encrypted credential storage and materialization."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from symposa.config import get_settings
from symposa.db.models import UserCredential

logger = logging.getLogger(__name__)

_PROVIDER_FILES = {
    "google_workspace": "google_token.json",
}
_COMPANY_PROVIDER_FILES = {
    "google_oauth_client": "google_client_secret.json",
}


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
) -> UserCredential:
    row = session.scalar(
        select(UserCredential).where(
            UserCredential.company_id == company_id,
            UserCredential.user_id == user_id,
            UserCredential.provider == provider,
        )
    )
    enc = encrypt_payload(payload)
    if row:
        row.encrypted_payload = enc
        row.version += 1
        session.flush()
        return row
    row = UserCredential(
        company_id=company_id,
        user_id=user_id,
        provider=provider,
        encrypted_payload=enc,
    )
    session.add(row)
    session.flush()
    return row


def _write_credential_file(hermes_home: Path, rel: str, data: Dict[str, Any]) -> None:
    path = hermes_home / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        from tools.credential_files import register_credential_file

        register_credential_file(rel)
    except Exception as exc:
        logger.debug("register_credential_file: %s", exc)


def materialize_user_credentials(
    company_id: UUID,
    user_id: UUID,
    hermes_home: Path,
) -> None:
    """Write decrypted credential files into HERMES_HOME for Hermes tools."""
    from symposa.db.models import CompanyCredential
    from symposa.db.session import session_scope
    from symposa.services.google_oauth import (
        GOOGLE_CLIENT_PROVIDER,
        GOOGLE_TOKEN_PROVIDER,
        refresh_google_token_if_needed,
    )

    with session_scope() as session:
        company_rows = list(
            session.scalars(
                select(CompanyCredential).where(
                    CompanyCredential.company_id == company_id,
                )
            )
        )
        for row in company_rows:
            rel = _COMPANY_PROVIDER_FILES.get(row.provider)
            if not rel:
                continue
            try:
                data = decrypt_payload(row.encrypted_payload)
                _write_credential_file(hermes_home, rel, data)
            except Exception as exc:
                logger.warning("materialize company %s failed: %s", row.provider, exc)

        rows = list(
            session.scalars(
                select(UserCredential).where(
                    UserCredential.company_id == company_id,
                    UserCredential.user_id == user_id,
                )
            )
        )
        for row in rows:
            rel = _PROVIDER_FILES.get(row.provider)
            if not rel:
                continue
            try:
                data = decrypt_payload(row.encrypted_payload)
                if row.provider == GOOGLE_TOKEN_PROVIDER:
                    try:
                        data = refresh_google_token_if_needed(
                            session, company_id, user_id, data
                        )
                    except Exception as exc:
                        logger.warning("google refresh failed: %s", exc)
                _write_credential_file(hermes_home, rel, data)
            except Exception as exc:
                logger.warning("materialize %s failed: %s", row.provider, exc)

        # Env fallback for company Google client when not in DB
        if not any(r.provider == GOOGLE_CLIENT_PROVIDER for r in company_rows):
            from symposa.services.google_oauth import _load_company_google_client

            client_cfg = _load_company_google_client(session, company_id)
            if client_cfg:
                rel = _COMPANY_PROVIDER_FILES[GOOGLE_CLIENT_PROVIDER]
                _write_credential_file(hermes_home, rel, client_cfg)
