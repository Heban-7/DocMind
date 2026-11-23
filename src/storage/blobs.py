"""Blob storage behind a small interface.

Keys are ``<tenant_id>/documents/<document_id>/<name>``, so one tenant's
files never share a folder with another's. The local implementation keeps
them under ``DOCMIND_STORAGE_DIR`` (default ``.refinery/storage``); an object
store (S3 or Oracle Object Storage) can implement the same four methods later.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Protocol

from src.config import REFINERY_DIR

_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*$")


def document_source_key(tenant_id: str, document_id: str) -> str:
    return f"{tenant_id}/documents/{document_id}/source.pdf"


def document_model_key(tenant_id: str, document_id: str) -> str:
    return f"{tenant_id}/documents/{document_id}/model.json"


class BlobStore(Protocol):
    def put_file(self, key: str, source: Path) -> None: ...

    def put_bytes(self, key: str, data: bytes) -> None: ...

    def local_path(self, key: str) -> Path: ...

    def delete_prefix(self, prefix: str) -> None: ...


class LocalBlobStore:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root or os.getenv("DOCMIND_STORAGE_DIR") or (REFINERY_DIR / "storage")).resolve()

    def _path(self, key: str) -> Path:
        if not _KEY.match(key) or ".." in key.split("/"):
            raise ValueError(f"invalid storage key {key!r}")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError(f"invalid storage key {key!r}")
        return path

    def put_file(self, key: str, source: Path) -> None:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        shutil.copyfile(source, tmp)
        os.replace(tmp, dest)

    def put_bytes(self, key: str, data: bytes) -> None:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, dest)

    def local_path(self, key: str) -> Path:
        """Path of a stored file on this machine; FileNotFoundError if absent."""
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path

    def delete_prefix(self, prefix: str) -> None:
        path = self._path(prefix.rstrip("/"))
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def get_blob_store() -> BlobStore:
    return LocalBlobStore()
