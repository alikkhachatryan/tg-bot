import asyncio
from pathlib import Path
from typing import Protocol

import aioboto3  # type: ignore[import-untyped]

from app.core.config import Settings


class PrivateStorage(Protocol):
    async def put(self, key: str, data: bytes, media_type: str) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...


class LocalPrivateStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError("Invalid storage key")
        return path

    async def put(self, key: str, data: bytes, media_type: str) -> None:
        del media_type
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, missing_ok=True)


class S3PrivateStorage:
    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.s3_bucket or ""
        self._client_options = {
            "endpoint_url": settings.s3_endpoint,
            "aws_access_key_id": (
                settings.s3_access_key.get_secret_value() if settings.s3_access_key else None
            ),
            "aws_secret_access_key": (
                settings.s3_secret_key.get_secret_value() if settings.s3_secret_key else None
            ),
        }

    async def put(self, key: str, data: bytes, media_type: str) -> None:
        async with aioboto3.Session().client("s3", **self._client_options) as client:
            await client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=media_type,
                ServerSideEncryption="AES256",
            )

    async def get(self, key: str) -> bytes:
        async with aioboto3.Session().client("s3", **self._client_options) as client:
            response = await client.get_object(Bucket=self._bucket, Key=key)
            async with response["Body"] as body:
                return bytes(await body.read())

    async def delete(self, key: str) -> None:
        async with aioboto3.Session().client("s3", **self._client_options) as client:
            await client.delete_object(Bucket=self._bucket, Key=key)


def create_storage(settings: Settings) -> PrivateStorage:
    if settings.storage_driver == "s3":
        return S3PrivateStorage(settings)
    return LocalPrivateStorage(settings.local_storage_path)
