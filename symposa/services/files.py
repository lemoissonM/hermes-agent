"""Per-user file registry, serving, and signed share links."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from symposa.config import get_settings
from symposa.db.models import UserFile
from symposa.runtime.path_guard import _allowed_roots
from symposa.services.runtime_paths import user_runtime_root
from symposa.services import storage as s3

SOURCE_WORKSPACE = "workspace"
SOURCE_S3 = "s3"


def _api_base() -> str:
    settings = get_settings()
    base = settings.link_base_url.rstrip("/")
    if base.endswith("/api"):
        return base
    return f"{base}/api"


def view_content_url(file_id: UUID, *, disposition: Optional[str] = None) -> str:
    url = f"{_api_base()}/user/files/{file_id}/content"
    if disposition == "attachment":
        return f"{url}?disposition=attachment"
    return url


def _guess_content_type(name: str, explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


def _inline_disposition(content_type: str) -> bool:
    ct = (content_type or "").lower()
    if ct == "text/html":
        return True
    if ct.startswith("image/"):
        return True
    if ct == "application/pdf":
        return True
    return False


def resolve_workspace_path(user_id: UUID, rel_path: str) -> Path:
    """Resolve a workspace-relative path and verify it stays inside allowed roots."""
    root = user_runtime_root(user_id).resolve()
    rel = rel_path.lstrip("/").replace("\\", "/")
    target = (root / rel).resolve()
    allowed = _allowed_roots(str(root))
    for allowed_root in allowed:
        try:
            target.relative_to(allowed_root)
            return target
        except ValueError:
            continue
    raise PermissionError(f"Path not allowed outside Symposa workspace: {rel_path}")


def workspace_rel_from_abs(user_id: UUID, abs_path: str | Path) -> str:
    root = user_runtime_root(user_id).resolve()
    resolved = Path(abs_path).resolve()
    return str(resolved.relative_to(root)).replace("\\", "/")


def register_workspace_file(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    abs_path: str | Path,
    *,
    content_type: Optional[str] = None,
) -> UserFile:
    """Register or refresh a workspace file row for an on-disk artifact."""
    resolved = Path(abs_path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(str(resolved))
    rel = workspace_rel_from_abs(user_id, resolved)
    resolve_workspace_path(user_id, rel)

    name = resolved.name
    ct = _guess_content_type(name, content_type)
    size = resolved.stat().st_size

    existing = session.scalar(
        select(UserFile).where(
            UserFile.company_id == company_id,
            UserFile.user_id == user_id,
            UserFile.source == SOURCE_WORKSPACE,
            UserFile.workspace_rel_path == rel,
        )
    )
    if existing is not None:
        existing.name = name
        existing.content_type = ct
        existing.size_bytes = size
        existing.storage_key = rel
        session.flush()
        return existing

    row = UserFile(
        company_id=company_id,
        user_id=user_id,
        name=name,
        source=SOURCE_WORKSPACE,
        storage_key=rel,
        workspace_rel_path=rel,
        content_type=ct,
        size_bytes=size,
    )
    session.add(row)
    session.flush()
    return row


def create_s3_file(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    name: str,
    storage_key: str,
    *,
    content_type: Optional[str] = None,
    size_bytes: Optional[int] = None,
) -> UserFile:
    row = UserFile(
        company_id=company_id,
        user_id=user_id,
        name=name,
        source=SOURCE_S3,
        storage_key=storage_key,
        workspace_rel_path=None,
        content_type=_guess_content_type(name, content_type),
        size_bytes=size_bytes,
    )
    session.add(row)
    session.flush()
    return row


def list_files(
    session: Session,
    company_id: UUID,
    user_id: UUID,
) -> List[UserFile]:
    return list(
        session.scalars(
            select(UserFile)
            .where(
                UserFile.company_id == company_id,
                UserFile.user_id == user_id,
            )
            .order_by(UserFile.created_at.desc())
        )
    )


def get_owned_file(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    file_id: UUID,
) -> Optional[UserFile]:
    return session.scalar(
        select(UserFile).where(
            UserFile.id == file_id,
            UserFile.company_id == company_id,
            UserFile.user_id == user_id,
        )
    )


def read_file_bytes(row: UserFile, user_id: UUID) -> bytes:
    if row.source == SOURCE_WORKSPACE:
        if not row.workspace_rel_path:
            raise FileNotFoundError("workspace path missing")
        path = resolve_workspace_path(user_id, row.workspace_rel_path)
        return path.read_bytes()
    data = s3.get_bytes(row.storage_key)
    if data is None:
        raise FileNotFoundError(row.storage_key)
    return data


def delete_owned_file(
    session: Session,
    company_id: UUID,
    user_id: UUID,
    file_id: UUID,
) -> bool:
    row = get_owned_file(session, company_id, user_id, file_id)
    if row is None:
        return False
    if row.source == SOURCE_WORKSPACE and row.workspace_rel_path:
        try:
            path = resolve_workspace_path(user_id, row.workspace_rel_path)
            if path.is_file():
                path.unlink()
        except (OSError, PermissionError):
            pass
    elif row.source == SOURCE_S3 and row.storage_key:
        s3.delete_object(row.storage_key)
    session.delete(row)
    session.flush()
    return True


def file_to_dict(row: UserFile, *, include_share: bool = False) -> Dict[str, Any]:
    fid = row.id
    out: Dict[str, Any] = {
        "id": str(fid),
        "name": row.name,
        "source": row.source,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "view_url": view_content_url(fid),
        "download_url": view_content_url(fid, disposition="attachment"),
    }
    if include_share:
        token, _ = mint_share_token(row)
        out["share_url"] = public_share_url(token)
    return out


def _sign_payload(payload: dict) -> str:
    settings = get_settings()
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = hmac.new(
        settings.file_sign_secret.encode(),
        raw,
        hashlib.sha256,
    ).digest()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    tag = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{body}.{tag}"


def _verify_token(token: str) -> Optional[dict]:
    settings = get_settings()
    parts = token.split(".", 1)
    if len(parts) != 2:
        return None
    body_b64, tag_b64 = parts
    try:
        pad = "=" * (-len(body_b64) % 4)
        raw = base64.urlsafe_b64decode(body_b64 + pad)
        pad2 = "=" * (-len(tag_b64) % 4)
        expected = base64.urlsafe_b64decode(tag_b64 + pad2)
    except Exception:
        return None
    sig = hmac.new(settings.file_sign_secret.encode(), raw, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(raw.decode())
    except json.JSONDecodeError:
        return None
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or time.time() > exp:
        return None
    return payload


def mint_share_token(row: UserFile, ttl_seconds: Optional[int] = None) -> Tuple[str, int]:
    settings = get_settings()
    ttl = ttl_seconds if ttl_seconds is not None else settings.file_share_ttl_seconds
    ttl = max(60, min(ttl, settings.file_share_max_ttl_seconds))
    exp = int(time.time()) + ttl
    payload = {
        "file_id": str(row.id),
        "user_id": str(row.user_id),
        "company_id": str(row.company_id),
        "exp": exp,
    }
    return _sign_payload(payload), ttl


def public_share_url(token: str) -> str:
    return f"{_api_base()}/public/files/{token}"


def resolve_share_token(session: Session, token: str) -> Optional[UserFile]:
    payload = _verify_token(token)
    if not payload:
        return None
    try:
        file_id = UUID(str(payload["file_id"]))
        user_id = UUID(str(payload["user_id"]))
        company_id = UUID(str(payload["company_id"]))
    except (ValueError, KeyError):
        return None
    return get_owned_file(session, company_id, user_id, file_id)


def content_disposition(row: UserFile, *, force_attachment: bool = False) -> str:
    inline = not force_attachment and _inline_disposition(row.content_type or "")
    disp = "inline" if inline else "attachment"
    safe_name = row.name.replace('"', "'")
    return f'{disp}; filename="{safe_name}"'


def html_csp_header() -> str:
    return "sandbox"
