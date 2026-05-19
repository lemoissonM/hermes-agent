"""Symposa configuration from environment."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _load_dotenv_symposa() -> None:
    """Load repo `.env.symposa` when present (idempotent)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    repo_root = Path(__file__).resolve().parents[1]
    env_file = repo_root / ".env.symposa"
    if env_file.is_file():
        load_dotenv(env_file, override=False)


@lru_cache(maxsize=1)
def get_settings() -> "SymposaSettings":
    _load_dotenv_symposa()
    return SymposaSettings()


class SymposaSettings:
    """Runtime settings (env-backed)."""

    def __init__(self) -> None:
        _load_dotenv_symposa()
        self.database_url = os.getenv(
            "SYMPOSA_DATABASE_URL",
            "postgresql+psycopg://symposa:symposa@localhost:5432/symposa",
        )
        self.jwt_secret = os.getenv("SYMPOSA_JWT_SECRET", "change-me-in-production")
        self.jwt_algorithm = os.getenv("SYMPOSA_JWT_ALGORITHM", "HS256")
        self.jwt_access_minutes = int(os.getenv("SYMPOSA_JWT_ACCESS_MINUTES", "60"))
        self.jwt_refresh_days = int(os.getenv("SYMPOSA_JWT_REFRESH_DAYS", "7"))
        self.runtime_root = os.getenv("SYMPOSA_RUNTIME_ROOT", "/var/symposa/runtime")
        self.runtime_wsl_root = os.getenv("SYMPOSA_RUNTIME_WSL_ROOT", "")
        self.hermes_api_url = os.getenv(
            "SYMPOSA_HERMES_API_URL", "http://127.0.0.1:8787/v1"
        )
        self.hermes_api_key = os.getenv("SYMPOSA_HERMES_API_KEY", "")
        self.hermes_base_url = os.getenv("SYMPOSA_HERMES_BASE_URL", "").strip()
        self.hermes_provider = os.getenv("SYMPOSA_HERMES_PROVIDER", "custom").strip()
        # LLM endpoint key (RunPod/Ollama), not the api_server Bearer token.
        self.llm_api_key = os.getenv("SYMPOSA_LLM_API_KEY", "key").strip()
        self.credential_encryption_key = os.getenv("SYMPOSA_CREDENTIAL_ENCRYPTION_KEY", "")
        self.link_base_url = os.getenv("SYMPOSA_LINK_BASE_URL", "http://localhost:3000")
        self.s3_endpoint = os.getenv("SYMPOSA_S3_ENDPOINT", "")
        self.s3_bucket = os.getenv("SYMPOSA_S3_BUCKET", "symposa")
        self.s3_access_key = os.getenv("SYMPOSA_S3_ACCESS_KEY", "")
        self.s3_secret_key = os.getenv("SYMPOSA_S3_SECRET_KEY", "")
        self.google_client_id = os.getenv("SYMPOSA_GOOGLE_CLIENT_ID", "")
        self.google_client_secret = os.getenv("SYMPOSA_GOOGLE_CLIENT_SECRET", "")
        self.google_redirect_uri = os.getenv(
            "SYMPOSA_GOOGLE_REDIRECT_URI",
            "http://127.0.0.1:8090/oauth/google/callback",
        )
        self.google_success_url = os.getenv(
            "SYMPOSA_GOOGLE_SUCCESS_URL",
            "http://localhost:3000/settings/integrations?google=connected",
        )
        raw_cors = os.getenv("SYMPOSA_CORS_ORIGINS", "").strip()
        if raw_cors:
            self.cors_origins = [o.strip() for o in raw_cors.split(",") if o.strip()]
        else:
            self.cors_origins = [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ]
