"""Development-only login (AUTH_DEV_MODE=true, never in production). Production uses Supabase Auth
in the browser. The API only verifies Supabase-issued JWTs."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import DB, ServicesDep
from app.core.exceptions import PermissionDeniedError
from app.core.security import dev_user_id, issue_dev_token
from app.database import repositories as repo

router = APIRouter(prefix="/auth", tags=["auth"])


class DevLoginIn(BaseModel):
    email: EmailStr
    display_name: str | None = Field(None, max_length=120)


class DevLoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: int
    user_id: str


@router.post("/dev/login", response_model=DevLoginOut)
async def dev_login(body: DevLoginIn, services: ServicesDep, db: DB) -> DevLoginOut:
    settings = services.settings
    if not settings.auth_dev_mode or settings.app_env == "production":
        raise PermissionDeniedError("Development login is disabled", code="dev_login_disabled")
    services.rate_limiter.check(f"devlogin:{body.email}", 20)
    user_id = dev_user_id(body.email)
    profile = await repo.ensure_profile(db, user_id, body.email)
    if body.display_name and not profile.display_name:
        profile.display_name = body.display_name
    token, exp = issue_dev_token(settings, user_id, body.email)
    return DevLoginOut(access_token=token, expires_at=exp, user_id=str(user_id))
