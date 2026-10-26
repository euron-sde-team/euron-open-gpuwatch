"""Object storage for report exports: local disk, or S3 (Floci locally). Rows keep only
the object key."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Protocol


class ObjectNotFoundError(Exception):
    """The object does not exist (never written, or expired by the bucket lifecycle)."""


class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError("object key escapes the storage root")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(key) from exc

    async def delete(self, key: str) -> None:
        path = self._path(key)
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(key) from exc


class S3Storage:
    def __init__(self, client: Any, bucket: str) -> None:
        self._s3 = client
        self._bucket = bucket

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._s3.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="aws:kms",
        )

    async def get(self, key: str) -> bytes:
        try:
            resp = await asyncio.to_thread(self._s3.get_object, Bucket=self._bucket, Key=key)
        except self._s3.exceptions.NoSuchKey as exc:
            raise ObjectNotFoundError(key) from exc
        return bytes(resp["Body"].read())

    async def delete(self, key: str) -> None:
        # S3 deletes are idempotent: a missing key is not an error.
        await asyncio.to_thread(self._s3.delete_object, Bucket=self._bucket, Key=key)
