"""ObjectStore contract (docs/03 · Storage).

Objects are content-addressed: the server derives the key from the SHA-256 of
the bytes, never from a client filename. Writes stream through a staging key
and are promoted atomically, so readers never see partial objects.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import BinaryIO, Iterator, Protocol

CHUNK = 1024 * 1024
# Keys are generated server-side; anything else is rejected before touching storage.
KEY_PATTERN = re.compile(r'^(objects|manifests|backups)/[0-9a-f]{2}/[0-9a-f]{64}$')


class StorageError(Exception):
    pass


class InvalidKey(StorageError):
    pass


class ChecksumMismatch(StorageError):
    pass


class ObjectNotFound(StorageError):
    pass


@dataclass(frozen=True)
class StoredObject:
    key: str
    sha256: str
    size_bytes: int
    created: bool  # False when identical bytes already existed


@dataclass(frozen=True)
class ObjectStat:
    key: str
    size_bytes: int
    sha256: str | None


def object_key(sha256: str, namespace: str = 'objects') -> str:
    key = f'{namespace}/{sha256[:2]}/{sha256}'
    validate_key(key)
    return key


def validate_key(key: str) -> str:
    if not KEY_PATTERN.fullmatch(key):
        raise InvalidKey('object keys are server-generated content addresses')
    return key


class HashingReader:
    """Wraps a stream, hashing and counting bytes as they are read."""

    def __init__(self, stream: BinaryIO, max_bytes: int | None = None):
        self.stream = stream
        self.max_bytes = max_bytes
        self.digest = hashlib.sha256()
        self.size = 0

    def read(self, size: int = -1) -> bytes:
        data = self.stream.read(size)
        self.size += len(data)
        if self.max_bytes is not None and self.size > self.max_bytes:
            raise StorageError(f'object exceeds the {self.max_bytes} byte limit')
        self.digest.update(data)
        return data

    @property
    def sha256(self) -> str:
        return self.digest.hexdigest()


class ObjectStore(Protocol):
    backend: str

    def put_if_absent(self, stream: BinaryIO, expected_sha256: str | None = None,
                      namespace: str = 'objects') -> StoredObject: ...

    def get_stream(self, key: str, start: int | None = None,
                   end: int | None = None) -> Iterator[bytes]:
        """Yield bytes of ``[start, end)``; both bounds optional."""

    def stat(self, key: str) -> ObjectStat | None: ...

    def delete(self, key: str) -> None: ...

    def list_manifest(self, namespace: str = 'objects') -> Iterator[ObjectStat]: ...


def copy_verified(source: ObjectStore, key: str, target: ObjectStore) -> StoredObject:
    """Copy between stores, re-hashing on the way; the address proves integrity."""
    expected = validate_key(key).rsplit('/', 1)[1]
    result = target.put_if_absent(_IterStream(source.get_stream(key)), expected_sha256=expected,
                                  namespace=key.split('/', 1)[0])
    return result


class _IterStream:
    def __init__(self, chunks: Iterator[bytes]):
        self.chunks = chunks
        self.buffer = b''

    def read(self, size: int = -1) -> bytes:
        while size < 0 or len(self.buffer) < size:
            chunk = next(self.chunks, None)
            if chunk is None:
                break
            self.buffer += chunk
        if size < 0:
            data, self.buffer = self.buffer, b''
        else:
            data, self.buffer = self.buffer[:size], self.buffer[size:]
        return data
