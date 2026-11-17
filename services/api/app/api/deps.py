"""FastAPI dependencies: services, database session, authenticated user, rate limits."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.core.logging import user_id_var
from app.core.security import AuthenticatedUser, verify_internal_key
from app.database import repositories as repo
from app.database.session import session_scope
from app.services import Services

bearer = HTTPBearer(auto_error=False, description="Supabase access token")


def get_services(request: Request) -> Services:
    return request.app.state.services


ServicesDep = Annotated[Services, Depends(get_services)]


async def get_db(services: ServicesDep) -> AsyncIterator[AsyncSession]:
    async with session_scope(services.sessionmaker) as session:
        yield session


# scope="function": commit before the response is sent, so clients never read stale data.
DB = Annotated[AsyncSession, Depends(get_db, scope="function")]


async def current_user(
    request: Request,
    services: ServicesDep,
    db: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AuthenticatedUser:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer token")
    user = await services.verifier.verify(credentials.credentials)
    user_id_var.set(str(user.id))
    services.rate_limiter.check(f"user:{user.id}", services.settings.rate_limit_per_minute)
    known: set[str] = request.app.state.known_profiles
    if str(user.id) not in known:
        await repo.ensure_profile(db, user.id, user.email)
        # Commit now: services that open their own sessions (runs, approvals) insert rows referencing
        # the profile, and must not wait on this request's uncommitted transaction.
        await db.commit()
        if len(known) > 50_000:
            known.clear()
        known.add(str(user.id))
    return user


CurrentUser = Annotated[AuthenticatedUser, Depends(current_user)]


def rate_limit(bucket: str, setting: str) -> Callable[..., None]:
    def _check(services: ServicesDep, user: CurrentUser) -> None:
        services.rate_limiter.check(f"{bucket}:{user.id}", int(getattr(services.settings, setting)))

    return _check


def require_internal(services: ServicesDep, x_nexora_internal_key: Annotated[str | None, Header()] = None) -> None:
    verify_internal_key(services.settings, x_nexora_internal_key)


def client_meta(request: Request) -> tuple[str | None, str | None]:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)
    return ip, request.headers.get("user-agent")
