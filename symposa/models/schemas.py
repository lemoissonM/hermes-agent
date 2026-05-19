"""Pydantic API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    company_name: str
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: UUID
    company_id: UUID
    email: str
    role: str


class ConversationCreate(BaseModel):
    title: str = "New conversation"


class ConversationOut(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None


class ConversationPatch(BaseModel):
    title: Optional[str] = None
    archived: Optional[bool] = None


class EventOut(BaseModel):
    id: UUID
    channel: str
    direction: str
    role: str
    content_text: Optional[str] = None
    content_json: Optional[Dict[str, Any]] = None
    created_at: datetime


class ChatRequest(BaseModel):
    message: str
    hermes_session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    hermes_session_id: Optional[str] = None


class ClarifyRespondRequest(BaseModel):
    clarify_id: str
    response: str


class RunApprovalRequest(BaseModel):
    run_id: str
    choice: str = Field(description="once | session | always | deny")


class WhatsAppLinkRequest(BaseModel):
    external_id: str


class SkillPatchRequest(BaseModel):
    body_md: str
    description: Optional[str] = None


class CredentialPutRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)


class SkillCatalogItem(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = None


class SkillsCatalogOut(BaseModel):
    skills: List[Dict[str, Any]]
    categories: List[str]
    count: int


class ToolCatalogItem(BaseModel):
    name: str
    description: str = ""
    toolset: Optional[str] = None


class ToolsCatalogOut(BaseModel):
    platform: str
    toolsets: List[str]
    tools: List[ToolCatalogItem]
    count: int


class AgentCreate(BaseModel):
    name: str
    soul_text: Optional[str] = None
    toolsets: Optional[List[str]] = None
    model: Optional[str] = None
    preloaded_skills: Optional[List[str]] = None


class AgentOut(BaseModel):
    id: UUID
    name: str
    soul_text: Optional[str] = None
    toolsets: Optional[List[str]] = None
    model: Optional[str] = None
    preloaded_skills: Optional[List[str]] = None


class GoogleCompanyIntegrationRequest(BaseModel):
    """Register the company's Google Cloud OAuth 2.0 Web application credentials."""

    client_id: str = Field(
        ...,
        description="OAuth 2.0 Client ID (Web application) from Google Cloud Console.",
        examples=["123456789.apps.googleusercontent.com"],
    )
    client_secret: str = Field(
        ...,
        description="OAuth 2.0 Client secret for the Web application client.",
        examples=["GOCSPX-example-secret"],
    )
    redirect_uri: Optional[str] = Field(
        default=None,
        description=(
            "Authorized redirect URI registered in Google Cloud Console. "
            "Must match Symposa's callback URL (default: SYMPOSA_GOOGLE_REDIRECT_URI)."
        ),
        examples=["http://127.0.0.1:8090/oauth/google/callback"],
    )


class GoogleCompanyIntegrationResponse(BaseModel):
    ok: bool = True
    client_id: str
    redirect_uri: str
    configured: bool = True


class GoogleCompanyIntegrationStatus(BaseModel):
    """Whether the company has a Google OAuth web client configured (admin view)."""

    configured: bool
    client_id: Optional[str] = None
    redirect_uri: Optional[str] = None
    source: str = Field(
        description="'database' when stored in company_credentials; 'env' for SYMPOSA_GOOGLE_* fallback.",
    )


class GoogleWorkspaceUserStatus(BaseModel):
    """Per-user Google Workspace connection status."""

    connected: bool
    summary: str
    email: Optional[str] = None
    expires_at: Optional[str] = None


class GoogleConnectUrlResponse(BaseModel):
    """URL for the user to open in a browser to connect Google Workspace."""

    authorize_url: str = Field(
        description="Open this URL in a browser, sign in with Google, and approve access.",
    )
    instructions: str = Field(
        default=(
            "Open authorize_url in your browser. After consent, you will be redirected "
            "to Symposa and your account will be linked."
        ),
    )
