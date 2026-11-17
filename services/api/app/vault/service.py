"""Secure vault service. Secrets are encrypted at rest, revealed only through an explicit,
audited user request, and are never passed to the LLM."""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotConfiguredError, ValidationFailedError
from app.database import models as m
from app.database import repositories as repo
from app.database.base import utcnow
from app.vault.encryption import EnvelopeCipher, SealedBox

PURPOSE = "vault_item"
VAULT_KINDS = ("api_key", "password", "note", "document", "secret")


class VaultService:
    def __init__(self, cipher: EnvelopeCipher | None, max_item_bytes: int) -> None:
        self.cipher = cipher
        self.max_item_bytes = max_item_bytes

    def _cipher(self) -> EnvelopeCipher:
        if self.cipher is None:
            raise NotConfiguredError(
                "The vault is not configured on this server (VAULT_MASTER_KEYS)", code="vault_not_configured"
            )
        return self.cipher

    def _payload(self, kind: str, secret: str | None, fields: dict[str, str] | None, file_base64: str | None) -> bytes:
        if kind not in VAULT_KINDS:
            raise ValidationFailedError(f"Unknown vault item kind '{kind}'")
        payload: dict[str, Any] = {"v": 1}
        if secret is not None:
            payload["secret"] = secret
        if fields:
            payload["fields"] = {str(k)[:64]: str(v)[:4096] for k, v in list(fields.items())[:20]}
        if file_base64 is not None:
            try:
                base64.b64decode(file_base64, validate=True)
            except ValueError as exc:
                raise ValidationFailedError("File content must be base64") from exc
            payload["file_base64"] = file_base64
        if len(payload) == 1:
            raise ValidationFailedError("Provide a secret, fields or a file")
        raw = json.dumps(payload, separators=(",", ":")).encode()
        if len(raw) > self.max_item_bytes:
            raise ValidationFailedError(f"Vault item too large (max {self.max_item_bytes} bytes)")
        return raw

    async def create(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        name: str,
        kind: str,
        description: str | None,
        secret: str | None = None,
        fields: dict[str, str] | None = None,
        file_base64: str | None = None,
        content_type: str | None = None,
    ) -> m.VaultItem:
        cipher = self._cipher()
        raw = self._payload(kind, secret, fields, file_base64)
        item_id = uuid.uuid4()
        box = cipher.seal(raw, cipher.context(PURPOSE, user_id, item_id))
        item = m.VaultItem(
            id=item_id,
            user_id=user_id,
            name=name.strip()[:120],
            kind=kind,
            description=(description or "").strip()[:500] or None,
            content_type=content_type,
            size_bytes=len(raw),
            ciphertext=box.ciphertext,
            wrapped_key=box.wrapped_key,
            key_id=box.key_id,
        )
        session.add(item)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise ConflictError("A vault item with this name already exists") from exc
        return item

    async def update(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        item_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        secret: str | None = None,
        fields: dict[str, str] | None = None,
        file_base64: str | None = None,
    ) -> m.VaultItem:
        item = await repo.get_owned(session, m.VaultItem, user_id, item_id, label="Vault item")
        if name is not None:
            item.name = name.strip()[:120]
        if description is not None:
            item.description = description.strip()[:500] or None
        if secret is not None or fields is not None or file_base64 is not None:
            cipher = self._cipher()
            raw = self._payload(item.kind, secret, fields, file_base64)
            box = cipher.seal(raw, cipher.context(PURPOSE, user_id, item.id))
            item.ciphertext, item.wrapped_key, item.key_id = box.ciphertext, box.wrapped_key, box.key_id
            item.size_bytes = len(raw)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise ConflictError("A vault item with this name already exists") from exc
        return item

    async def reveal(self, session: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> dict[str, Any]:
        cipher = self._cipher()
        item = await repo.get_owned(session, m.VaultItem, user_id, item_id, label="Vault item")
        payload = json.loads(
            cipher.open(
                SealedBox(item.key_id, item.wrapped_key, item.ciphertext), cipher.context(PURPOSE, user_id, item.id)
            )
        )
        item.last_accessed_at = utcnow()
        await session.flush()
        return payload

    async def rotate_user_items(self, session: AsyncSession, user_id: uuid.UUID | None = None) -> int:
        """Re-wrap data keys under the active master key."""
        cipher = self._cipher()
        stmt = select(m.VaultItem)
        if user_id:
            stmt = stmt.where(m.VaultItem.user_id == user_id)
        count = 0
        for item in (await session.execute(stmt)).scalars():
            box = SealedBox(item.key_id, item.wrapped_key, item.ciphertext)
            if cipher.needs_rewrap(box):
                new = cipher.rewrap(box, cipher.context(PURPOSE, item.user_id, item.id))
                item.key_id, item.wrapped_key = new.key_id, new.wrapped_key
                count += 1
        await session.flush()
        return count
