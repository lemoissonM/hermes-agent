"""Pydantic schemas for Symposa2 API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProfileOut(BaseModel):
    display_name: str
    soul_md: Optional[str] = None
    updated_at: Optional[datetime] = None


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    soul_md: Optional[str] = None


class SkillOut(BaseModel):
    skill_name: str
    description: Optional[str] = None
    is_custom: bool = False
    has_override: bool = False
    updated_at: Optional[datetime] = None


class SkillBodyOut(BaseModel):
    skill_name: str
    body_md: str
    description: Optional[str] = None
    is_custom: bool = False
    source: str = "database"


class SkillUpsert(BaseModel):
    body_md: str
    description: Optional[str] = None


class SkillCreate(BaseModel):
    skill_name: str = Field(min_length=1, max_length=255)
    body_md: str
    description: Optional[str] = None


class CompanySkillOut(BaseModel):
    skill_name: str
    description: Optional[str] = None
    enabled: bool = True
    is_custom: bool = False
    has_body: bool = False
    updated_at: Optional[datetime] = None


class CompanySkillUpsert(BaseModel):
    skill_name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    body_md: Optional[str] = None
    enabled: bool = True
    is_custom: bool = False


class IntegrationStatusOut(BaseModel):
    provider: str
    label: str
    description: str
    scope: str
    connect_type: str
    connected: bool


class IntegrationApiKeyPut(BaseModel):
    api_key: str = Field(min_length=1)


class WhatsAppLinkRequest(BaseModel):
    external_id: str
