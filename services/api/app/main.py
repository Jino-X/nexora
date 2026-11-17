"""Nexora core API."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    activity,
    assistant,
    auth,
    automations,
    conversations,
    discover,
    integrations,
    me,
    memories,
    messaging,
    system,
    vault,
    voice,
)
from app.automations.scheduler import AutomationScheduler
from app.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from app.services import Services, build_services, close_services

logger = logging.getLogger("nexora")


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        svc = services or await build_services(settings)
        app.state.services = svc
        app.state.known_profiles = set()
        stop = asyncio.Event()
        scheduler_task = None
        if settings.run_scheduler_in_api:
            scheduler_task = asyncio.create_task(AutomationScheduler(svc).run_forever(stop))
        logger.info(
            "nexora api started (env=%s, llm=%s, auth=%s)",
            settings.app_env,
            settings.llm_provider,
            "dev" if settings.auth_dev_mode else "supabase",
        )
        try:
            yield
        finally:
            stop.set()
            if scheduler_task:
                scheduler_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await scheduler_task
            if services is None:
                await close_services(svc)

    app = FastAPI(
        title="Nexora API",
        version="0.1.0",
        description="Core API for the Nexora personal AI assistant. All /api/v1 routes need a Supabase "
        "access token (Bearer) unless noted otherwise.",
        lifespan=lifespan,
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    api = APIRouter(prefix="/api/v1")
    for router in (
        auth.router,
        me.router,
        assistant.router,
        conversations.router,
        voice.router,
        voice.internal,
        integrations.router,
        messaging.gmail,
        messaging.whatsapp,
        discover.location,
        discover.weather,
        discover.news,
        discover.youtube,
        discover.music,
        memories.router,
        vault.router,
        automations.router,
        activity.tasks,
        activity.approvals,
        activity.notifications,
        activity.permissions,
        activity.dashboard,
    ):
        api.include_router(router)
    app.include_router(system.router)
    app.include_router(api)
    return app


# Run with: uvicorn app.main:create_app --factory
