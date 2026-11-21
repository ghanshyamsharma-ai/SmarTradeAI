"""Cloud/object storage adapters: AWS S3, Azure Blob or local disk."""

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

from config.settings import settings
from core.logger import logger

LOCAL_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"


class LocalStorage:
    name = "local"

    async def init(self) -> None:
        LOCAL_DIR.mkdir(parents=True, exist_ok=True)

    async def put_json(self, key: str, payload: Any) -> str:
        target = LOCAL_DIR / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")
        return str(target)

    async def get_json(self, key: str) -> Optional[Any]:
        target = LOCAL_DIR / key
        if not target.exists():
            return None
        return json.loads(target.read_text(encoding="utf-8"))

    async def close(self) -> None:
        return None


class S3Storage:
    name = "aws_s3"

    def __init__(self) -> None:
        self._client: Any = None

    async def init(self) -> None:
        import boto3  # type: ignore

        self._client = boto3.client("s3", region_name=settings.AWS_REGION)

    async def put_json(self, key: str, payload: Any) -> str:
        body = json.dumps(payload, default=str).encode("utf-8")
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=settings.AWS_S3_BUCKET,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
        return f"s3://{settings.AWS_S3_BUCKET}/{key}"

    async def get_json(self, key: str) -> Optional[Any]:
        response = await __import__("asyncio").to_thread(
            self._client.get_object, Bucket=settings.AWS_S3_BUCKET, Key=key
        )
        return json.loads(response["Body"].read().decode("utf-8"))

    async def close(self) -> None:
        return None


class AzureBlobStorage:
    name = "azure_blob"

    def __init__(self) -> None:
        self._container: Any = None

    async def init(self) -> None:
        from azure.storage.blob.aio import BlobServiceClient  # type: ignore

        service = BlobServiceClient.from_connection_string(
            settings.AZURE_STORAGE_CONNECTION_STRING
        )
        self._container = service.get_container_client(settings.AZURE_CONTAINER)

    async def put_json(self, key: str, payload: Any) -> str:
        body = json.dumps(payload, default=str)
        await self._container.upload_blob(key, body, overwrite=True)
        return f"azure://{settings.AZURE_CONTAINER}/{key}"

    async def get_json(self, key: str) -> Optional[Any]:
        downloader = await self._container.download_blob(key)
        return json.loads((await downloader.readall()).decode("utf-8"))

    async def close(self) -> None:
        if self._container is not None:
            await self._container.close()


_storage: Any = None


async def get_storage() -> Any:
    global _storage
    if _storage is not None:
        return _storage
    mode = settings.CLOUD_STORAGE.strip().lower()
    try:
        if mode == "s3" and settings.AWS_S3_BUCKET:
            candidate = S3Storage()
            await candidate.init()
            _storage = candidate
        elif mode == "azure" and settings.AZURE_STORAGE_CONNECTION_STRING:
            candidate = AzureBlobStorage()
            await candidate.init()
            _storage = candidate
        else:
            raise RuntimeError("using local object storage")
    except Exception as exc:
        logger.warning(f"Cloud storage '{mode}' unavailable, using local disk: {exc}")
        _storage = LocalStorage()
        await _storage.init()
    return _storage


async def close_storage() -> None:
    global _storage
    if _storage is not None:
        await _storage.close()
        _storage = None


def storage_status() -> dict[str, Any]:
    return {
        "configured": settings.CLOUD_STORAGE,
        "backend": _storage.name if _storage else "not_initialised",
        "active": _storage is not None,
    }
