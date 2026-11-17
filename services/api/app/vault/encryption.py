"""Envelope encryption for vault items and OAuth credentials.

Design (see docs/security.md):
* Each record gets a fresh 256-bit data-encryption key (DEK). The payload is encrypted with
  AES-256-GCM under the DEK, with a random 96-bit nonce stored as a prefix of the ciphertext.
* The DEK is wrapped by a key-encryption key (KEK) held by a `KeyProvider`: a versioned local
  keyring (keys live in the environment / secret manager, never in the database) or AWS KMS.
* Associated data binds every ciphertext to (purpose, user_id, record_id). A row copied to another
  user or record fails authentication.
* Rotation: add a new KEK, mark it active, then call `rewrap()` (scripts/rotate_vault_keys.py). DEKs
  are re-wrapped and payloads are never decrypted to disk.
"""

from __future__ import annotations

import base64
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import Settings
from app.core.exceptions import AppError, NotConfiguredError

NONCE_BYTES = 12
KEY_BYTES = 32


class DecryptionError(AppError):
    status_code = 500
    code = "decryption_failed"


def _aad(context: dict[str, str]) -> bytes:
    return json.dumps(context, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True)
class SealedBox:
    key_id: str
    wrapped_key: bytes
    ciphertext: bytes


class KeyProvider(ABC):
    @property
    @abstractmethod
    def active_key_id(self) -> str: ...

    @abstractmethod
    def wrap(self, dek: bytes, context: dict[str, str]) -> tuple[str, bytes]: ...

    @abstractmethod
    def unwrap(self, key_id: str, wrapped: bytes, context: dict[str, str]) -> bytes: ...


class LocalKeyring(KeyProvider):
    """Versioned KEKs from configuration: "k2:<b64>,k1:<b64>" with an explicit active id."""

    def __init__(self, keys: dict[str, bytes], active_key_id: str) -> None:
        if active_key_id not in keys:
            raise ValueError(f"active key id '{active_key_id}' not present in keyring")
        for kid, key in keys.items():
            if len(key) != KEY_BYTES:
                raise ValueError(f"key '{kid}' must be {KEY_BYTES} bytes")
        self._keys = keys
        self._active = active_key_id

    @classmethod
    def from_config(cls, raw: str, active: str | None) -> LocalKeyring:
        keys: dict[str, bytes] = {}
        for entry in raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            kid, _, b64 = entry.partition(":")
            if not kid or not b64:
                raise ValueError("VAULT_MASTER_KEYS entries must look like '<id>:<base64>'")
            keys[kid.strip()] = base64.b64decode(b64.strip())
        if not keys:
            raise ValueError("VAULT_MASTER_KEYS is empty")
        return cls(keys, active or next(iter(keys)))

    @property
    def active_key_id(self) -> str:
        return f"local:{self._active}"

    def wrap(self, dek: bytes, context: dict[str, str]) -> tuple[str, bytes]:
        nonce = os.urandom(NONCE_BYTES)
        wrapped = AESGCM(self._keys[self._active]).encrypt(nonce, dek, _aad({"wrap": "dek", **context}))
        return self.active_key_id, nonce + wrapped

    def unwrap(self, key_id: str, wrapped: bytes, context: dict[str, str]) -> bytes:
        kid = key_id.removeprefix("local:")
        if kid not in self._keys:
            raise DecryptionError("Encryption key is no longer available")
        try:
            return AESGCM(self._keys[kid]).decrypt(
                wrapped[:NONCE_BYTES], wrapped[NONCE_BYTES:], _aad({"wrap": "dek", **context})
            )
        except InvalidTag as exc:
            raise DecryptionError("Key unwrap failed") from exc


class AwsKmsKeyProvider(KeyProvider):
    """Wraps DEKs with AWS KMS (`Encrypt`/`Decrypt` with an encryption context).

    Requires the optional `boto3` dependency (`pip install .[aws]`) and IAM permissions
    kms:Encrypt and kms:Decrypt on the key."""

    def __init__(self, key_id: str, region: str | None) -> None:
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise NotConfiguredError("KEY_PROVIDER=aws_kms requires boto3 (pip install '.[aws]')") from exc
        self._client = boto3.client("kms", region_name=region)
        self._key_id = key_id

    @property
    def active_key_id(self) -> str:
        return f"kms:{self._key_id}"

    def wrap(self, dek: bytes, context: dict[str, str]) -> tuple[str, bytes]:
        res = self._client.encrypt(KeyId=self._key_id, Plaintext=dek, EncryptionContext=context)
        return self.active_key_id, res["CiphertextBlob"]

    def unwrap(self, key_id: str, wrapped: bytes, context: dict[str, str]) -> bytes:
        try:
            res = self._client.decrypt(
                CiphertextBlob=wrapped, EncryptionContext=context, KeyId=key_id.removeprefix("kms:")
            )
        except Exception as exc:  # botocore raises service-specific ClientErrors
            raise DecryptionError("KMS decrypt failed") from exc
        return res["Plaintext"]


class EnvelopeCipher:
    def __init__(self, provider: KeyProvider) -> None:
        self.provider = provider

    @staticmethod
    def context(purpose: str, user_id: Any, record_id: Any) -> dict[str, str]:
        return {"purpose": purpose, "user_id": str(user_id), "record_id": str(record_id)}

    def seal(self, plaintext: bytes, context: dict[str, str]) -> SealedBox:
        dek = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = nonce + AESGCM(dek).encrypt(nonce, plaintext, _aad(context))
        key_id, wrapped = self.provider.wrap(dek, context)
        return SealedBox(key_id=key_id, wrapped_key=wrapped, ciphertext=ciphertext)

    def open(self, box: SealedBox, context: dict[str, str]) -> bytes:
        dek = self.provider.unwrap(box.key_id, box.wrapped_key, context)
        try:
            return AESGCM(dek).decrypt(box.ciphertext[:NONCE_BYTES], box.ciphertext[NONCE_BYTES:], _aad(context))
        except InvalidTag as exc:
            raise DecryptionError("Ciphertext authentication failed") from exc

    def seal_json(self, payload: dict[str, Any], context: dict[str, str]) -> SealedBox:
        return self.seal(json.dumps(payload, separators=(",", ":")).encode(), context)

    def open_json(self, box: SealedBox, context: dict[str, str]) -> dict[str, Any]:
        return json.loads(self.open(box, context))

    def needs_rewrap(self, box: SealedBox) -> bool:
        return box.key_id != self.provider.active_key_id

    def rewrap(self, box: SealedBox, context: dict[str, str]) -> SealedBox:
        """Re-wrap the DEK under the active KEK. The payload ciphertext is unchanged."""
        dek = self.provider.unwrap(box.key_id, box.wrapped_key, context)
        key_id, wrapped = self.provider.wrap(dek, context)
        return SealedBox(key_id=key_id, wrapped_key=wrapped, ciphertext=box.ciphertext)


def build_cipher(settings: Settings) -> EnvelopeCipher | None:
    if settings.key_provider == "aws_kms":
        if not settings.aws_kms_key_id:
            return None
        return EnvelopeCipher(AwsKmsKeyProvider(settings.aws_kms_key_id, settings.aws_region))
    if not settings.vault_master_keys:
        return None
    return EnvelopeCipher(
        LocalKeyring.from_config(settings.vault_master_keys.get_secret_value(), settings.vault_active_key_id)
    )
