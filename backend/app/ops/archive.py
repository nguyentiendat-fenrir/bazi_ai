"""Encrypted backup files (docs/12 · Backup nhất quán; T052).

Each file of a backup (the database dump and every blob) is encrypted on its own with
AES-256-GCM in fixed-size chunks, so a multi-gigabyte dump never sits in memory and a
restore can stream. Layout: ``BAZIENC1`` · chunk size (u32) · 8-byte random prefix, then
for each chunk its length (u32) and ciphertext+tag. The nonce is the prefix plus the
chunk counter; the associated data binds the file's path in the backup, the counter and
a last-chunk flag, so chunks cannot be reordered, moved to another file or cut off.

The key is derived per backup with HKDF-SHA256 from ``BACKUP_ENCRYPTION_KEY`` and a
random salt kept in the manifest; the manifest also keeps a key id (a second HKDF output)
so a restore can say "wrong key" before touching data. The secret itself is never
written anywhere.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import os
from pathlib import Path
import struct
from typing import BinaryIO, Iterator

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEME = 'aes-256-gcm-chunked-1'
MAGIC = b'BAZIENC1'
CHUNK = 4 * 1024 * 1024
MIN_SECRET = 32


class ArchiveError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _hkdf(secret: str, salt: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(
        secret.encode('utf-8'))


class _ChunkStream(io.RawIOBase):
    def __init__(self, chunks: Iterator[bytes], handle: BinaryIO):
        self._chunks, self._left, self._handle = chunks, b'', handle

    def close(self) -> None:
        self._handle.close()
        super().close()

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        while not self._left:
            try:
                self._left = next(self._chunks)
            except StopIteration:
                return 0
        n = min(len(buffer), len(self._left))
        buffer[:n], self._left = self._left[:n], self._left[n:]
        return n


class BackupKey:
    """The per-backup key; built from the secret and the backup's salt."""

    def __init__(self, secret: str, salt: bytes):
        if len(secret) < MIN_SECRET:
            raise ArchiveError('KEY_TOO_SHORT', f'BACKUP_ENCRYPTION_KEY needs at least'
                               f' {MIN_SECRET} characters')
        self.salt = salt
        self._aead = AESGCM(_hkdf(secret, salt, b'bazi-backup-v1 data'))
        self.key_id = _hkdf(secret, salt, b'bazi-backup-v1 key-id').hex()[:32]

    @classmethod
    def new(cls, secret: str) -> 'BackupKey':
        return cls(secret, os.urandom(16))

    def describe(self) -> dict:
        return {'scheme': SCHEME, 'salt': self.salt.hex(), 'key_id': self.key_id,
                'chunk_bytes': CHUNK, 'key_ref': 'BACKUP_ENCRYPTION_KEY'}

    @classmethod
    def for_manifest(cls, secret: str | None, encryption: dict) -> 'BackupKey':
        if encryption.get('scheme') != SCHEME:
            raise ArchiveError('ENCRYPTION_UNSUPPORTED', f"unknown scheme {encryption.get('scheme')}")
        if not secret:
            raise ArchiveError('KEY_MISSING', 'this backup is encrypted; set BACKUP_ENCRYPTION_KEY')
        key = cls(secret, bytes.fromhex(encryption['salt']))
        if not hmac.compare_digest(key.key_id, encryption['key_id']):
            raise ArchiveError('WRONG_KEY', 'BACKUP_ENCRYPTION_KEY is not the key of this backup')
        return key

    def _aad(self, path: str, index: int, last: bool) -> bytes:
        return f'{path}\x00{index}\x00{int(last)}'.encode('utf-8')

    def encrypt(self, source: BinaryIO, target: BinaryIO, path: str) -> str:
        """Encrypt ``source`` into ``target``; returns the plaintext sha256."""
        prefix = os.urandom(8)
        target.write(MAGIC + struct.pack('>I', CHUNK) + prefix)
        digest = hashlib.sha256()
        index, current = 0, source.read(CHUNK)
        while True:
            following = source.read(CHUNK) if current else b''
            last = not following
            digest.update(current)
            sealed = self._aead.encrypt(prefix + struct.pack('>I', index), current,
                                        self._aad(path, index, last))
            target.write(struct.pack('>I', len(sealed)) + sealed)
            if last:
                return digest.hexdigest()
            index, current = index + 1, following

    def decrypt(self, source: BinaryIO, path: str) -> Iterator[bytes]:
        """Plaintext chunks; raises ArchiveError on any tampering or truncation."""
        head = source.read(len(MAGIC) + 12)
        if len(head) != len(MAGIC) + 12 or not head.startswith(MAGIC):
            raise ArchiveError('ARCHIVE_CORRUPT', f'{path} is not an encrypted backup file')
        (size,), prefix = struct.unpack('>I', head[8:12]), head[12:20]
        index, seen_last = 0, False
        while True:
            length = source.read(4)
            if not length:
                break
            if seen_last:
                raise ArchiveError('ARCHIVE_CORRUPT', f'{path} has data after its last chunk')
            (n,) = struct.unpack('>I', length)
            if n > size + 16:
                raise ArchiveError('ARCHIVE_CORRUPT', f'{path} has an oversized chunk')
            sealed = source.read(n)
            for last in (True, False):
                try:
                    plain = self._aead.decrypt(prefix + struct.pack('>I', index), sealed,
                                               self._aad(path, index, last))
                except InvalidTag:
                    continue
                seen_last = last
                yield plain
                break
            else:
                raise ArchiveError('ARCHIVE_CORRUPT', f'{path} failed authentication at chunk'
                                   f' {index}')
            index += 1
        if not seen_last:
            raise ArchiveError('ARCHIVE_CORRUPT', f'{path} is truncated')

    def reader(self, sealed: Path, path: str) -> io.BufferedReader:
        """A file-like plaintext view of ``sealed``, decrypted as it is read."""
        handle = open(sealed, 'rb')
        return io.BufferedReader(_ChunkStream(self.decrypt(handle, path), handle), CHUNK)

    def encrypt_file(self, plain: Path, sealed: Path, path: str) -> str:
        with open(plain, 'rb') as source, open(sealed, 'wb') as target:
            digest = self.encrypt(source, target, path)
            target.flush()
            os.fsync(target.fileno())
        return digest

    def decrypt_file(self, sealed: Path, plain: Path, path: str) -> str:
        digest = hashlib.sha256()
        with open(sealed, 'rb') as source, open(plain, 'wb') as target:
            for chunk in self.decrypt(source, path):
                digest.update(chunk)
                target.write(chunk)
        return digest.hexdigest()

    def plaintext_sha256(self, sealed: Path, path: str) -> str:
        digest = hashlib.sha256()
        with open(sealed, 'rb') as source:
            for chunk in self.decrypt(source, path):
                digest.update(chunk)
        return digest.hexdigest()
