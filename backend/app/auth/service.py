"""Users and sessions. Tokens are random 256-bit values; only their SHA-256 is stored."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import hmac
import secrets
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .passwords import hash_password, needs_rehash, verify_password

ROLES = ('reader', 'reviewer', 'admin')
CAPABILITIES = {
    'reader': ['library:read', 'own:data'],
    'reviewer': ['library:read', 'own:data', 'library:review'],
    'admin': ['library:read', 'own:data', 'library:review', 'library:manage', 'system:admin'],
}


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    email: str
    role: str
    session_id: uuid.UUID
    csrf_hash: str

    @property
    def capabilities(self) -> list[str]:
        return CAPABILITIES[self.role]

    def has_role(self, role: str) -> bool:
        return ROLES.index(self.role) >= ROLES.index(role)


@dataclass(frozen=True)
class NewSession:
    token: str
    csrf_token: str
    principal: Principal


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def csrf_matches(principal: Principal, presented: str | None) -> bool:
    return bool(presented) and hmac.compare_digest(token_hash(presented), principal.csrf_hash)


def authenticate(conn: Connection, email: str, password: str) -> dict | None:
    """Return the enabled user for valid credentials; same work when the email is unknown."""
    user = conn.execute(text('SELECT id, email, role, password_hash, enabled FROM users'
                             ' WHERE email = :email'), {'email': email}).mappings().first()
    valid = verify_password(user['password_hash'] if user else None, password)
    if not (valid and user['enabled']):
        return None
    if needs_rehash(user['password_hash']):
        conn.execute(text('UPDATE users SET password_hash = :h WHERE id = :id'),
                     {'h': hash_password(password), 'id': user['id']})
    return dict(user)


def create_session(conn: Connection, user: dict, ttl: timedelta) -> NewSession:
    token, csrf_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    csrf_hash = token_hash(csrf_token)
    session_id = conn.execute(text(
        'INSERT INTO sessions (user_id, token_hash, csrf_hash, expires_at)'
        ' VALUES (:user_id, :token_hash, :csrf_hash, now() + :ttl) RETURNING id'),
        {'user_id': user['id'], 'token_hash': token_hash(token), 'csrf_hash': csrf_hash,
         'ttl': ttl}).scalar_one()
    principal = Principal(user['id'], user['email'], user['role'], session_id, csrf_hash)
    return NewSession(token, csrf_token, principal)


def principal_for(conn: Connection, token: str) -> Principal | None:
    row = conn.execute(text(
        'SELECT s.id AS session_id, s.csrf_hash, u.id AS user_id, u.email, u.role'
        ' FROM sessions s JOIN users u ON u.id = s.user_id'
        ' WHERE s.token_hash = :h AND s.revoked_at IS NULL AND s.expires_at > now()'
        ' AND u.enabled'), {'h': token_hash(token)}).mappings().first()
    if row is None:
        return None
    return Principal(row['user_id'], row['email'], row['role'], row['session_id'],
                     row['csrf_hash'])


def revoke_session(conn: Connection, session_id: uuid.UUID) -> None:
    conn.execute(text('UPDATE sessions SET revoked_at = now()'
                      ' WHERE id = :id AND revoked_at IS NULL'), {'id': session_id})


def revoke_user_sessions(conn: Connection, user_id: uuid.UUID) -> None:
    conn.execute(text('UPDATE sessions SET revoked_at = now()'
                      ' WHERE user_id = :id AND revoked_at IS NULL'), {'id': user_id})


USER_COLUMNS = 'id, email, role, enabled, locale, created_at, updated_at'


def create_user(conn: Connection, email: str, password: str, role: str) -> dict:
    return dict(conn.execute(text(
        'INSERT INTO users (email, password_hash, role) VALUES (:email, :hash, :role)'
        f' RETURNING {USER_COLUMNS}'),
        {'email': email, 'hash': hash_password(password), 'role': role}).mappings().one())


def list_users(conn: Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(text(
        f'SELECT {USER_COLUMNS} FROM users ORDER BY created_at, id')).mappings()]


def update_user(conn: Connection, user_id: uuid.UUID, changes: dict) -> dict | None:
    allowed = {k: v for k, v in changes.items() if k in ('role', 'enabled') and v is not None}
    if not allowed:
        row = conn.execute(text(f'SELECT {USER_COLUMNS} FROM users WHERE id = :id'),
                           {'id': user_id}).mappings().first()
        return dict(row) if row else None
    assignments = ', '.join(f'{k} = :{k}' for k in allowed)
    row = conn.execute(text(f'UPDATE users SET {assignments} WHERE id = :id'
                            f' RETURNING {USER_COLUMNS}'),
                       {**allowed, 'id': user_id}).mappings().first()
    if row is not None and allowed.get('enabled') is False:
        revoke_user_sessions(conn, user_id)
    return dict(row) if row else None
