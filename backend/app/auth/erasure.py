"""Erasure of one person's private data (docs/12 · Deletion; T049).

The work is done by ``bazi_erase_owner`` (M015) so that an admin, or a restore re-applying
the deletion ledger, can reach rows that row-level security hides from them. Callers
confirm with the account's email; a person erasing their own data also gives their
password. Only counts are returned and audited, never content.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..core.errors import AppError
from .passwords import verify_password


def _subject(conn: Connection, user_id: uuid.UUID) -> dict:
    row = conn.execute(text('SELECT id, email, role, enabled, password_hash FROM users'
                            ' WHERE id = :i FOR UPDATE'), {'i': user_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'User not found')
    return dict(row)


def erase(conn: Connection, actor_id: uuid.UUID, subject_id: uuid.UUID, confirm: str,
          delete_account: bool, password: str | None = None, request_id: str = '') -> dict:
    subject = _subject(conn, subject_id)
    if confirm.strip().lower() != subject['email'].lower():
        raise AppError(422, 'CONFIRMATION_MISMATCH', 'Type the account email to confirm',
                       field_errors=[{'path': 'body.confirm', 'message': 'must be the email'}])
    if password is not None and not verify_password(subject['password_hash'], password):
        raise AppError(403, 'PASSWORD_INCORRECT', 'The password is not correct',
                       field_errors=[{'path': 'body.password', 'message': 'incorrect'}])
    if delete_account and subject['role'] == 'admin' and subject['enabled'] and not conn.execute(
            text("SELECT 1 FROM users WHERE role = 'admin' AND enabled AND id <> :i LIMIT 1"),
            {'i': subject_id}).first():
        raise AppError(409, 'LAST_ADMIN', 'The last active admin cannot delete the account')
    counts = conn.execute(text('SELECT bazi_erase_owner(:s, :a, :actor)'),
                          {'s': subject_id, 'a': delete_account, 'actor': actor_id}).scalar_one()
    conn.execute(text(
        "INSERT INTO audit_logs (actor_id, action, target_kind, target_id, trace_id,"
        " redacted_diff, outcome) VALUES (:a, :action, 'user', :t, :tr, CAST(:d AS jsonb),"
        " 'success')"),
        {'a': actor_id, 'action': 'user.erase_account' if delete_account else 'user.erase_data',
         't': subject_id, 'tr': request_id, 'd': json.dumps({'counts': counts})})
    return {'user_id': str(subject_id), 'account_deleted': delete_account, 'counts': counts}
