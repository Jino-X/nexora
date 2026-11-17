"""Health and capability status (used by the UI to show honest disabled states)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import ServicesDep
from app.core.exceptions import AppError

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(services: ServicesDep) -> dict[str, Any]:
    try:
        async with services.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise AppError("Database unavailable", code="db_unavailable", status_code=503) from exc
    return {"status": "ready"}


@router.get("/api/v1/system/status")
async def system_status(services: ServicesDep) -> dict[str, Any]:
    s = services.settings
    primary = services.llm.provider(s.llm_provider)
    primary_ok = await primary.health() if primary is not None else False
    chain = services.llm.chain("auto")
    return {
        "environment": s.app_env,
        "auth": {"mode": "dev" if s.auth_dev_mode else "supabase", "supabase": bool(s.supabase_url)},
        "llm": {
            "primary": s.llm_provider,
            "model": primary.model if primary else None,
            "primary_available": primary_ok,
            "providers": services.llm.names,
            "offline_fallback": "offline" in services.llm.names,
            "status": chain.primary_status(),
        },
        "embeddings": {"model": services.embeddings.model_id},
        "voice": {"livekit": services.livekit.configured, "agent_name": s.livekit_agent_name},
        "vault": {"configured": services.vault.cipher is not None, "key_provider": s.key_provider},
        "integrations": {
            "gmail": s.google_configured,
            "youtube": services.youtube.configured,
            "spotify": bool(s.spotify_client_id),
            "whatsapp_webhook": bool(s.whatsapp_webhook_verify_token),
            "weather": True,
            "maps": True,
            "news": True,
        },
    }
