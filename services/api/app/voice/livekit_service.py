"""LiveKit access tokens and room management. Only the API can mint tokens. They are short-lived,
scoped to one private room, limited to microphone publishing, and they dispatch the Nexora agent
explicitly."""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from livekit import api

from app.config import Settings
from app.core.exceptions import NotConfiguredError

logger = logging.getLogger("nexora.voice")


class LiveKitService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return self.settings.livekit_configured

    def _require(self) -> tuple[str, str, str]:
        if not self.configured:
            raise NotConfiguredError(
                "Voice is not configured on this server (LIVEKIT_URL / API key / secret)", code="voice_not_configured"
            )
        assert self.settings.livekit_url and self.settings.livekit_api_key and self.settings.livekit_api_secret
        return (
            self.settings.livekit_url,
            self.settings.livekit_api_key,
            self.settings.livekit_api_secret.get_secret_value(),
        )

    def create_participant_token(
        self, *, identity: str, name: str | None, room: str, agent_metadata: dict[str, Any]
    ) -> str:
        _, key, secret = self._require()
        token = (
            api.AccessToken(key, secret)
            .with_identity(identity)
            .with_name(name or "Nexora user")
            .with_ttl(timedelta(seconds=self.settings.voice_token_ttl_seconds))
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                    can_publish_sources=["microphone"],
                    can_update_own_metadata=False,
                )
            )
            .with_room_config(
                api.RoomConfiguration(
                    empty_timeout=60,
                    departure_timeout=20,
                    max_participants=2,
                    agents=[
                        api.RoomAgentDispatch(
                            agent_name=self.settings.livekit_agent_name, metadata=json.dumps(agent_metadata)
                        )
                    ],
                )
            )
        )
        return token.to_jwt()

    async def delete_room(self, room: str) -> None:
        if not self.configured:
            return
        url, key, secret = self._require()
        lk = api.LiveKitAPI(url, key, secret)
        try:
            await lk.room.delete_room(api.DeleteRoomRequest(room=room))
        except Exception as exc:  # room may already be gone
            logger.info("delete_room %s: %s", room, type(exc).__name__)
        finally:
            await lk.aclose()
