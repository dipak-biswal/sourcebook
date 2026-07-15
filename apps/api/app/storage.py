"""File storage for uploaded documents.

Two backends behind one interface:
- LocalStorage: files under settings.upload_dir (dev / single machine)
- S3Storage: any S3-compatible object store (R2, B2, S3, ...)

Selection is env-driven: setting S3_ENDPOINT_URL switches to S3Storage.
Parsers need a real filesystem path, so `local_path` is a context manager —
LocalStorage yields the stored file directly; S3Storage downloads to a
temp file (suffix preserved for parser dispatch) and cleans it up.
"""

from __future__ import annotations

import tempfile
from contextlib import AbstractContextManager, contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Protocol

from app.config import settings


class Storage(Protocol):
    def save(self, key: str, data: bytes) -> None: ...

    def delete(self, key: str) -> None: ...

    def local_path(self, key: str) -> AbstractContextManager[Path]: ...


class LocalStorage:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or settings.upload_dir)

    def _path(self, key: str) -> Path:
        return self.root / key

    def save(self, key: str, data: bytes) -> None:
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
    def __init__(self, client=None, bucket: str | None = None):
        if client is None:
            import boto3

            client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                region_name="auto",
            )
        self.client = client
        self.bucket = bucket or settings.s3_bucket

    def save(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)

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


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    if settings.s3_endpoint_url:
        return S3Storage()
    return LocalStorage()
