"""Field encryption for birth data (docs/12 · Secrets và dữ liệu cá nhân).

AES-256-GCM with a random 96-bit nonce per value; the key is derived with HKDF-SHA256
from ``FIELD_ENCRYPTION_KEY``. Associated data binds a ciphertext to its kind, owner and
row, so a value copied to another row or user does not decrypt. ``key_version`` is a
fingerprint of the derived key (never the key): a restore with another .env is detected
instead of producing garbage. Losing the key loses the data — keep it with the backups'
recovery material, not in them.
"""
from __future__ import annotations

import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

FORMAT = 1


class DecryptError(Exception):
    """Wrong key, tampered value or value of another row."""


class FieldCipher:
    def __init__(self, secret: str):
        if len(secret) < 16:
            raise ValueError('FIELD_ENCRYPTION_KEY is too short')
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b'bazi-field-encryption',
                   info=b'aes-256-gcm v1').derive(secret.encode('utf-8'))
        self._aead = AESGCM(key)
        self.key_version = 'v1:' + hashlib.sha256(key).hexdigest()[:12]

    @staticmethod
    def context(kind: str, owner_id, row_id) -> bytes:
        return f'{kind}:{owner_id}:{row_id}'.encode()

    def encrypt(self, plaintext: bytes, context: bytes) -> bytes:
        nonce = os.urandom(12)
        return bytes([FORMAT]) + nonce + self._aead.encrypt(nonce, plaintext, context)

    def decrypt(self, value: bytes, context: bytes) -> bytes:
        value = bytes(value)
        if not value or value[0] != FORMAT:
            raise DecryptError('unknown ciphertext format')
        try:
            return self._aead.decrypt(value[1:13], value[13:], context)
        except InvalidTag:
            raise DecryptError('cannot decrypt: other key, other row or tampered') from None
