"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, AsyncIterator, List, Optional
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from symposa2.services.chat import (
    chat_via_hermes,
    chat_via_hermes_stream,
    resolve_clarify_response,
    resolve_run_approval,
)
from symposa.config import get_settings
from symposa.api.deps import AuthContext, get_auth, get_db_user
from symposa.auth.jwt import create_access_token, create_refresh_token, decode_token
from symposa.auth.passwords import hash_password, verify_password
from symposa.db.models import Company, CompanyAgent, User, UserAgent
from symposa.db.session import get_session_factory, session_scope, set_rls_context
from symposa.models.schemas import (
    AgentCreate,
    AgentOut,
    ChatRequest,
    ChatResponse,
    ClarifyRespondRequest,
    RunApprovalRequest,
    FileShareOut,
    FileShareRequest,
    UserFileListOut,
    UserFileOut,
    ConversationCreate,
    ConversationOut,
    ConversationPatch,
    CredentialPutRequest,
    EventOut,
    GoogleCompanyIntegrationRequest,
    GoogleCompanyIntegrationResponse,
    GoogleCompanyIntegrationStatus,
    GoogleConnectUrlResponse,
    GoogleWorkspaceUserStatus,
    LoginRequest,
    RegisterRequest,
    SkillPatchRequest,
    SkillsCatalogOut,
    TenantOut,
    TenantUpdate,
    TenantUserCreate,
    TenantUserOut,
    TokenResponse,
    ToolCatalogItem,
    ToolsCatalogOut,
    UserOut,
    WhatsAppLinkRequest,
)
from symposa.services.catalog import hermes_health, list_skills_catalog, list_tools_catalog
from symposa.services.conversations import (
    create_conversation,
    get_conversation,
    list_conversations,
    set_active_conversation,
)
from symposa.services.events import append_event, list_events
from symposa.services.identity import link_channel_identity
from symposa.services.skills import upsert_user_skill_override
from symposa.db.models import Conversation, ConversationEvent


def _conversation_out(conv: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        archived_at=conv.archived_at,
    )


def _event_out(row: ConversationEvent) -> EventOut:
    return EventOut(
        id=row.id,
        channel=row.channel,
        direction=row.direction,
        role=row.role,
        content_text=row.content_text,
        content_json=row.content_json,
        created_at=row.created_at,
    )


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "tenant"


def _tenant_out(company: Company) -> TenantOut:
    return TenantOut(
        id=company.id,
        slug=company.slug or str(company.id),
        name=company.name,
        environment=company.environment,
        region=company.region,
        timezone=company.timezone,
        currency=company.currency,
        language=company.language,
        status=company.status,
        overview_md=company.overview_md,
        governance_md=company.governance_md,
        created_at=company.created_at,
    )


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Symposa API",
        version="2.0.0",
        description=(
            "Multi-tenant Hermes workplace API (Symposa2). Use **Authorize** with a JWT from "
            "`POST /auth/login` or `POST /auth/register`."
        ),
        openapi_tags=[
            {"name": "auth", "description": "Register and login"},
            {"name": "company-integrations", "description": "Admin: company-wide OAuth apps (Google)"},
            {"name": "integrations", "description": "Per-user integrations (Google Workspace)"},
            {"name": "catalog", "description": "Hermes tools and skills catalog"},
            {"name": "conversations", "description": "Chats and events"},
        ],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _startup_sanitize_runtime_auth() -> None:
        try:
            from symposa.services.inference_config import sanitize_all_runtime_auth_files

            count = sanitize_all_runtime_auth_files()
            if count:
                import logging

                logging.getLogger(__name__).info(
                    "Removed credential_pool from %s Symposa runtime auth.json file(s)",
                    count,
                )
        except Exception:
            pass

    @app.post("/auth/register", response_model=TokenResponse)
    def register(body: RegisterRequest) -> TokenResponse:
        with session_scope() as session:
            company = Company(name=body.company_name, slug=f"{_slugify(body.company_name)}-{uuid4().hex[:6]}")
            session.add(company)
            session.flush()
            user = User(
                company_id=company.id,
                email=body.email.lower(),
                password_hash=hash_password(body.password),
                role="admin",
            )
            session.add(user)
            session.flush()
            link_channel_identity(
                session, company.id, user.id, "web", str(user.id)
            )
            from symposa.services.company_defaults import ensure_company_agent

            ensure_company_agent(session, company.id)
            access = create_access_token(user.id, company.id, user.role, user.email)
            refresh = create_refresh_token(user.id, company.id)
        return TokenResponse(access_token=access, refresh_token=refresh)

    @app.post("/auth/login", response_model=TokenResponse)
    def login(body: LoginRequest) -> TokenResponse:
        with session_scope() as session:
            user = session.query(User).filter(User.email == body.email.lower()).first()
            if user is None or not verify_password(body.password, user.password_hash):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
            access = create_access_token(user.id, user.company_id, user.role, user.email)
            refresh = create_refresh_token(user.id, user.company_id)
        return TokenResponse(access_token=access, refresh_token=refresh)

    @app.post("/auth/refresh", response_model=TokenResponse)
    def refresh(token: str) -> TokenResponse:
        try:
            payload = decode_token(token)
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid refresh token") from exc
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        uid = UUID(payload["sub"])
        cid = UUID(payload["company_id"])
        with session_scope() as session:
            user = session.get(User, uid)
            if user is None:
                raise HTTPException(status_code=401, detail="User not found")
            access = create_access_token(user.id, cid, user.role, user.email)
            new_refresh = create_refresh_token(user.id, cid)
        return TokenResponse(access_token=access, refresh_token=new_refresh)

    @app.get("/me", response_model=UserOut)
    def me(auth: Annotated[AuthContext, Depends(get_auth)]) -> UserOut:
        with session_scope() as session:
            company = session.get(Company, auth.company_id)
        return UserOut(
            id=auth.user_id,
            company_id=auth.company_id,
            email=auth.email,
            role=auth.role,
            tenant_slug=company.slug if company else None,
            company_name=company.name if company else None,
        )

    @app.get("/company/tenant", response_model=TenantOut)
    def tenant_get(auth: Annotated[AuthContext, Depends(get_auth)]) -> TenantOut:
        with session_scope() as session:
            company = session.get(Company, auth.company_id)
            if company is None:
                raise HTTPException(status_code=404, detail="Tenant not found")
            return _tenant_out(company)

    @app.patch("/company/tenant", response_model=TenantOut)
    def tenant_update(
        body: TenantUpdate,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> TenantOut:
        if auth.role != "admin":
            raise HTTPException(status_code=403, detail="Admin only")
        with session_scope() as session:
            company = session.get(Company, auth.company_id)
            if company is None:
                raise HTTPException(status_code=404, detail="Tenant not found")
            for field in (
                "name",
                "environment",
                "region",
                "timezone",
                "currency",
                "language",
                "status",
                "overview_md",
                "governance_md",
            ):
                value = getattr(body, field)
                if value is not None:
                    setattr(company, field, value)
            if body.slug is not None:
                company.slug = _slugify(body.slug)
            session.flush()
            return _tenant_out(company)

    @app.get("/company/users", response_model=List[TenantUserOut])
    def tenant_users_list(auth: Annotated[AuthContext, Depends(get_auth)]) -> List[TenantUserOut]:
        if auth.role != "admin":
            raise HTTPException(status_code=403, detail="Admin only")
        with session_scope() as session:
            users = list(session.query(User).filter(User.company_id == auth.company_id).order_by(User.created_at.asc()))
            profile_by_user = {}
            try:
                from symposa2.db.models import S2UserProfile

                rows = session.query(S2UserProfile).filter(S2UserProfile.company_id == auth.company_id)
                profile_by_user = {row.user_id: row.display_name for row in rows}
            except Exception:
                profile_by_user = {}
            return [
                TenantUserOut(
                    id=user.id,
                    email=user.email,
                    role=user.role,
                    display_name=profile_by_user.get(user.id),
                    created_at=user.created_at,
                )
                for user in users
            ]

    @app.post("/company/users", response_model=TenantUserOut, status_code=201)
    def tenant_users_create(
        body: TenantUserCreate,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> TenantUserOut:
        if auth.role != "admin":
            raise HTTPException(status_code=403, detail="Admin only")
        role = "admin" if body.role in ("admin", "tenant_admin") else "member"
        with session_scope() as session:
            existing = session.query(User).filter(
                User.company_id == auth.company_id,
                User.email == body.email.lower(),
            ).first()
            if existing is not None:
                raise HTTPException(status_code=409, detail="User already exists")
            user = User(
                company_id=auth.company_id,
                email=body.email.lower(),
                password_hash=hash_password(body.password),
                role=role,
            )
            session.add(user)
            session.flush()
            link_channel_identity(session, auth.company_id, user.id, "web", str(user.id))
            if body.display_name:
                from symposa2.services.profile import upsert_profile

                upsert_profile(
                    session,
                    auth.company_id,
                    user.id,
                    display_name=body.display_name,
                    soul_md=None,
                )
            return TenantUserOut(
                id=user.id,
                email=user.email,
                role=user.role,
                display_name=body.display_name,
                created_at=user.created_at,
            )

    @app.delete("/company/users/{user_id}")
    def tenant_users_delete(
        user_id: UUID,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> dict:
        if auth.role != "admin":
            raise HTTPException(status_code=403, detail="Admin only")
        if user_id == auth.user_id:
            raise HTTPException(status_code=400, detail="You cannot delete yourself")
        with session_scope() as session:
            user = session.query(User).filter(User.company_id == auth.company_id, User.id == user_id).first()
            if user is None:
                raise HTTPException(status_code=404, detail="User not found")
            session.delete(user)
        return {"ok": True}

    @app.get("/catalog/skills", response_model=SkillsCatalogOut)
    def catalog_skills(
        auth: Annotated[AuthContext, Depends(get_auth)],
        allowlist: Optional[str] = Query(None, description="Set to 'company' for workspace allowlist"),
    ) -> SkillsCatalogOut:
        skill_allowlist = None
        if allowlist == "company":
            from symposa.services.company_defaults import get_company_workspace_config

            with session_scope() as session:
                _, skill_allowlist, _ = get_company_workspace_config(session, auth.company_id)
        data = list_skills_catalog(allowlist=skill_allowlist)
        return SkillsCatalogOut(
            skills=data.get("skills") or [],
            categories=data.get("categories") or [],
            count=int(data.get("count") or 0),
        )

    @app.get("/catalog/tools", response_model=ToolsCatalogOut)
    def catalog_tools(
        auth: Annotated[AuthContext, Depends(get_auth)],
        platform: str = Query("api_server"),
    ) -> ToolsCatalogOut:
        from symposa.services.company_defaults import get_company_workspace_config

        with session_scope() as session:
            toolsets, _, _ = get_company_workspace_config(session, auth.company_id)
        data = list_tools_catalog(platform=platform, toolsets_override=toolsets)
        return ToolsCatalogOut(
            platform=data["platform"],
            toolsets=data.get("toolsets") or [],
            tools=[ToolCatalogItem(**t) for t in data.get("tools") or []],
            count=int(data.get("count") or 0),
        )

    @app.get("/catalog/hermes-health")
    def catalog_hermes_health(
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> dict:
        return hermes_health()

    @app.get("/conversations", response_model=List[ConversationOut])
    def conversations_list(
        auth: Annotated[AuthContext, Depends(get_auth)],
        include_archived: bool = False,
    ) -> List[ConversationOut]:
        with session_scope() as session:
            rows = list_conversations(
                session, auth.company_id, auth.user_id, include_archived=include_archived
            )
            return [_conversation_out(r) for r in rows]

    @app.post("/conversations", response_model=ConversationOut, status_code=201)
    def conversations_create(
        body: ConversationCreate,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> ConversationOut:
        with session_scope() as session:
            conv = create_conversation(
                session, auth.company_id, auth.user_id, title=body.title
            )
            return _conversation_out(conv)

    @app.get("/conversations/{conversation_id}", response_model=ConversationOut)
    def conversations_get(
        conversation_id: UUID,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> ConversationOut:
        with session_scope() as session:
            conv = get_conversation(session, auth.company_id, auth.user_id, conversation_id)
            if conv is None:
                raise HTTPException(status_code=404, detail="Not found")
            return _conversation_out(conv)

    @app.patch("/conversations/{conversation_id}", response_model=ConversationOut)
    def conversations_patch(
        conversation_id: UUID,
        body: ConversationPatch,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> ConversationOut:
        with session_scope() as session:
            conv = get_conversation(session, auth.company_id, auth.user_id, conversation_id)
            if conv is None:
                raise HTTPException(status_code=404, detail="Not found")
            if body.title is not None:
                conv.title = body.title
            if body.archived is True:
                conv.archived_at = datetime.now(timezone.utc)
            elif body.archived is False:
                conv.archived_at = None
            session.flush()
            return _conversation_out(conv)

    @app.put("/conversations/{conversation_id}/active")
    def conversations_set_active(
        conversation_id: UUID,
        auth: Annotated[AuthContext, Depends(get_auth)],
        channel: str = Query("web"),
        sync_whatsapp: bool = Query(False),
    ) -> dict:
        with session_scope() as session:
            set_active_conversation(
                session, auth.company_id, auth.user_id, channel, conversation_id
            )
            if sync_whatsapp:
                set_active_conversation(
                    session, auth.company_id, auth.user_id, "whatsapp", conversation_id
                )
        return {"ok": True, "conversation_id": str(conversation_id), "channel": channel}

    @app.get("/conversations/{conversation_id}/events", response_model=List[EventOut])
    def events_list(
        conversation_id: UUID,
        auth: Annotated[AuthContext, Depends(get_auth)],
        limit: int = Query(100, le=500),
    ) -> List[EventOut]:
        with session_scope() as session:
            rows = list_events(
                session, auth.company_id, auth.user_id, conversation_id, limit=limit
            )
            return [_event_out(r) for r in rows]

    @app.get("/conversations/{conversation_id}/events/stream")
    async def events_stream(
        conversation_id: UUID,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> StreamingResponse:
        async def gen() -> AsyncIterator[str]:
            last: Optional[datetime] = None
            while True:
                with session_scope() as session:
                    rows = list_events(
                        session,
                        auth.company_id,
                        auth.user_id,
                        conversation_id,
                        after=last,
                        limit=50,
                    )
                    payloads = [
                        {
                            "id": str(row.id),
                            "channel": row.channel,
                            "role": row.role,
                            "content_text": row.content_text,
                            "created_at": row.created_at.isoformat(),
                        }
                        for row in rows
                    ]
                for payload in payloads:
                    yield f"data: {json.dumps(payload)}\n\n"
                    last = datetime.fromisoformat(payload["created_at"])
                await asyncio.sleep(2)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/conversations/{conversation_id}/chat", response_model=ChatResponse)
    def conversation_chat(
        conversation_id: UUID,
        body: ChatRequest,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> ChatResponse:
        with session_scope() as session:
            conv = get_conversation(session, auth.company_id, auth.user_id, conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Not found")
        reply, sid = chat_via_hermes(
            auth.company_id,
            auth.user_id,
            conversation_id,
            body.message,
            hermes_session_id=body.hermes_session_id,
        )
        return ChatResponse(reply=reply, hermes_session_id=sid)

    @app.post(
        "/conversations/{conversation_id}/chat/stream",
        tags=["conversations"],
        summary="Stream chat completion (SSE)",
    )
    async def conversation_chat_stream(
        conversation_id: UUID,
        body: ChatRequest,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> StreamingResponse:
        with session_scope() as session:
            conv = get_conversation(session, auth.company_id, auth.user_id, conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Not found")

        async def gen() -> AsyncIterator[bytes]:
            async for chunk in chat_via_hermes_stream(
                auth.company_id,
                auth.user_id,
                conversation_id,
                body.message,
                hermes_session_id=body.hermes_session_id,
            ):
                yield chunk

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post(
        "/conversations/{conversation_id}/clarify",
        tags=["conversations"],
        summary="Respond to an in-flight clarify prompt",
    )
    def conversation_clarify(
        conversation_id: UUID,
        body: ClarifyRespondRequest,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> dict:
        with session_scope() as session:
            conv = get_conversation(session, auth.company_id, auth.user_id, conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Not found")
        ok = resolve_clarify_response(body.clarify_id, body.response)
        if not ok:
            raise HTTPException(status_code=404, detail="Clarify prompt not found or expired")
        return {"ok": True}

    @app.post(
        "/conversations/{conversation_id}/approval",
        tags=["conversations"],
        summary="Resolve a pending Hermes run approval (dangerous command)",
    )
    def conversation_approval(
        conversation_id: UUID,
        body: RunApprovalRequest,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> dict:
        with session_scope() as session:
            conv = get_conversation(session, auth.company_id, auth.user_id, conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Not found")
        ok = resolve_run_approval(body.run_id, body.choice)
        if not ok:
            raise HTTPException(status_code=404, detail="Approval prompt not found or expired")
        return {"ok": True}

    @app.post("/channel-identities/whatsapp/link")
    def whatsapp_link(
        body: WhatsAppLinkRequest,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> dict:
        from symposa.services.identity import canonical_whatsapp_external_id

        ext = canonical_whatsapp_external_id(body.external_id)
        with session_scope() as session:
            link_channel_identity(session, auth.company_id, auth.user_id, "whatsapp", ext)
        return {"ok": True, "external_id": ext}

    @app.patch("/skills/{skill_name}")
    def skills_patch(
        skill_name: str,
        body: SkillPatchRequest,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> dict:
        with session_scope() as session:
            upsert_user_skill_override(
                session,
                auth.company_id,
                auth.user_id,
                skill_name,
                body.body_md,
                body.description,
            )
        return {"ok": True, "skill_name": skill_name}

    @app.get("/company/agents", response_model=List[AgentOut])
    def company_agents_list(auth: Annotated[AuthContext, Depends(get_auth)]) -> List[AgentOut]:
        with session_scope() as session:
            rows = list(
                session.query(CompanyAgent).filter(CompanyAgent.company_id == auth.company_id)
            )
        return [
            AgentOut(
                id=r.id,
                name=r.name,
                soul_text=r.soul_text,
                toolsets=r.toolsets,
                model=r.model,
                preloaded_skills=r.preloaded_skills,
            )
            for r in rows
        ]

    @app.post("/company/agents", response_model=AgentOut, status_code=201)
    def company_agents_create(
        body: AgentCreate,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> AgentOut:
        if auth.role != "admin":
            raise HTTPException(status_code=403, detail="Admin only")
        with session_scope() as session:
            row = CompanyAgent(
                company_id=auth.company_id,
                name=body.name,
                soul_text=body.soul_text,
                toolsets=body.toolsets,
                model=body.model,
                preloaded_skills=body.preloaded_skills,
            )
            session.add(row)
            session.flush()
        return AgentOut(
            id=row.id,
            name=row.name,
            soul_text=row.soul_text,
            toolsets=row.toolsets,
            model=row.model,
            preloaded_skills=row.preloaded_skills,
        )

    @app.get("/user/agents", response_model=List[AgentOut])
    def user_agents_list(auth: Annotated[AuthContext, Depends(get_auth)]) -> List[AgentOut]:
        with session_scope() as session:
            set_rls_context(session, str(auth.company_id), str(auth.user_id))
            rows = list(
                session.query(UserAgent).filter(
                    UserAgent.company_id == auth.company_id,
                    UserAgent.user_id == auth.user_id,
                )
            )
        return [
            AgentOut(
                id=r.id,
                name=r.name,
                soul_text=r.soul_text,
                toolsets=r.toolsets,
                model=r.model,
                preloaded_skills=r.preloaded_skills,
            )
            for r in rows
        ]

    @app.post("/user/agents", response_model=AgentOut, status_code=201)
    def user_agents_create(
        body: AgentCreate,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> AgentOut:
        with session_scope() as session:
            set_rls_context(session, str(auth.company_id), str(auth.user_id))
            row = UserAgent(
                company_id=auth.company_id,
                user_id=auth.user_id,
                name=body.name,
                soul_text=body.soul_text,
                toolsets=body.toolsets,
                model=body.model,
                preloaded_skills=body.preloaded_skills,
            )
            session.add(row)
            session.flush()
        return AgentOut(
            id=row.id,
            name=row.name,
            soul_text=row.soul_text,
            toolsets=row.toolsets,
            model=row.model,
            preloaded_skills=row.preloaded_skills,
        )

    def _user_file_out(row, *, include_share: bool = False) -> UserFileOut:
        from symposa.services.files import file_to_dict

        d = file_to_dict(row, include_share=include_share)
        return UserFileOut(**d)

    @app.get("/user/files", response_model=UserFileListOut, tags=["files"])
    def user_files_list(auth: Annotated[AuthContext, Depends(get_auth)]) -> UserFileListOut:
        from symposa.services.files import list_files

        with session_scope() as session:
            set_rls_context(session, str(auth.company_id), str(auth.user_id))
            rows = list_files(session, auth.company_id, auth.user_id)
            return UserFileListOut(files=[_user_file_out(r) for r in rows])

    @app.post("/user/files", tags=["files"])
    async def user_files_upload(
        request: Request,
        auth: Annotated[AuthContext, Depends(get_auth)],
        name: str = Query(...),
        content_type: str = Query("application/octet-stream"),
    ) -> UserFileOut:
        body = await request.body()
        from symposa.services.files import create_s3_file
        from symposa.services.storage import put_bytes, storage_key_for_user

        key = storage_key_for_user(auth.company_id, auth.user_id, name)
        put_bytes(key, body, content_type=content_type)
        with session_scope() as session:
            set_rls_context(session, str(auth.company_id), str(auth.user_id))
            row = create_s3_file(
                session,
                auth.company_id,
                auth.user_id,
                name,
                key,
                content_type=content_type,
                size_bytes=len(body),
            )
        return _user_file_out(row, include_share=True)

    @app.get("/user/files/{file_id}", response_model=UserFileOut, tags=["files"])
    def user_files_get(
        file_id: UUID,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> UserFileOut:
        from symposa.services.files import get_owned_file

        with session_scope() as session:
            set_rls_context(session, str(auth.company_id), str(auth.user_id))
            row = get_owned_file(session, auth.company_id, auth.user_id, file_id)
        if row is None:
            raise HTTPException(status_code=404, detail="File not found")
        return _user_file_out(row)

    @app.get("/user/files/{file_id}/content", tags=["files"])
    def user_files_content(
        file_id: UUID,
        auth: Annotated[AuthContext, Depends(get_auth)],
        disposition: Optional[str] = Query(None),
    ) -> Response:
        from symposa.services.files import (
            content_disposition,
            get_owned_file,
            html_csp_header,
            read_file_bytes,
        )

        with session_scope() as session:
            set_rls_context(session, str(auth.company_id), str(auth.user_id))
            row = get_owned_file(session, auth.company_id, auth.user_id, file_id)
        if row is None:
            raise HTTPException(status_code=404, detail="File not found")
        try:
            data = read_file_bytes(row, auth.user_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        force_attachment = (disposition or "").lower() == "attachment"
        headers = {
            "Content-Disposition": content_disposition(row, force_attachment=force_attachment),
        }
        ct = row.content_type or "application/octet-stream"
        if ct == "text/html":
            headers["Content-Security-Policy"] = html_csp_header()
        return Response(content=data, media_type=ct, headers=headers)

    @app.post("/user/files/{file_id}/share", response_model=FileShareOut, tags=["files"])
    def user_files_share(
        file_id: UUID,
        body: FileShareRequest,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> FileShareOut:
        from symposa.config import get_settings
        from symposa.services.files import get_owned_file, mint_share_token, public_share_url

        settings = get_settings()
        ttl = body.ttl_seconds if body.ttl_seconds is not None else settings.file_share_ttl_seconds
        ttl = max(60, min(ttl, settings.file_share_max_ttl_seconds))
        with session_scope() as session:
            set_rls_context(session, str(auth.company_id), str(auth.user_id))
            row = get_owned_file(session, auth.company_id, auth.user_id, file_id)
        if row is None:
            raise HTTPException(status_code=404, detail="File not found")
        token, actual_ttl = mint_share_token(row, ttl_seconds=ttl)
        return FileShareOut(share_url=public_share_url(token), expires_in_seconds=actual_ttl)

    @app.delete("/user/files/{file_id}", tags=["files"])
    def user_files_delete(
        file_id: UUID,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> dict:
        from symposa.services.files import delete_owned_file

        with session_scope() as session:
            set_rls_context(session, str(auth.company_id), str(auth.user_id))
            ok = delete_owned_file(session, auth.company_id, auth.user_id, file_id)
        if not ok:
            raise HTTPException(status_code=404, detail="File not found")
        return {"ok": True}

    @app.get("/public/files/{token:path}", tags=["files"])
    def public_files_content(token: str, disposition: Optional[str] = Query(None)) -> Response:
        from symposa.services.files import (
            content_disposition,
            html_csp_header,
            read_file_bytes,
            resolve_share_token,
        )

        with session_scope() as session:
            row = resolve_share_token(session, token)
        if row is None:
            raise HTTPException(status_code=404, detail="Invalid or expired link")
        try:
            data = read_file_bytes(row, row.user_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        force_attachment = (disposition or "").lower() == "attachment"
        headers = {
            "Content-Disposition": content_disposition(row, force_attachment=force_attachment),
        }
        ct = row.content_type or "application/octet-stream"
        if ct == "text/html":
            headers["Content-Security-Policy"] = html_csp_header()
        return Response(content=data, media_type=ct, headers=headers)

    def _company_file_out(row) -> UserFileOut:
        base = get_settings().link_base_url.rstrip("/")
        if base.endswith("/api"):
            api_base = base
        else:
            api_base = f"{base}/api"
        content_url = f"{api_base}/company/files/{row.id}/content"
        return UserFileOut(
            id=row.id,
            name=row.name,
            source="company",
            content_type=row.content_type,
            size_bytes=row.size_bytes,
            created_at=row.created_at,
            view_url=content_url,
            download_url=f"{content_url}?disposition=attachment",
        )

    @app.get("/company/files", response_model=UserFileListOut, tags=["files"])
    def company_files_list(auth: Annotated[AuthContext, Depends(get_auth)]) -> UserFileListOut:
        from symposa.db.models import CompanyFile

        with session_scope() as session:
            rows = list(
                session.query(CompanyFile)
                .filter(CompanyFile.company_id == auth.company_id)
                .order_by(CompanyFile.created_at.desc())
            )
            return UserFileListOut(files=[_company_file_out(row) for row in rows])

    @app.post("/company/files", response_model=UserFileOut, tags=["files"])
    async def company_files_upload(
        request: Request,
        auth: Annotated[AuthContext, Depends(get_auth)],
        name: str = Query(...),
        content_type: str = Query("application/octet-stream"),
    ) -> dict:
        body = await request.body()
        if auth.role != "admin":
            raise HTTPException(status_code=403, detail="Admin only")
        from symposa.db.models import CompanyFile
        from symposa.services.storage import put_bytes, storage_key_for_company

        key = storage_key_for_company(auth.company_id, name)
        put_bytes(key, body, content_type=content_type)
        with session_scope() as session:
            row = CompanyFile(
                company_id=auth.company_id,
                name=name,
                storage_key=key,
                content_type=content_type,
                size_bytes=len(body),
            )
            session.add(row)
            session.flush()
            return _company_file_out(row)

    @app.get("/company/files/{file_id}/content", tags=["files"])
    def company_files_content(
        file_id: UUID,
        auth: Annotated[AuthContext, Depends(get_auth)],
        disposition: Optional[str] = Query(None),
    ) -> Response:
        from symposa.db.models import CompanyFile
        from symposa.services.files import content_disposition, html_csp_header
        from symposa.services.storage import get_bytes

        with session_scope() as session:
            row = session.query(CompanyFile).filter(
                CompanyFile.id == file_id,
                CompanyFile.company_id == auth.company_id,
            ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="File not found")
        data = get_bytes(row.storage_key)
        if data is None:
            raise HTTPException(status_code=404, detail="File bytes not found")
        force_attachment = (disposition or "").lower() == "attachment"
        headers = {
            "Content-Disposition": content_disposition(row, force_attachment=force_attachment),
        }
        ct = row.content_type or "application/octet-stream"
        if ct == "text/html":
            headers["Content-Security-Policy"] = html_csp_header()
        return Response(content=data, media_type=ct, headers=headers)

    @app.delete("/company/files/{file_id}", tags=["files"])
    def company_files_delete(
        file_id: UUID,
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> dict:
        if auth.role != "admin":
            raise HTTPException(status_code=403, detail="Admin only")
        from symposa.db.models import CompanyFile
        from symposa.services.storage import delete_object

        with session_scope() as session:
            row = session.query(CompanyFile).filter(
                CompanyFile.id == file_id,
                CompanyFile.company_id == auth.company_id,
            ).first()
            if row is None:
                raise HTTPException(status_code=404, detail="File not found")
            delete_object(row.storage_key)
            session.delete(row)
        return {"ok": True}

    @app.post("/user/credentials/{provider}")
    def user_credentials_put(
        provider: str,
        auth: Annotated[AuthContext, Depends(get_auth)],
        body: CredentialPutRequest,
    ) -> dict:
        from symposa.services.credentials import upsert_user_credential

        with session_scope() as session:
            upsert_user_credential(
                session, auth.company_id, auth.user_id, provider, body.payload
            )
        return {"ok": True, "provider": provider}

    @app.get(
        "/company/integrations/google",
        response_model=GoogleCompanyIntegrationStatus,
        tags=["company-integrations"],
        summary="Get company Google OAuth client status",
    )
    def company_google_integration_get(
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> GoogleCompanyIntegrationStatus:
        if auth.role != "admin":
            raise HTTPException(status_code=403, detail="Admin only")
        from symposa.services.google_oauth import company_google_client_status

        with session_scope() as session:
            data = company_google_client_status(session, auth.company_id)
        return GoogleCompanyIntegrationStatus(**data)

    @app.put(
        "/company/integrations/google",
        response_model=GoogleCompanyIntegrationResponse,
        tags=["company-integrations"],
        summary="Register company Google OAuth client (client ID + secret)",
    )
    def company_google_integration_put(
        auth: Annotated[AuthContext, Depends(get_auth)],
        body: GoogleCompanyIntegrationRequest,
    ) -> GoogleCompanyIntegrationResponse:
        if auth.role != "admin":
            raise HTTPException(status_code=403, detail="Admin only")
        from symposa.config import get_settings
        from symposa.services.google_oauth import upsert_company_google_client

        settings = get_settings()
        redirect_uri = body.redirect_uri or settings.google_redirect_uri
        with session_scope() as session:
            upsert_company_google_client(
                session,
                auth.company_id,
                body.client_id.strip(),
                body.client_secret.strip(),
                redirect_uri,
            )
        return GoogleCompanyIntegrationResponse(
            client_id=body.client_id.strip(),
            redirect_uri=redirect_uri,
        )

    @app.get(
        "/integrations/google/status",
        response_model=GoogleWorkspaceUserStatus,
        tags=["integrations"],
        summary="Current user's Google Workspace connection status",
    )
    def google_integration_status(
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> GoogleWorkspaceUserStatus:
        from symposa.services.google_oauth import google_workspace_status

        with session_scope() as session:
            data = google_workspace_status(session, auth.company_id, auth.user_id)
        return GoogleWorkspaceUserStatus(**data)

    def _google_authorize_url(company_id: UUID, user_id: UUID) -> str:
        from symposa.services.google_oauth import start_google_connect

        try:
            with session_scope() as session:
                return start_google_connect(session, company_id, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get(
        "/integrations/google/connect-url",
        response_model=GoogleConnectUrlResponse,
        tags=["integrations"],
        summary="Get Google OAuth URL to connect your account (for Swagger / SPA)",
    )
    def google_integration_connect_url(
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> GoogleConnectUrlResponse:
        """Returns the Google consent URL as JSON. Open it in a browser to link your account."""
        url = _google_authorize_url(auth.company_id, auth.user_id)
        return GoogleConnectUrlResponse(authorize_url=url)

    @app.get(
        "/integrations/google/connect",
        tags=["integrations"],
        summary="Connect Google account (HTTP redirect to Google)",
        responses={302: {"description": "Redirect to Google consent screen"}},
    )
    def google_integration_connect(
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> RedirectResponse:
        """Browser-friendly redirect. For Swagger, use GET /integrations/google/connect-url instead."""
        url = _google_authorize_url(auth.company_id, auth.user_id)
        return RedirectResponse(url=url, status_code=302)

    @app.get(
        "/oauth/google/callback",
        tags=["integrations"],
        summary="Google OAuth callback (public)",
        include_in_schema=True,
    )
    def google_oauth_callback(
        code: str = Query(...),
        state: str = Query(...),
    ) -> RedirectResponse:
        from symposa.config import get_settings
        from symposa.services.google_oauth import complete_google_callback

        settings = get_settings()
        try:
            with session_scope() as session:
                complete_google_callback(session, state, code)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(url=settings.google_success_url, status_code=302)

    @app.delete(
        "/integrations/google",
        tags=["integrations"],
        summary="Disconnect Google Workspace for current user",
    )
    def google_integration_delete(
        auth: Annotated[AuthContext, Depends(get_auth)],
    ) -> dict:
        from symposa.services.google_oauth import revoke_google_workspace

        with session_scope() as session:
            ok = revoke_google_workspace(session, auth.company_id, auth.user_id)
        return {"ok": ok}

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "symposa2"}

    from symposa2.api.routes import register_routes

    register_routes(app)

    web_dist = Path(__file__).resolve().parents[1] / "web" / "dist"
    if web_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="symposa-web")

    return app
