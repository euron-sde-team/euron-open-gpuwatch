"""Sealing of provider credentials before they are stored.

``local`` uses AES-256-GCM with a key derived from LOCAL_MASTER_KEY. ``kms`` calls AWS KMS
(Floci locally) with an encryption context bound to the record, so a sealed value copied to
another provider row fails to open.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from typing import Any, Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_LOCAL_VERSION = b"\x01"


class KeySealer(Protocol):
    async def seal(self, plaintext: str, context: str) -> bytes: ...
    async def open(self, sealed: bytes, context: str) -> str: ...


class LocalSealer:
    def __init__(self, master_key: str) -> None:
        self._aes = AESGCM(hashlib.sha256(master_key.encode()).digest())

    async def seal(self, plaintext: str, context: str) -> bytes:
        nonce = os.urandom(12)
        return (
            _LOCAL_VERSION + nonce + self._aes.encrypt(nonce, plaintext.encode(), context.encode())
        )

    async def open(self, sealed: bytes, context: str) -> str:
        if sealed[:1] != _LOCAL_VERSION:
            raise ValueError("unknown sealed format")
        nonce, ct = sealed[1:13], sealed[13:]
        return self._aes.decrypt(nonce, ct, context.encode()).decode()


class KmsSealer:
    def __init__(self, kms_client: Any, key_id: str) -> None:
        self._kms = kms_client
        self._key_id = key_id

    async def seal(self, plaintext: str, context: str) -> bytes:
        resp = await asyncio.to_thread(
            self._kms.encrypt,
            KeyId=self._key_id,
            Plaintext=plaintext.encode(),
            EncryptionContext={"gpuwatch:record": context},
        )
        return bytes(resp["CiphertextBlob"])

    async def open(self, sealed: bytes, context: str) -> str:
        resp = await asyncio.to_thread(
            self._kms.decrypt,
            CiphertextBlob=sealed,
            EncryptionContext={"gpuwatch:record": context},
        )
        return bytes(resp["Plaintext"]).decode()
