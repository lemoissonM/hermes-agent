"""Symposa2 v2 API routes (profile, skills, integrations)."""

from __future__ import annotations

from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from symposa.api.deps import AuthContext, get_auth
from symposa.config import get_settings
from symposa.db.session import session_scope, set_rls_context
from symposa.services.identity import link_channel_identity
from symposa.services.runtime_paths import user_hermes_home
from symposa2.models.schemas import (
    CompanySkillOut,
    CompanySkillUpsert,
    IntegrationApiKeyPut,
    IntegrationStatusOut,
    ProfileOut,
    ProfileUpdate,
    SkillBodyOut,
    SkillCreate,
    SkillOut,
    SkillUpsert,
    WhatsAppLinkRequest,
)
from symposa2.services.bootstrap import bootstrap_runtime
from symposa2.services.credentials import (
    delete_user_credential,
    list_credential_status,
    upsert_user_credential,
)
from symposa2.services.credential_registry import get_integration, list_integrations
from symposa2.services.profile import build_soul_md, get_profile, materialize_soul, upsert_profile
from symposa2.services.skills import (
    delete_company_skill,
    delete_user_skill,
    list_company_skills,
    get_user_skill,
    list_user_skills,
    materialize_skills,
    upsert_user_skill,
    upsert_company_skill,
)

router = APIRouter(prefix="/v2", tags=["symposa2"])


def _company_skill_out(row) -> CompanySkillOut:
    return CompanySkillOut(
        skill_name=row.skill_name,
        description=row.description,
        enabled=row.enabled,
        is_custom=row.is_custom,
        has_body=bool(row.body_md),
        updated_at=row.updated_at,
    )


@router.get("/profile", response_model=ProfileOut)
def profile_get(auth: Annotated[AuthContext, Depends(get_auth)]) -> ProfileOut:
    with session_scope() as session:
        set_rls_context(session, str(auth.company_id), str(auth.user_id))
        row = get_profile(session, auth.company_id, auth.user_id)
        if row is None:
            from symposa2.services.profile import DEFAULT_SOUL

            return ProfileOut(display_name="Hermes", soul_md=DEFAULT_SOUL)
        return ProfileOut(
            display_name=row.display_name,
            soul_md=row.soul_md,
            updated_at=row.updated_at,
        )


@router.put("/profile", response_model=ProfileOut)
def profile_put(
    body: ProfileUpdate,
    auth: Annotated[AuthContext, Depends(get_auth)],
) -> ProfileOut:
    with session_scope() as session:
        set_rls_context(session, str(auth.company_id), str(auth.user_id))
        row = upsert_profile(
            session,
            auth.company_id,
            auth.user_id,
            display_name=body.display_name,
            soul_md=body.soul_md,
        )
        materialize_soul(session, auth.company_id, auth.user_id, user_hermes_home(auth.user_id))
        return ProfileOut(
            display_name=row.display_name,
            soul_md=row.soul_md,
            updated_at=row.updated_at,
        )


@router.get("/skills", response_model=List[SkillOut])
def skills_list(auth: Annotated[AuthContext, Depends(get_auth)]) -> List[SkillOut]:
    with session_scope() as session:
        set_rls_context(session, str(auth.company_id), str(auth.user_id))
        rows = list_user_skills(session, auth.company_id, auth.user_id)
        return [
            SkillOut(
                skill_name=r.skill_name,
                description=r.description,
                is_custom=r.is_custom,
                has_override=True,
                updated_at=r.updated_at,
            )
            for r in rows
        ]


@router.get("/skills/{skill_name}", response_model=SkillBodyOut)
def skills_get(
    skill_name: str,
    auth: Annotated[AuthContext, Depends(get_auth)],
) -> SkillBodyOut:
    with session_scope() as session:
        set_rls_context(session, str(auth.company_id), str(auth.user_id))
        row = get_user_skill(session, auth.company_id, auth.user_id, skill_name)
        if row is None:
            raise HTTPException(status_code=404, detail="Skill not found in your library")
        return SkillBodyOut(
            skill_name=row.skill_name,
            body_md=row.body_md,
            description=row.description,
            is_custom=row.is_custom,
        )


@router.put("/skills/{skill_name}", response_model=SkillOut)
def skills_put(
    skill_name: str,
    body: SkillUpsert,
    auth: Annotated[AuthContext, Depends(get_auth)],
) -> SkillOut:
    with session_scope() as session:
        set_rls_context(session, str(auth.company_id), str(auth.user_id))
        row = upsert_user_skill(
            session,
            auth.company_id,
            auth.user_id,
            skill_name,
            body.body_md,
            description=body.description,
            is_custom=False,
        )
        home = user_hermes_home(auth.user_id)
        materialize_skills(session, auth.company_id, auth.user_id, home)
        return SkillOut(
            skill_name=row.skill_name,
            description=row.description,
            is_custom=row.is_custom,
            has_override=True,
            updated_at=row.updated_at,
        )


@router.post("/skills", response_model=SkillOut, status_code=201)
def skills_create(
    body: SkillCreate,
    auth: Annotated[AuthContext, Depends(get_auth)],
) -> SkillOut:
    with session_scope() as session:
        set_rls_context(session, str(auth.company_id), str(auth.user_id))
        row = upsert_user_skill(
            session,
            auth.company_id,
            auth.user_id,
            body.skill_name,
            body.body_md,
            description=body.description,
            is_custom=True,
        )
        home = user_hermes_home(auth.user_id)
        materialize_skills(session, auth.company_id, auth.user_id, home)
        return SkillOut(
            skill_name=row.skill_name,
            description=row.description,
            is_custom=True,
            has_override=True,
            updated_at=row.updated_at,
        )


@router.delete("/skills/{skill_name}")
def skills_delete(
    skill_name: str,
    auth: Annotated[AuthContext, Depends(get_auth)],
) -> dict:
    with session_scope() as session:
        set_rls_context(session, str(auth.company_id), str(auth.user_id))
        ok = delete_user_skill(session, auth.company_id, auth.user_id, skill_name)
        if not ok:
            raise HTTPException(status_code=404, detail="Skill not found")
        home = user_hermes_home(auth.user_id)
        materialize_skills(session, auth.company_id, auth.user_id, home)
    return {"ok": True}


@router.get("/company/skills", response_model=List[CompanySkillOut])
def company_skills_list(auth: Annotated[AuthContext, Depends(get_auth)]) -> List[CompanySkillOut]:
    with session_scope() as session:
        set_rls_context(session, str(auth.company_id), str(auth.user_id))
        return [_company_skill_out(row) for row in list_company_skills(session, auth.company_id)]


@router.put("/company/skills/{skill_name}", response_model=CompanySkillOut)
def company_skills_put(
    skill_name: str,
    body: CompanySkillUpsert,
    auth: Annotated[AuthContext, Depends(get_auth)],
) -> CompanySkillOut:
    if auth.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    with session_scope() as session:
        set_rls_context(session, str(auth.company_id), str(auth.user_id))
        row = upsert_company_skill(
            session,
            auth.company_id,
            skill_name,
            description=body.description,
            body_md=body.body_md,
            enabled=body.enabled,
            is_custom=body.is_custom,
        )
        return _company_skill_out(row)


@router.post("/company/skills", response_model=CompanySkillOut, status_code=201)
def company_skills_create(
    body: CompanySkillUpsert,
    auth: Annotated[AuthContext, Depends(get_auth)],
) -> CompanySkillOut:
    return company_skills_put(body.skill_name, body, auth)


@router.delete("/company/skills/{skill_name}")
def company_skills_delete(
    skill_name: str,
    auth: Annotated[AuthContext, Depends(get_auth)],
) -> dict:
    if auth.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    with session_scope() as session:
        set_rls_context(session, str(auth.company_id), str(auth.user_id))
        ok = delete_company_skill(session, auth.company_id, skill_name)
        if not ok:
            raise HTTPException(status_code=404, detail="Skill not found")
    return {"ok": True}


@router.get("/credentials/status", response_model=List[IntegrationStatusOut])
def credentials_status(
    auth: Annotated[AuthContext, Depends(get_auth)],
) -> List[IntegrationStatusOut]:
    with session_scope() as session:
        set_rls_context(session, str(auth.company_id), str(auth.user_id))
        rows = list_credential_status(
            session,
            auth.company_id,
            auth.user_id,
            is_admin=(auth.role == "admin"),
        )
    return [IntegrationStatusOut(**r) for r in rows]


@router.get("/integrations", response_model=List[IntegrationStatusOut])
def integrations_list(
    auth: Annotated[AuthContext, Depends(get_auth)],
) -> List[IntegrationStatusOut]:
    return credentials_status(auth)


@router.put("/integrations/{provider}")
def integrations_connect_api_key(
    provider: str,
    body: IntegrationApiKeyPut,
    auth: Annotated[AuthContext, Depends(get_auth)],
) -> dict:
    integration = get_integration(provider)
    if integration is None or integration.connect_type != "api_key":
        raise HTTPException(status_code=404, detail="Unknown integration")
    if integration.scope == "company" and auth.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    payload = {"token": body.api_key, "api_key": body.api_key}
    with session_scope() as session:
        set_rls_context(session, str(auth.company_id), str(auth.user_id))
        upsert_user_credential(session, auth.company_id, auth.user_id, provider, payload)
    return {"ok": True, "provider": provider}


@router.delete("/integrations/{provider}")
def integrations_disconnect(
    provider: str,
    auth: Annotated[AuthContext, Depends(get_auth)],
) -> dict:
    with session_scope() as session:
        set_rls_context(session, str(auth.company_id), str(auth.user_id))
        ok = delete_user_credential(session, auth.company_id, auth.user_id, provider)
    if not ok:
        raise HTTPException(status_code=404, detail="Not connected")
    return {"ok": True}


@router.get("/integrations/google/connect")
def google_connect_url(auth: Annotated[AuthContext, Depends(get_auth)]) -> dict:
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth not configured (set SYMPOSA_GOOGLE_CLIENT_ID in .env.symposa)",
        )
    from symposa.services.google_oauth import build_google_connect_url

    with session_scope() as session:
        url = build_google_connect_url(session, auth.company_id, auth.user_id)
    return {"url": url}


@router.post("/channel-identities/whatsapp/link")
def whatsapp_link_v2(
    body: WhatsAppLinkRequest,
    auth: Annotated[AuthContext, Depends(get_auth)],
) -> dict:
    from symposa.services.identity import canonical_whatsapp_external_id

    ext = canonical_whatsapp_external_id(body.external_id)
    with session_scope() as session:
        link_channel_identity(session, auth.company_id, auth.user_id, "whatsapp", ext)
    return {"ok": True, "external_id": ext}


def register_routes(app) -> None:
    app.include_router(router)
