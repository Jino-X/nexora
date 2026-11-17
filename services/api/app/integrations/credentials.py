"""Encrypted per-user integration credentials (OAuth tokens, WhatsApp access tokens)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotConfiguredError, NotFoundError
from app.database import models as m
from app.database import repositories as repo
from app.database.base import utcnow
from app.vault.encryption import EnvelopeCipher, SealedBox

PURPOSE = "integration_credentials"


class CredentialStore:
    def __init__(self, cipher: EnvelopeCipher | None) -> None:
        self.cipher = cipher

    def _require_cipher(self) -> EnvelopeCipher:
        if self.cipher is None:
            raise NotConfiguredError(
                "Credential encryption is not configured (set VAULT_MASTER_KEYS)", code="encryption_not_configured"
            )
        return self.cipher

    async def save(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        provider: str,
        credentials: dict[str, Any],
        *,
        account_label: str | None = None,
        scopes: list[str] | None = None,
        config: dict[str, Any] | None = None,
        expires_at: datetime | None = None,
    ) -> m.Integration:
        cipher = self._require_cipher()
        integ = await repo.get_integration(session, user_id, provider)
        if integ is None:
            integ = m.Integration(id=uuid.uuid4(), user_id=user_id, provider=provider)
            session.add(integ)
        box = cipher.seal_json(credentials, cipher.context(PURPOSE, user_id, integ.id))
        integ.credentials_ciphertext = box.ciphertext
        integ.credentials_wrapped_key = box.wrapped_key
        integ.credentials_key_id = box.key_id
        integ.status = "connected"
        integ.last_error = None
        integ.token_expires_at = expires_at
        integ.connected_at = integ.connected_at or utcnow()
        if account_label is not None:
            integ.account_label = account_label
        if scopes is not None:
            integ.scopes = scopes
        if config is not None:
            integ.config = config
        await session.flush()
        return integ

    def load(self, integ: m.Integration) -> dict[str, Any]:
        cipher = self._require_cipher()
        if not (integ.credentials_ciphertext and integ.credentials_wrapped_key and integ.credentials_key_id):
            raise NotFoundError(f"{integ.provider} has no stored credentials")
        box = SealedBox(integ.credentials_key_id, integ.credentials_wrapped_key, integ.credentials_ciphertext)
        return cipher.open_json(box, cipher.context(PURPOSE, integ.user_id, integ.id))

    async def update_tokens(
        self, session: AsyncSession, integ: m.Integration, credentials: dict[str, Any], expires_at: datetime | None
    ) -> None:
        cipher = self._require_cipher()
        box = cipher.seal_json(credentials, cipher.context(PURPOSE, integ.user_id, integ.id))
        integ.credentials_ciphertext = box.ciphertext
        integ.credentials_wrapped_key = box.wrapped_key
        integ.credentials_key_id = box.key_id
        integ.token_expires_at = expires_at
        await session.flush()

    @staticmethod
    async def disconnect(session: AsyncSession, integ: m.Integration) -> None:
        integ.status = "disconnected"
        integ.credentials_ciphertext = None
        integ.credentials_wrapped_key = None
        integ.credentials_key_id = None
        integ.token_expires_at = None
        integ.last_error = None
        await session.flush()

    @staticmethod
    async def mark_error(session: AsyncSession, integ: m.Integration, message: str) -> None:
        integ.status = "error"
        integ.last_error = message[:500]
        await session.flush()
