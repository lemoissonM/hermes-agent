"""Integration credential registry — tenant DB only, not provider/inference keys."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional


@dataclass(frozen=True)
class CredentialTarget:
    kind: Literal["file", "env"]
    path: str  # relative file path or env var name


@dataclass(frozen=True)
class IntegrationDef:
    provider_key: str
    label: str
    description: str
    scope: Literal["user", "company"]
    targets: tuple[CredentialTarget, ...]
    connect_type: Literal["oauth", "api_key"] = "api_key"
    oauth_url: Optional[str] = None


INTEGRATIONS: tuple[IntegrationDef, ...] = (
    IntegrationDef(
        provider_key="google_workspace",
        label="Google Workspace",
        description="Gmail, Calendar, Drive, Sheets, and Docs",
        scope="user",
        targets=(CredentialTarget("file", "google_token.json"),),
        connect_type="oauth",
    ),
    IntegrationDef(
        provider_key="google_oauth_client",
        label="Google OAuth App",
        description="Company OAuth client (admin only)",
        scope="company",
        targets=(CredentialTarget("file", "google_client_secret.json"),),
        connect_type="oauth",
    ),
    IntegrationDef(
        provider_key="github",
        label="GitHub",
        description="Repositories, issues, and pull requests",
        scope="user",
        targets=(CredentialTarget("env", "GITHUB_TOKEN"), CredentialTarget("env", "GH_TOKEN")),
        connect_type="api_key",
    ),
    IntegrationDef(
        provider_key="notion",
        label="Notion",
        description="Pages and databases",
        scope="user",
        targets=(CredentialTarget("env", "NOTION_API_KEY"),),
        connect_type="api_key",
    ),
    IntegrationDef(
        provider_key="spotify",
        label="Spotify",
        description="Music and playlists",
        scope="user",
        targets=(CredentialTarget("env", "SPOTIFY_CLIENT_ID"), CredentialTarget("env", "SPOTIFY_CLIENT_SECRET")),
        connect_type="api_key",
    ),
)

_PROVIDER_BY_KEY: Dict[str, IntegrationDef] = {i.provider_key: i for i in INTEGRATIONS}
_FILE_TO_PROVIDER: Dict[str, str] = {}
_ENV_TO_PROVIDER: Dict[str, str] = {}
for _def in INTEGRATIONS:
    for _t in _def.targets:
        if _t.kind == "file":
            _FILE_TO_PROVIDER[_t.path] = _def.provider_key
        else:
            _ENV_TO_PROVIDER[_t.path] = _def.provider_key


def get_integration(provider_key: str) -> Optional[IntegrationDef]:
    return _PROVIDER_BY_KEY.get(provider_key)


def list_integrations(*, include_company: bool = True) -> List[IntegrationDef]:
    if include_company:
        return list(INTEGRATIONS)
    return [i for i in INTEGRATIONS if i.scope == "user"]


def provider_for_file(relative_path: str) -> Optional[str]:
    return _FILE_TO_PROVIDER.get(relative_path)


def provider_for_env(env_name: str) -> Optional[str]:
    return _ENV_TO_PROVIDER.get(env_name)


def is_tenant_env(env_name: str) -> bool:
    return env_name in _ENV_TO_PROVIDER
