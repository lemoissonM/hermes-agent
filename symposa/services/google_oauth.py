"""Google Workspace OAuth (company web client + per-user tokens)."""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from symposa.config import get_settings
from symposa.db.models import CompanyCredential, OAuthPendingSession, UserCredential
from symposa.services.credentials import decrypt_payload, encrypt_payload, upsert_user_credential

logger = logging.getLogger(__name__)

GOOGLE_CLIENT_PROVIDER = "google_oauth_client"
GOOGLE_TOKEN_PROVIDER = "google_workspace"


def _oauth_flow_class():
    try:
        from google_auth_oauthlib.flow import Flow

        return Flow
    except ImportError as exc:
        raise RuntimeError(
            "Google OAuth dependencies are not installed. "
            'Install with: pip install -e ".[symposa]"'
        ) from exc


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
]


def _normalize_web_client_config(web: Dict[str, Any], redirect_uri: str) -> Dict[str, Any]:
    """Build a google-auth-oauthlib-compatible web client block."""
    client_id = (web.get("client_id") or "").strip()
    client_secret = (web.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        raise ValueError("Google OAuth client_id and client_secret are required")
    uris = list(web.get("redirect_uris") or [])
    if redirect_uri and redirect_uri not in uris:
        uris.insert(0, redirect_uri)
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "project_id": web.get("project_id", ""),
        "auth_uri": web.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
        "token_uri": web.get("token_uri", "https://oauth2.googleapis.com/token"),
        "auth_provider_x509_cert_url": web.get(
            "auth_provider_x509_cert_url",
            "https://www.googleapis.com/oauth2/v1/certs",
        ),
        "redirect_uris": uris or [redirect_uri],
    }


def _normalize_client_config(client_cfg: Dict[str, Any], redirect_uri: str) -> Dict[str, Any]:
    web = client_cfg.get("web") or client_cfg.get("installed")
    if not isinstance(web, dict):
        raise ValueError("Google OAuth client configuration must include a web or installed block")
    return {"web": _normalize_web_client_config(web, redirect_uri)}


def _normalize_authorized_user(payload: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(payload)
    if not out.get("type"):
        out["type"] = "authorized_user"
    if "scopes" not in out and out.get("scope"):
        out["scopes"] = out["scope"].split()
    return out


def _load_company_google_client(session: Session, company_id: UUID) -> Optional[Dict[str, Any]]:
    row = session.scalar(
        select(CompanyCredential).where(
            CompanyCredential.company_id == company_id,
            CompanyCredential.provider == GOOGLE_CLIENT_PROVIDER,
        )
    )
    if row is not None:
        return decrypt_payload(row.encrypted_payload)
    settings = get_settings()
    if settings.google_client_id and settings.google_client_secret:
        return {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uris": [settings.google_redirect_uri],
            }
        }
    return None


def company_google_client_status(
    session: Session, company_id: UUID
) -> Dict[str, Any]:
    """Admin-safe view of company Google OAuth client configuration."""
    row = session.scalar(
        select(CompanyCredential).where(
            CompanyCredential.company_id == company_id,
            CompanyCredential.provider == GOOGLE_CLIENT_PROVIDER,
        )
    )
    if row is not None:
        try:
            data = decrypt_payload(row.encrypted_payload)
            web = data.get("web") or {}
            uris = web.get("redirect_uris") or []
            return {
                "configured": True,
                "client_id": web.get("client_id"),
                "redirect_uri": uris[0] if uris else None,
                "source": "database",
            }
        except Exception:
            return {"configured": False, "client_id": None, "redirect_uri": None, "source": "database"}
    settings = get_settings()
    if settings.google_client_id and settings.google_client_secret:
        return {
            "configured": True,
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "source": "env",
        }
    return {"configured": False, "client_id": None, "redirect_uri": None, "source": "none"}


def upsert_company_google_client(
    session: Session,
    company_id: UUID,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> None:
    payload = {
        "web": _normalize_web_client_config(
            {"client_id": client_id, "client_secret": client_secret},
            redirect_uri,
        )
    }
    row = session.scalar(
        select(CompanyCredential).where(
            CompanyCredential.company_id == company_id,
            CompanyCredential.provider == GOOGLE_CLIENT_PROVIDER,
        )
    )
    enc = encrypt_payload(payload)
    if row:
        row.encrypted_payload = enc
        row.version += 1
    else:
        session.add(
            CompanyCredential(
                company_id=company_id,
                provider=GOOGLE_CLIENT_PROVIDER,
                encrypted_payload=enc,
            )
        )
    session.flush()


def google_workspace_status(
    session: Session, company_id: UUID, user_id: UUID
) -> Dict[str, Any]:
    row = session.scalar(
        select(UserCredential).where(
            UserCredential.company_id == company_id,
            UserCredential.user_id == user_id,
            UserCredential.provider == GOOGLE_TOKEN_PROVIDER,
        )
    )
    if row is None:
        return {
            "connected": False,
            "summary": "not connected — use Connect Google in settings",
        }
    try:
        data = decrypt_payload(row.encrypted_payload)
    except Exception:
        return {"connected": False, "summary": "credential unreadable"}
    email = data.get("account") or data.get("client_id") or ""
    expiry = data.get("expiry")
    return {
        "connected": True,
        "email": email,
        "expires_at": expiry,
        "summary": f"connected as {email}" if email else "connected",
    }


def start_google_connect(
    session: Session, company_id: UUID, user_id: UUID
) -> str:
    """Return Google authorize URL (PKCE)."""
    client_cfg = _load_company_google_client(session, company_id)
    if not client_cfg:
        raise ValueError("Google OAuth client not configured for this company")

    Flow = _oauth_flow_class()
    settings = get_settings()
    redirect_uri = settings.google_redirect_uri
    normalized = _normalize_client_config(client_cfg, redirect_uri)
    flow = Flow.from_client_config(
        normalized,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
        autogenerate_code_verifier=True,
    )
    state = secrets.token_urlsafe(32)
    auth_url, returned_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    oauth_state = returned_state or state
    session.execute(
        delete(OAuthPendingSession).where(
            OAuthPendingSession.company_id == company_id,
            OAuthPendingSession.user_id == user_id,
        )
    )
    session.add(
        OAuthPendingSession(
            state=oauth_state,
            company_id=company_id,
            user_id=user_id,
            code_verifier=flow.code_verifier or "",
            redirect_uri=redirect_uri,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
    )
    session.flush()
    return auth_url


def complete_google_callback(
    session: Session, state: str, code: str
) -> Tuple[UUID, UUID]:
    """Exchange code and persist user token. Returns (company_id, user_id)."""
    pending = session.scalar(
        select(OAuthPendingSession).where(OAuthPendingSession.state == state)
    )
    if pending is None or pending.expires_at < datetime.now(timezone.utc):
        raise ValueError("Invalid or expired OAuth state")
    client_cfg = _load_company_google_client(session, pending.company_id)
    if not client_cfg:
        raise ValueError("Google OAuth client not configured")

    Flow = _oauth_flow_class()
    normalized = _normalize_client_config(client_cfg, pending.redirect_uri)
    flow = Flow.from_client_config(
        normalized,
        scopes=SCOPES,
        redirect_uri=pending.redirect_uri,
        state=state,
        code_verifier=pending.code_verifier,
    )
    if pending.code_verifier:
        flow.code_verifier = pending.code_verifier
    flow.fetch_token(code=code)
    creds = flow.credentials
    token_payload = _normalize_authorized_user(
        {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes or SCOPES),
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }
    )
    upsert_user_credential(
        session,
        pending.company_id,
        pending.user_id,
        GOOGLE_TOKEN_PROVIDER,
        token_payload,
    )
    company_id, user_id = pending.company_id, pending.user_id
    session.delete(pending)
    session.flush()
    return company_id, user_id


def revoke_google_workspace(session: Session, company_id: UUID, user_id: UUID) -> bool:
    row = session.scalar(
        select(UserCredential).where(
            UserCredential.company_id == company_id,
            UserCredential.user_id == user_id,
            UserCredential.provider == GOOGLE_TOKEN_PROVIDER,
        )
    )
    if row is None:
        return False
    try:
        data = decrypt_payload(row.encrypted_payload)
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request as GoogleRequest

        creds = Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            scopes=data.get("scopes"),
        )
        creds.revoke(GoogleRequest())
    except Exception as exc:
        logger.debug("google revoke: %s", exc)
    session.delete(row)
    session.flush()
    return True


def refresh_google_token_if_needed(
    session: Session, company_id: UUID, user_id: UUID, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Refresh expired token and persist back to Postgres."""
    expiry_raw = payload.get("expiry")
    if not expiry_raw or not payload.get("refresh_token"):
        return payload
    try:
        if isinstance(expiry_raw, str):
            expiry = datetime.fromisoformat(expiry_raw.replace("Z", "+00:00"))
        else:
            expiry = expiry_raw
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
    except Exception:
        return payload
    if expiry > datetime.now(timezone.utc) + timedelta(minutes=2):
        return payload

    client_cfg = _load_company_google_client(session, company_id)
    web = (client_cfg or {}).get("web") or {}
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as GoogleRequest

    creds = Credentials(
        token=payload.get("token"),
        refresh_token=payload.get("refresh_token"),
        token_uri=payload.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=payload.get("client_id") or web.get("client_id"),
        client_secret=payload.get("client_secret") or web.get("client_secret"),
        scopes=payload.get("scopes"),
    )
    try:
        creds.refresh(GoogleRequest())
    except Exception as exc:
        logger.warning("google token refresh failed: %s", exc)
        raise
    updated = _normalize_authorized_user(
        {
            **payload,
            "token": creds.token,
            "refresh_token": creds.refresh_token or payload.get("refresh_token"),
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }
    )
    upsert_user_credential(
        session, company_id, user_id, GOOGLE_TOKEN_PROVIDER, updated
    )
    return updated
