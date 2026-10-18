"""A person's rating of an answer or a rule analysis of their own (M017).

One row per person and target; rating again replaces it. Row-level security keeps it
private and the DB trigger checks the target belongs to the person. Only completed
assistant messages and analyses with a result can be rated.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..core.errors import AppError

CATEGORIES = ('wrong_source', 'missing_source', 'wrong_school', 'calculation', 'too_certain',
              'unclear', 'other')


def _dto(row) -> dict:
    return {'rating': row.rating, 'categories': list(row.categories), 'comment': row.comment,
            'updated_at': row.updated_at}


def rate(conn: Connection, user_id: uuid.UUID, rating: int, categories: list[str],
         comment: str | None, message_id=None, analysis_id=None) -> dict:
    if message_id is not None:
        target = conn.execute(text("SELECT status = 'completed' AND role = 'assistant'"
                                   ' FROM messages WHERE id = :i'), {'i': message_id}).scalar()
        column, value = 'message_id', message_id
    else:
        target = conn.execute(text("SELECT answer IS NOT NULL FROM chart_analyses WHERE id = :i"),
                              {'i': analysis_id}).scalar()
        column, value = 'analysis_id', analysis_id
    if target is None:
        raise AppError(404, 'NOT_FOUND', 'Nothing to rate here')
    if not target:
        raise AppError(409, 'NOT_RATEABLE', 'Only finished answers and analyses can be rated')
    row = conn.execute(text(
        f'INSERT INTO feedback (user_id, {column}, rating, categories, comment)'
        ' VALUES (:u, :t, :r, CAST(:c AS jsonb), :m)'
        f' ON CONFLICT (user_id, {column}) WHERE {column} IS NOT NULL DO UPDATE SET'
        ' rating = EXCLUDED.rating, categories = EXCLUDED.categories, comment = EXCLUDED.comment'
        ' RETURNING rating, categories, comment, updated_at'),
        {'u': user_id, 't': value, 'r': rating, 'c': json.dumps(sorted(set(categories))),
         'm': comment}).one()
    return _dto(row)


def mine(conn: Connection, message_ids: list) -> dict[str, dict]:
    if not message_ids:
        return {}
    return {str(r.message_id): _dto(r) for r in conn.execute(text(
        'SELECT message_id, rating, categories, comment, updated_at FROM feedback'
        ' WHERE message_id = ANY(CAST(:ids AS uuid[]))'), {'ids': [str(i) for i in message_ids]})}


def for_analysis(conn: Connection, analysis_id) -> dict | None:
    row = conn.execute(text('SELECT rating, categories, comment, updated_at FROM feedback'
                            ' WHERE analysis_id = :a'), {'a': analysis_id}).first()
    return _dto(row) if row else None
