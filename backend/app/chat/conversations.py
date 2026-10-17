"""Conversations, messages and runs (docs/09 · Multi-turn memory, docs/10 · conversations).

* A conversation carries its context (mode, chart, schools, methods, books, as_of).
  Changing the chart or schools starts a new memory window: later runs do not see the
  turns before the change, so facts of the old chart never leak into the new one.
* Posting a message creates the user message, a pending assistant message and a queued
  run in one transaction; the run pins a snapshot of the context, the last six turns of
  the window, the active model profile and corpus release. One active run at a time.
* Deleting a conversation cancels its runs and wipes content, claims, citations and
  events; only minimal metadata stays (ids, timestamps, states).
"""
from __future__ import annotations

import base64
from datetime import datetime
import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..charts import service as charts
from ..core.errors import AppError
from ..reasoning.prompts import PROMPT_VERSION

MODES = ('research', 'chart_analysis', 'comparison')
ACTIVE_RUN = ('queued', 'running', 'waiting_provider')
HISTORY_TURNS = 6
MEMORY_KEYS = ('chart_id', 'school_ids')       # changing these starts a new memory window


def _cursor(stamp: datetime, row_id) -> str:
    return base64.urlsafe_b64encode(f'{stamp.isoformat()}|{row_id}'.encode()).decode()


def _after(cursor: str | None):
    if not cursor:
        return None
    try:
        stamp, row = base64.urlsafe_b64decode(cursor.encode()).decode().split('|')
        return datetime.fromisoformat(stamp), uuid.UUID(row)
    except (ValueError, UnicodeDecodeError):
        raise AppError(422, 'VALIDATION_ERROR', 'Invalid cursor') from None


def check_context(conn: Connection, context: dict) -> dict:
    """Owner/reference checks; returns the normalized context (ids as strings)."""
    clean = {'mode': context.get('mode', 'research'),
             'chart_id': str(context['chart_id']) if context.get('chart_id') else None,
             'school_ids': [str(s) for s in context.get('school_ids') or []],
             'method_ids': [str(m) for m in context.get('method_ids') or []],
             'book_ids': [str(b) for b in context.get('book_ids') or []],
             'as_of': context.get('as_of')}
    if clean['mode'] not in MODES:
        raise AppError(422, 'VALIDATION_ERROR', f"mode is one of {', '.join(MODES)}")
    if clean['chart_id']:
        charts.chart_facts(conn, clean['chart_id'])            # 404 unless it is the owner's
    for table, ids in (('schools', clean['school_ids']), ('methods', clean['method_ids'])):
        if ids and conn.execute(text(f'SELECT count(DISTINCT id) FROM {table}'
                                     ' WHERE id = ANY(CAST(:ids AS uuid[]))'),
                                {'ids': ids}).scalar_one() != len(set(ids)):
            raise AppError(422, 'VALIDATION_ERROR', f'unknown {table[:-1]} in context')
    return clean


CONVERSATION = ('SELECT c.id, c.title, c.starred, c.context, c.revision, c.created_at,'
                ' c.updated_at, (SELECT count(*) FROM messages m WHERE m.conversation_id = c.id)'
                ' AS messages_count FROM conversations c WHERE c.deleted_at IS NULL')


def _dto(row) -> dict:
    return {'id': str(row.id), 'title': row.title, 'starred': row.starred,
            'context': row.context, 'revision': row.revision,
            'messages_count': row.messages_count, 'created_at': row.created_at,
            'updated_at': row.updated_at}


def _row(conn: Connection, conversation_id, lock: bool = False):
    row = conn.execute(text(f'{CONVERSATION} AND c.id = :i{" FOR UPDATE OF c" if lock else ""}'),
                       {'i': conversation_id}).first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Conversation not found')   # also another owner's
    return row


def create_conversation(conn: Connection, principal: Principal, title: str,
                        context: dict) -> dict:
    clean = check_context(conn, context)
    conversation_id = conn.execute(text(
        'INSERT INTO conversations (owner_id, title, context) VALUES (:o, :t, CAST(:c AS jsonb))'
        ' RETURNING id'), {'o': principal.user_id, 't': title.strip(),
                           'c': json.dumps({**clean, 'memory_from_seq': 0})}).scalar_one()
    return _dto(_row(conn, conversation_id))


def list_conversations(conn: Connection, q: str | None, starred: bool | None, limit: int,
                       cursor: str | None) -> tuple[list[dict], str | None]:
    clauses, params = [], {'n': limit + 1}
    if q:
        # Owner-scoped by row-level security; matches titles and message text.
        clauses.append("(c.title ILIKE :like OR EXISTS (SELECT 1 FROM messages m WHERE"
                       " m.conversation_id = c.id AND to_tsvector('simple', m.content) @@"
                       " plainto_tsquery('simple', :q)))")
        params.update(q=q, like=f"%{q.replace('%', '').replace('_', '')}%")
    if starred is not None:
        clauses.append('c.starred = :starred')
        params['starred'] = starred
    after = _after(cursor)
    if after:
        clauses.append('(c.updated_at, c.id) < (:at, :id)')
        params.update(at=after[0], id=after[1])
    where = ''.join(f' AND {c}' for c in clauses)
    rows = conn.execute(text(f'{CONVERSATION}{where} ORDER BY c.updated_at DESC, c.id DESC'
                             ' LIMIT :n'), params).all()
    page = rows[:limit]
    return [_dto(r) for r in page], (_cursor(page[-1].updated_at, page[-1].id)
                                     if len(rows) > limit else None)


def messages(conn: Connection, conversation_id, after_seq: int, limit: int) -> list[dict]:
    _row(conn, conversation_id)
    return [{'id': str(m.id), 'seq': m.seq, 'role': m.role, 'content': m.content,
             'status': m.status, 'run_id': str(m.run_id) if m.run_id else None,
             'answer': m.structured_answer, 'created_at': m.created_at}
            for m in conn.execute(text(
                'SELECT id, seq, role, content, status, run_id, structured_answer, created_at'
                ' FROM messages WHERE conversation_id = :c AND seq > :s ORDER BY seq LIMIT :n'),
                {'c': conversation_id, 's': after_seq, 'n': limit}).all()]


def get_conversation(conn: Connection, conversation_id) -> dict:
    return _dto(_row(conn, conversation_id))


def update_conversation(conn: Connection, conversation_id, revision: int, title: str | None,
                        starred: bool | None, context: dict | None) -> dict:
    row = _row(conn, conversation_id, lock=True)
    if row.revision != revision:
        raise AppError(412, 'REVISION_MISMATCH', 'The conversation changed; reload and retry',
                       headers={'ETag': f'"{row.revision}"'})
    new_context = row.context
    if context is not None:
        clean = check_context(conn, context)
        last = conn.execute(text('SELECT coalesce(max(seq), 0) FROM messages'
                                 ' WHERE conversation_id = :c'), {'c': row.id}).scalar_one()
        changed = any(clean.get(k) != row.context.get(k) for k in MEMORY_KEYS)
        new_context = {**clean, 'memory_from_seq': last if changed
                       else row.context.get('memory_from_seq', 0)}
    conn.execute(text('UPDATE conversations SET title = :t, starred = :s, context = CAST(:c AS'
                      ' jsonb), revision = revision + 1 WHERE id = :i'),
                 {'t': (title if title is not None else row.title).strip(),
                  's': row.starred if starred is None else starred,
                  'c': json.dumps(new_context), 'i': row.id})
    return _dto(_row(conn, conversation_id))


def delete_conversation(conn: Connection, conversation_id) -> dict:
    row = _row(conn, conversation_id, lock=True)
    cancelled = conn.execute(text(
        "UPDATE chat_runs SET state = 'cancelled' WHERE conversation_id = :c"
        " AND state = ANY(:active)"), {'c': row.id, 'active': list(ACTIVE_RUN)}).rowcount
    conn.execute(text('DELETE FROM citations WHERE claim_id IN (SELECT cl.id FROM claims cl'
                      ' JOIN messages m ON m.id = cl.message_id WHERE m.conversation_id = :c)'),
                 {'c': row.id})
    conn.execute(text('DELETE FROM claims WHERE message_id IN (SELECT id FROM messages'
                      ' WHERE conversation_id = :c)'), {'c': row.id})
    conn.execute(text('DELETE FROM run_events WHERE run_id IN (SELECT id FROM chat_runs'
                      ' WHERE conversation_id = :c)'), {'c': row.id})
    conn.execute(text("UPDATE messages SET content = '', structured_answer = NULL,"
                      " status = CASE WHEN status IN ('pending', 'streaming') THEN 'cancelled'"
                      ' ELSE status END WHERE conversation_id = :c'), {'c': row.id})
    conn.execute(text("UPDATE conversations SET title = '', context = '{}', deleted_at = now()"
                      ' WHERE id = :c'), {'c': row.id})
    return {'conversation_id': str(row.id), 'runs_cancelled': cancelled}


def post_message(conn: Connection, principal: Principal, conversation_id, content: str,
                 mode: str | None) -> dict:
    row = _row(conn, conversation_id, lock=True)
    if conn.execute(text('SELECT 1 FROM chat_runs WHERE conversation_id = :c'
                         ' AND state = ANY(:active)'),
                    {'c': row.id, 'active': list(ACTIVE_RUN)}).first():
        raise AppError(409, 'RUN_ACTIVE', 'Wait for the current answer or cancel it')
    context = dict(row.context)
    if mode:
        if mode not in MODES:
            raise AppError(422, 'VALIDATION_ERROR', f"mode is one of {', '.join(MODES)}")
        context['mode'] = mode
    if context['mode'] == 'chart_analysis' and not context.get('chart_id'):
        raise AppError(422, 'CHART_REQUIRED', 'choose a chart for chart analysis',
                       field_errors=[{'path': 'context.chart_id', 'message': 'required'}])
    if context['mode'] == 'comparison' and len(context.get('school_ids') or []) < 2:
        raise AppError(422, 'SCHOOLS_REQUIRED', 'choose at least two schools to compare',
                       field_errors=[{'path': 'context.school_ids', 'message': 'two or more'}])
    window = context.get('memory_from_seq', 0)
    history = [{'role': h.role, 'content': h.content} for h in reversed(conn.execute(text(
        "SELECT role, content FROM messages WHERE conversation_id = :c AND seq > :w"
        " AND status = 'completed' ORDER BY seq DESC LIMIT :n"),
        {'c': row.id, 'w': window, 'n': HISTORY_TURNS * 2}).all())]
    seq = conn.execute(text('SELECT coalesce(max(seq), 0) FROM messages WHERE conversation_id = :c'),
                       {'c': row.id}).scalar_one()
    user_id, assistant_id, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    conn.execute(text(
        "INSERT INTO messages (id, conversation_id, seq, role, content, status, run_id) VALUES"
        " (:u, :c, :s1, 'user', :content, 'completed', :r),"
        " (:a, :c, :s2, 'assistant', '', 'pending', :r)"),
        {'u': user_id, 'a': assistant_id, 'c': row.id, 's1': seq + 1, 's2': seq + 2,
         'content': content.strip(), 'r': run_id})
    profile = conn.execute(text("SELECT id FROM model_profiles WHERE kind = 'llm' AND enabled"
                                ' ORDER BY created_at DESC LIMIT 1')).scalar()
    release = conn.execute(text("SELECT release_id FROM active_corpus WHERE slot = 'default'")
                           ).scalar()
    snapshot = {**{k: context.get(k) for k in ('mode', 'chart_id', 'school_ids', 'method_ids',
                                               'book_ids', 'as_of')}, 'history': history}
    conn.execute(text(
        'INSERT INTO chat_runs (id, conversation_id, user_message_id, assistant_message_id,'
        ' owner_id, mode, context_snapshot, model_profile_id, corpus_release_id, prompt_version)'
        ' VALUES (:r, :c, :u, :a, :o, :m, CAST(:snap AS jsonb), :p, :rel, :v)'),
        {'r': run_id, 'c': row.id, 'u': user_id, 'a': assistant_id, 'o': principal.user_id,
         'm': context['mode'], 'snap': json.dumps(snapshot, ensure_ascii=False), 'p': profile,
         'rel': release, 'v': PROMPT_VERSION})
    title = row.title or content.strip()[:60]
    conn.execute(text('UPDATE conversations SET title = :t, updated_at = now() WHERE id = :c'),
                 {'t': title, 'c': row.id})
    return {'run': get_run(conn, run_id), 'user_message_id': str(user_id),
            'assistant_message_id': str(assistant_id)}


RUN = ('SELECT r.id, r.conversation_id, r.mode, r.state, r.error, r.assistant_message_id,'
       ' r.created_at, r.updated_at, m.structured_answer, m.status AS message_status'
       ' FROM chat_runs r JOIN messages m ON m.id = r.assistant_message_id')


def get_run(conn: Connection, run_id) -> dict:
    row = conn.execute(text(f'{RUN} WHERE r.id = :r'), {'r': run_id}).first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Run not found')
    return {'id': str(row.id), 'conversation_id': str(row.conversation_id), 'mode': row.mode,
            'state': row.state, 'error': row.error,
            'assistant_message_id': str(row.assistant_message_id),
            'answer': row.structured_answer, 'created_at': row.created_at,
            'updated_at': row.updated_at}


def cancel_run(conn: Connection, run_id) -> dict:
    row = conn.execute(text('SELECT id, state, assistant_message_id FROM chat_runs'
                            ' WHERE id = :r FOR UPDATE'), {'r': run_id}).first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Run not found')
    if row.state in ACTIVE_RUN:
        conn.execute(text("UPDATE chat_runs SET state = 'cancelled' WHERE id = :r"),
                     {'r': run_id})
        conn.execute(text("UPDATE messages SET status = 'cancelled' WHERE id = :m"
                          " AND status IN ('pending', 'streaming')"),
                     {'m': row.assistant_message_id})
    return get_run(conn, run_id)


def events(conn: Connection, run_id, after_seq: int, limit: int = 200) -> list[dict]:
    return [{'seq': e.seq, 'type': e.event_type, 'payload': e.payload}
            for e in conn.execute(text(
                'SELECT seq, event_type, payload FROM run_events WHERE run_id = :r AND seq > :s'
                ' ORDER BY seq LIMIT :n'), {'r': run_id, 's': after_seq, 'n': limit}).all()]
