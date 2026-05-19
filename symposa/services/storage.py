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


def _s3_client():
    settings = get_settings()
    if not settings.s3_endpoint:
        return None
    import boto3
    from botocore.client import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
    )


def put_bytes(key: str, data: bytes, content_type: Optional[str] = None) -> bool:
    settings = get_settings()
    if not settings.s3_endpoint:
        logger.warning("S3 not configured; file not stored: %s", key)
        return False
    try:
        client = _s3_client()
        extra = {}
        if content_type:
            extra["ContentType"] = content_type
        client.put_object(Bucket=settings.s3_bucket, Key=key, Body=data, **extra)
        return True
    except Exception as exc:
        logger.warning("S3 put failed: %s", exc)
        return False


def get_bytes(key: str) -> Optional[bytes]:
    settings = get_settings()
    if not settings.s3_endpoint:
        return None
    try:
        client = _s3_client()
        resp = client.get_object(Bucket=settings.s3_bucket, Key=key)
        return resp["Body"].read()
    except Exception as exc:
        logger.warning("S3 get failed for %s: %s", key, exc)
        return None


def delete_object(key: str) -> bool:
    settings = get_settings()
    if not settings.s3_endpoint or not key:
        return False
    try:
        client = _s3_client()
        client.delete_object(Bucket=settings.s3_bucket, Key=key)
        return True
    except Exception as exc:
        logger.warning("S3 delete failed for %s: %s", key, exc)
        return False


def presigned_get_url(
    key: str,
    ttl_seconds: int,
    *,
    content_type: Optional[str] = None,
    inline: bool = False,
    filename: Optional[str] = None,
) -> Optional[str]:
    settings = get_settings()
    if not settings.s3_endpoint or not key:
        return None
    try:
        client = _s3_client()
        params = {"Bucket": settings.s3_bucket, "Key": key}
        if content_type:
            params["ResponseContentType"] = content_type
        disp = "inline" if inline else "attachment"
        if filename:
            params["ResponseContentDisposition"] = f'{disp}; filename="{filename}"'
        else:
            params["ResponseContentDisposition"] = disp
        return client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=max(1, min(ttl_seconds, settings.file_share_max_ttl_seconds)),
        )
    except Exception as exc:
        logger.warning("S3 presign failed for %s: %s", key, exc)
        return None
