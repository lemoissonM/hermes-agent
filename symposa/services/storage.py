"""S3-compatible object storage for company and user files."""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from symposa.config import get_settings

logger = logging.getLogger(__name__)


def storage_key_for_user(company_id: UUID, user_id: UUID, filename: str) -> str:
    return f"{company_id}/users/{user_id}/{filename}"


def storage_key_for_company(company_id: UUID, filename: str) -> str:
    return f"{company_id}/shared/{filename}"


def put_bytes(key: str, data: bytes, content_type: Optional[str] = None) -> bool:
    settings = get_settings()
    if not settings.s3_endpoint:
        logger.warning("S3 not configured; file not stored: %s", key)
        return False
    try:
        import boto3
        from botocore.client import Config

        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=Config(signature_version="s3v4"),
        )
        extra = {}
        if content_type:
            extra["ContentType"] = content_type
        client.put_object(Bucket=settings.s3_bucket, Key=key, Body=data, **extra)
        return True
    except Exception as exc:
        logger.warning("S3 put failed: %s", exc)
        return False
