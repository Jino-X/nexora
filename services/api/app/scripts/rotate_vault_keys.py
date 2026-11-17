"""Re-wrap every vault item and integration credential under the active master key.

Rotation procedure (see docs/security.md):
  1. Generate a new key: python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"
  2. Prepend it to VAULT_MASTER_KEYS ("k2:<new>,k1:<old>") and set VAULT_ACTIVE_KEY_ID=k2; deploy.
  3. Run: python -m app.scripts.rotate_vault_keys          (idempotent; safe to re-run)
  4. When it reports 0 remaining, remove k1 from VAULT_MASTER_KEYS and deploy again.
Payload ciphertexts never change. Only the wrapped data keys are re-encrypted.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.config import get_settings
from app.database import models as m
from app.database.session import session_scope
from app.integrations.credentials import PURPOSE as CREDENTIALS_PURPOSE
from app.services import build_services, close_services
from app.vault.encryption import SealedBox


async def rotate() -> int:
    services = await build_services(get_settings())
    try:
        if services.cipher is None:
            print("No key provider configured", file=sys.stderr)
            return 1
        cipher = services.cipher
        async with session_scope(services.sessionmaker) as s:
            vault_count = await services.vault.rotate_user_items(s)
            cred_count = 0
            for integ in (await s.execute(select(m.Integration))).scalars():
                if not (integ.credentials_key_id and integ.credentials_wrapped_key and integ.credentials_ciphertext):
                    continue
                box = SealedBox(integ.credentials_key_id, integ.credentials_wrapped_key, integ.credentials_ciphertext)
                if cipher.needs_rewrap(box):
                    new = cipher.rewrap(box, cipher.context(CREDENTIALS_PURPOSE, integ.user_id, integ.id))
                    integ.credentials_key_id, integ.credentials_wrapped_key = new.key_id, new.wrapped_key
                    cred_count += 1
        async with session_scope(services.sessionmaker) as s:
            active = cipher.provider.active_key_id
            remaining = len([1 for k in (await s.execute(select(m.VaultItem.key_id))).scalars() if k != active])
            remaining += len(
                [1 for k in (await s.execute(select(m.Integration.credentials_key_id))).scalars() if k and k != active]
            )
        print(
            f"re-wrapped {vault_count} vault item(s) and {cred_count} credential(s); {remaining} remaining on old keys"
        )
        return 0
    finally:
        await close_services(services)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(rotate()))
