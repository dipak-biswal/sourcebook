"""File storage for uploaded documents.

Two backends behind one interface:
- LocalStorage: files under settings.upload_dir (dev / single machine)
- S3Storage: any S3-compatible object store (Cloudflare R2, B2, S3, ...)

Selection is env-driven: setting S3_ENDPOINT_URL switches to S3Storage.
All document uploads (Documents page, Add workspace modal, etc.) go through
``get_storage().save`` — so with R2 env vars set, every user upload lands in R2.

Parsers need a real filesystem path, so `local_path` is a context manager —
LocalStorage yields the stored file directly; S3Storage downloads to a
temp file (suffix preserved for parser dispatch) and cleans it up.
"""

from __future__ import annotations

import logging
import tempfile
from contextlib import AbstractContextManager, contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Protocol

from app.config import settings

logger = logging.getLogger(__name__)


class Storage(Protocol):
    def save(
        self, key: str, data: bytes, *, content_type: str | None = None
    ) -> None: ...

    def delete(self, key: str) -> None: ...

    def local_path(self, key: str) -> AbstractContextManager[Path]: ...

    @property
    def backend_name(self) -> str: ...


class LocalStorage:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or settings.upload_dir)

    @property
    def backend_name(self) -> str:
        return "local"

    def _path(self, key: str) -> Path:
        return self.root / key

    def save(
        self, key: str, data: bytes, *, content_type: str | None = None
    ) -> None:
        del content_type  # unused for local files
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()

    @contextmanager
    def local_path(self, key: str) -> Iterator[Path]:
        yield self._path(key)


class S3Storage:
    """S3-compatible store — Cloudflare R2, Backblaze B2, AWS S3, MinIO, etc."""

    def __init__(self, client=None, bucket: str | None = None):
        if client is None:
            import boto3
            from botocore.config import Config

            # R2 is S3-compatible; path-style + auto region works well.
            client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                region_name="auto",
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},
                ),
            )
        self.client = client
        self.bucket = bucket or settings.s3_bucket

    @property
    def backend_name(self) -> str:
        return "s3/r2"

    def save(
        self, key: str, data: bytes, *, content_type: str | None = None
    ) -> None:
        extra: dict = {"Bucket": self.bucket, "Key": key, "Body": data}
        if content_type:
            extra["ContentType"] = content_type
        self.client.put_object(**extra)

    def delete(self, key: str) -> None:
        # S3 delete of a missing key is a no-op, matching LocalStorage
        self.client.delete_object(Bucket=self.bucket, Key=key)

    @contextmanager
    def local_path(self, key: str) -> Iterator[Path]:
        suffix = Path(key).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
            self.client.download_fileobj(self.bucket, key, tmp)
            tmp.flush()
            yield Path(tmp.name)


def _s3_configured() -> bool:
    return bool(
        (settings.s3_endpoint_url or "").strip()
        and (settings.s3_bucket or "").strip()
        and (settings.s3_access_key_id or "").strip()
        and (settings.s3_secret_access_key or "").strip()
    )


def _s3_partially_configured() -> bool:
    flags = [
        bool((settings.s3_endpoint_url or "").strip()),
        bool((settings.s3_bucket or "").strip()),
        bool((settings.s3_access_key_id or "").strip()),
        bool((settings.s3_secret_access_key or "").strip()),
    ]
    return any(flags) and not all(flags)


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    if _s3_partially_configured():
        raise RuntimeError(
            "Object storage is partially configured. Set all of: "
            "S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY "
            "(Cloudflare R2 S3 API credentials)."
        )
    if _s3_configured():
        logger.info(
            "storage_backend=s3/r2 endpoint=%s bucket=%s",
            settings.s3_endpoint_url,
            settings.s3_bucket,
        )
        return S3Storage()
    logger.info(
        "storage_backend=local path=%s (set S3_* for Cloudflare R2)",
        settings.upload_dir,
    )
    return LocalStorage()
