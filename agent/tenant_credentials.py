"""Request-scoped tenant credential resolution for Symposa2 multi-tenant Hermes."""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

LoadProviderFn = Callable[[str], Optional[Dict[str, Any]]]
LoadFileFn = Callable[[str], Optional[Dict[str, Any]]]
LoadEnvFn = Callable[[str], Optional[str]]
EnvOverlayFn = Callable[[], Dict[str, str]]


@dataclass(frozen=True)
class TenantCredentialContext:
    company_id: UUID
    user_id: UUID


_TENANT_CTX: ContextVar[Optional[TenantCredentialContext]] = ContextVar(
    "tenant_cred_ctx", default=None
)
_LOAD_PROVIDER: ContextVar[Optional[LoadProviderFn]] = ContextVar("tenant_load_provider", default=None)
_LOAD_FILE: ContextVar[Optional[LoadFileFn]] = ContextVar("tenant_load_file", default=None)
_LOAD_ENV: ContextVar[Optional[LoadEnvFn]] = ContextVar("tenant_load_env", default=None)
_ENV_OVERLAY: ContextVar[Optional[EnvOverlayFn]] = ContextVar("tenant_env_overlay", default=None)
_EPHEMERAL_CACHE: ContextVar[Dict[str, Path]] = ContextVar("tenant_ephemeral_files", default={})


def set_tenant_context(ctx: TenantCredentialContext) -> None:
    _TENANT_CTX.set(ctx)
    _EPHEMERAL_CACHE.set({})


def get_tenant_context() -> Optional[TenantCredentialContext]:
    return _TENANT_CTX.get()


def register_tenant_loader(
    *,
    load_provider: LoadProviderFn,
    load_file: LoadFileFn,
    load_env: LoadEnvFn,
    env_overlay: EnvOverlayFn,
) -> None:
    _LOAD_PROVIDER.set(load_provider)
    _LOAD_FILE.set(load_file)
    _LOAD_ENV.set(load_env)
    _ENV_OVERLAY.set(env_overlay)


def clear_tenant_context() -> None:
    _TENANT_CTX.set(None)
    _LOAD_PROVIDER.set(None)
    _LOAD_FILE.set(None)
    _LOAD_ENV.set(None)
    _ENV_OVERLAY.set(None)
    _EPHEMERAL_CACHE.set({})


def resolve_provider(provider_key: str) -> Optional[Dict[str, Any]]:
    fn = _LOAD_PROVIDER.get()
    if fn is None:
        return None
    try:
        return fn(provider_key)
    except Exception as exc:
        logger.debug("resolve_provider %s failed: %s", provider_key, exc)
        return None


def resolve_credential_file(relative_path: str) -> Optional[Dict[str, Any]]:
    fn = _LOAD_FILE.get()
    if fn is None:
        return None
    try:
        return fn(relative_path)
    except Exception as exc:
        logger.debug("resolve_credential_file %s failed: %s", relative_path, exc)
        return None


def resolve_integration_env(env_name: str) -> Optional[str]:
    fn = _LOAD_ENV.get()
    if fn is None:
        return None
    try:
        return fn(env_name)
    except Exception as exc:
        logger.debug("resolve_integration_env %s failed: %s", env_name, exc)
        return None


def get_integration_env_overlay() -> Dict[str, str]:
    fn = _ENV_OVERLAY.get()
    if fn is None:
        return {}
    try:
        return dict(fn())
    except Exception as exc:
        logger.debug("env overlay failed: %s", exc)
        return {}


def _hermes_home() -> Path:
    from hermes_constants import get_hermes_home

    return get_hermes_home()


def ensure_credential_file(relative_path: str) -> Optional[Path]:
    """Write ephemeral credential file from DB when tenant context is active."""
    if get_tenant_context() is None:
        return None
    cache = _EPHEMERAL_CACHE.get()
    if relative_path in cache and cache[relative_path].is_file():
        return cache[relative_path]

    payload = resolve_credential_file(relative_path)
    if not payload:
        return None

    home = _hermes_home()
    target = home / ".runtime" / "credentials" / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Skills expect canonical path under HERMES_HOME root for google_token.json
    canonical = home / relative_path
    if not canonical.is_file():
        try:
            canonical.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("canonical credential write failed: %s", exc)

    cache = dict(cache)
    cache[relative_path] = target
    _EPHEMERAL_CACHE.set(cache)
    return canonical if canonical.is_file() else target


@contextmanager
def integration_env_overlay() -> Iterator[None]:
    """Temporarily overlay tenant integration env vars for in-process tool calls."""
    overlay = get_integration_env_overlay()
    if not overlay:
        yield
        return
    saved = {k: os.environ.get(k) for k in overlay}
    try:
        os.environ.update(overlay)
        yield
    finally:
        for key, old in saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
