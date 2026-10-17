"""Argon2id password hashing (docs/12)."""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_LENGTH = 12
MAX_LENGTH = 1024  # bound hashing work per request

_hasher = PasswordHasher()  # argon2id with the library's current recommended parameters
# Verified when the email is unknown so response time does not reveal accounts.
_DUMMY_HASH = _hasher.hash('timing-equaliser-not-a-real-password')


def validate_new_password(password: str) -> None:
    if not MIN_LENGTH <= len(password) <= MAX_LENGTH:
        raise ValueError(f'password must be {MIN_LENGTH}-{MAX_LENGTH} characters')


def hash_password(password: str) -> str:
    validate_new_password(password)
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    if len(password) > MAX_LENGTH:
        return False
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)
