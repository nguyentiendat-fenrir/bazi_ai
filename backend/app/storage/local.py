"""Filesystem ObjectStore: the default local volume (ADR-03)."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import BinaryIO, Iterator
import uuid

from .base import (CHUNK, ChecksumMismatch, HashingReader, InvalidKey, ObjectNotFound, ObjectStat,
                   StoredObject, object_key, validate_key)


class LocalObjectStore:
    backend = 'local'

    def __init__(self, root: str | Path, max_bytes: int | None = None):
        self.root = Path(root).resolve()
        self.max_bytes = max_bytes  # directories are created on first write, not at import

    def _path(self, key: str) -> Path:
        validate_key(key)
        path = self.root / key
        # Defence in depth beyond the key pattern (which already fixes the layout
        # root/<namespace>/<xx>/<sha>): neither directory may be a link that leads
        # elsewhere. Checked without Path.resolve(), whose Windows final-path lookup
        # races with concurrent writers creating the same directories.
        for directory in (path.parent.parent, path.parent):
            if directory.is_symlink() or os.path.isjunction(directory):
                raise InvalidKey('key escapes the storage root')
        return path

    def put_if_absent(self, stream: BinaryIO, expected_sha256: str | None = None,
                      namespace: str = 'objects') -> StoredObject:
        (self.root / 'staging').mkdir(parents=True, exist_ok=True)
        staging = self.root / 'staging' / uuid.uuid4().hex
        reader = HashingReader(stream, self.max_bytes)
        try:
            with open(staging, 'xb') as out:
                while chunk := reader.read(CHUNK):
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            if expected_sha256 and reader.sha256 != expected_sha256:
                raise ChecksumMismatch('content does not match the expected SHA-256')
            key = object_key(reader.sha256, namespace)
            final = self._path(key)
            if final.exists():
                return StoredObject(key, reader.sha256, reader.size, created=False)
            final.parent.mkdir(parents=True, exist_ok=True)
            # Same filesystem: rename is atomic, readers see all bytes or nothing.
            try:
                os.replace(staging, final)
            except PermissionError:
                # Windows refuses to replace a file another writer is placing right now;
                # identical bytes are already there, so this writer simply lost the race.
                if final.is_file() and final.stat().st_size == reader.size:
                    return StoredObject(key, reader.sha256, reader.size, created=False)
                raise
            return StoredObject(key, reader.sha256, reader.size, created=True)
        finally:
            staging.unlink(missing_ok=True)

    def get_stream(self, key: str, start: int | None = None,
                   end: int | None = None) -> Iterator[bytes]:
        path = self._path(key)
        if not path.is_file():
            raise ObjectNotFound(key)
        handle = open(path, 'rb')

        def chunks() -> Iterator[bytes]:
            with handle:
                position = start or 0
                handle.seek(position)
                while end is None or position < end:
                    want = CHUNK if end is None else min(CHUNK, end - position)
                    data = handle.read(want)
                    if not data:
                        return
                    position += len(data)
                    yield data
        return chunks()

    def stat(self, key: str) -> ObjectStat | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return ObjectStat(key, path.stat().st_size, key.rsplit('/', 1)[1])

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def list_manifest(self, namespace: str = 'objects') -> Iterator[ObjectStat]:
        base = self.root / namespace
        if not base.is_dir():
            return
        for path in sorted(base.glob('*/*')):
            key = path.relative_to(self.root).as_posix()
            try:
                validate_key(key)
            except InvalidKey:
                continue  # stray files are not objects
            yield ObjectStat(key, path.stat().st_size, path.name)

    def purge_staging(self) -> int:
        """Remove leftovers of interrupted writes; only call when no writer is active."""
        removed = 0
        if not (self.root / 'staging').is_dir():
            return 0
        for path in (self.root / 'staging').iterdir():
            if path.is_file():
                path.unlink()
                removed += 1
            elif path.is_dir():
                shutil.rmtree(path)
                removed += 1
        return removed
