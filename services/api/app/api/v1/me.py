"""Profile, preferences, onboarding, usage, data export and account deletion."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, ServicesDep, client_meta
from app.automations.schedule import zone
from app.core.exceptions import ValidationFailedError
from app.database import models as m
from app.database import repositories as repo
from app.database.base import utcnow
from app.schemas.common import OkResponse
from app.schemas.resources import (
    MeOut,
    OnboardingIn,
    PreferencesOut,
    PreferencesUpdate,
    ProfileOut,
    ProfileUpdate,
)

router = APIRouter(prefix="/me", tags=["me"])
logger = logging.getLogger("nexora.me")


async def _me(db: DB, user_id: Any) -> MeOut:
    profile = await db.get(m.Profile, user_id)
    prefs = await repo.get_preferences(db, user_id)
    return MeOut(profile=ProfileOut.model_validate(profile), preferences=PreferencesOut.model_validate(prefs))


@router.get("", response_model=MeOut)
async def get_me(user: CurrentUser, db: DB) -> MeOut:
    return await _me(db, user.id)


@router.patch("/profile", response_model=ProfileOut)
async def update_profile(body: ProfileUpdate, user: CurrentUser, db: DB) -> ProfileOut:
    profile = await db.get(m.Profile, user.id)
    assert profile is not None
    data = body.model_dump(exclude_none=True)
    if "timezone" in data:
        zone(data["timezone"])
    for key, value in data.items():
        setattr(profile, key, value)
    await db.flush()
    return ProfileOut.model_validate(profile)


@router.patch("/preferences", response_model=PreferencesOut)
async def update_preferences(body: PreferencesUpdate, user: CurrentUser, db: DB) -> PreferencesOut:
    prefs = await repo.get_preferences(db, user.id)
    for key, value in body.model_dump(exclude_none=True, exclude={"clear_fields"}).items():
        setattr(prefs, key, value)
    for key in body.clear_fields:
        setattr(prefs, key, None)
    if (prefs.home_latitude is None) != (prefs.home_longitude is None):
        raise ValidationFailedError("Set both home latitude and longitude")
    await db.flush()
    return PreferencesOut.model_validate(prefs)


@router.post("/onboarding", response_model=MeOut)
async def onboarding(body: OnboardingIn, user: CurrentUser, db: DB) -> MeOut:
    zone(body.timezone)
    profile = await db.get(m.Profile, user.id)
    assert profile is not None
    profile.display_name = body.display_name
    profile.timezone = body.timezone
    profile.onboarded_at = profile.onboarded_at or utcnow()
    prefs = await repo.get_preferences(db, user.id)
    prefs.preferred_language = body.preferred_language
    prefs.news_categories = body.news_categories
    prefs.memory_enabled = body.memory_enabled
    if body.home_latitude is not None and body.home_longitude is not None:
        prefs.home_latitude, prefs.home_longitude = body.home_latitude, body.home_longitude
        prefs.home_label = body.home_label
    await db.flush()
    return await _me(db, user.id)


@router.get("/usage")
async def usage(user: CurrentUser, db: DB, days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    since = utcnow() - timedelta(days=days)
    day = func.date(m.ExecutionLog.created_at)
    rows = (
        await db.execute(
            select(
                day.label("day"),
                m.ExecutionLog.event_type,
                m.ExecutionLog.provider,
                func.count().label("calls"),
                func.sum(m.ExecutionLog.input_tokens).label("input_tokens"),
                func.sum(m.ExecutionLog.output_tokens).label("output_tokens"),
                func.avg(m.ExecutionLog.duration_ms).label("avg_ms"),
            )
            .where(m.ExecutionLog.user_id == user.id, m.ExecutionLog.created_at >= since)
            .group_by(day, m.ExecutionLog.event_type, m.ExecutionLog.provider)
            .order_by(day)
        )
    ).all()
    return {
        "days": days,
        "rows": [
            {
                "day": str(r.day),
                "event_type": r.event_type,
                "provider": r.provider,
                "calls": r.calls,
                "input_tokens": int(r.input_tokens or 0),
                "output_tokens": int(r.output_tokens or 0),
                "avg_ms": round(float(r.avg_ms or 0), 1),
            }
            for r in rows
        ],
    }


def _rows(objs: list[Any], exclude: set[str] | None = None) -> list[dict[str, Any]]:
    exclude = exclude or set()
    out = []
    for obj in objs:
        out.append({c.key: getattr(obj, c.key) for c in obj.__mapper__.column_attrs if c.key not in exclude})
    return out


@router.get("/export")
async def export_data(user: CurrentUser, db: DB) -> dict[str, Any]:
    """Everything Nexora stores about the user. Vault secrets and integration tokens are excluded
    (reveal vault items individually). Their metadata is included."""

    async def all_of(model: Any) -> list[Any]:
        return list((await db.execute(select(model).where(model.user_id == user.id))).scalars())

    await repo.audit(db, user.id, action="account.export", resource_type="profile", resource_id=str(user.id))
    return {
        "exported_at": utcnow().isoformat(),
        "profile": _rows([await db.get(m.Profile, user.id)]),
        "preferences": _rows(await all_of(m.UserPreferences)),
        "conversations": _rows(await all_of(m.Conversation)),
        "messages": _rows(await all_of(m.Message)),
        "memories": _rows(await all_of(m.Memory), {"embedding"}),
        "automations": _rows(await all_of(m.AutomationRule), {"lock_token", "locked_until"}),
        "task_runs": _rows(await all_of(m.TaskRun)),
        "approvals": _rows(await all_of(m.Approval)),
        "notifications": _rows(await all_of(m.Notification)),
        "voice_sessions": _rows(await all_of(m.VoiceSession)),
        "integrations": _rows(
            await all_of(m.Integration), {"credentials_ciphertext", "credentials_wrapped_key", "credentials_key_id"}
        ),
        "vault_items": _rows(await all_of(m.VaultItem), {"ciphertext", "wrapped_key"}),
        "tool_permissions": _rows(await all_of(m.ToolPermission)),
        "audit_logs": _rows(await all_of(m.AuditLog)),
    }


class DeleteAccountIn(BaseModel):
    confirm: str


@router.delete("", response_model=OkResponse)
async def delete_account(
    body: DeleteAccountIn, request: Request, user: CurrentUser, db: DB, services: ServicesDep
) -> OkResponse:
    if body.confirm != "DELETE":
        raise ValidationFailedError('Type "DELETE" to confirm account deletion')
    gmail = await repo.get_integration(db, user.id, "gmail")
    if gmail and gmail.credentials_ciphertext and services.cipher:
        try:
            creds = services.credentials.load(gmail)
            await services.google_oauth.revoke(creds.get("refresh_token") or creds.get("access_token", ""))
        except Exception:
            logger.warning("gmail revoke during account deletion failed")
    await repo.delete_user_data(db, user.id)
    request.app.state.known_profiles.discard(str(user.id))
    s = services.settings
    if s.supabase_url and s.supabase_service_role_key:
        key = s.supabase_service_role_key.get_secret_value()
        try:
            await services.http.delete(
                f"{s.supabase_url.rstrip('/')}/auth/v1/admin/users/{user.id}",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                timeout=15,
            )
        except httpx.HTTPError:
            logger.error("supabase auth user deletion failed; delete manually")
    ip, _ = client_meta(request)
    logger.info("account deleted", extra={"data": {"user_id": str(user.id), "ip": ip}})
    return OkResponse(detail="Your account and data were deleted")
