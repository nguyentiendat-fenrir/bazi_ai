"""Birth profiles and charts: encrypted birth input, immutable facts (docs/04, docs/12).

* A profile keeps a label and the latest BirthInput, encrypted with the field cipher
  under (kind, owner, row); a PATCH writes a new revision, charts made before keep their
  own encrypted input snapshot and facts.
* A chart stores ChartFacts as JSON (without the input snapshot, which is encrypted
  apart) and is never edited; the database recomputes ``facts_hash`` and refuses rows
  whose hash does not match. Rows are owner-scoped by row-level security.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..calc import policies as calc_policies, solar_terms
from ..calc.chart import POSITIONS, compute
from ..calc.timebase import BirthInput, CalcError
from ..core.crypto import DecryptError, FieldCipher
from ..core.errors import AppError

PROFILE, CHART_INPUT = 'birth_profile', 'chart_input'


def require_cipher(cipher: FieldCipher | None) -> FieldCipher:
    if cipher is None:
        raise AppError(503, 'ENCRYPTION_NOT_CONFIGURED', 'FIELD_ENCRYPTION_KEY is not configured;'
                       ' birth data cannot be stored')
    return cipher


def calc_error(exc: CalcError) -> AppError:
    path = f'body.{exc.field}' if exc.field else 'body'
    return AppError(422, exc.code, str(exc), field_errors=[{'path': path, 'message': str(exc)}])


def _decrypt(cipher: FieldCipher, blob, kind: str, owner, row_id) -> dict:
    try:
        return json.loads(cipher.decrypt(blob, FieldCipher.context(kind, owner, row_id)))
    except DecryptError:
        raise AppError(409, 'ENCRYPTION_KEY_MISMATCH', 'Stored birth data cannot be decrypted with'
                       ' the configured key (restored with another .env?)') from None


def _cursor(created_at: datetime, row_id) -> str:
    return base64.urlsafe_b64encode(f'{created_at.isoformat()}|{row_id}'.encode()).decode()


def _after(cursor: str | None) -> tuple | None:
    if not cursor:
        return None
    try:
        stamp, row = base64.urlsafe_b64decode(cursor.encode()).decode().split('|')
        return datetime.fromisoformat(stamp), uuid.UUID(row)
    except (ValueError, UnicodeDecodeError):
        raise AppError(422, 'VALIDATION_ERROR', 'Invalid cursor') from None


# ---- policies ---------------------------------------------------------------------------

def ensure_policy(conn: Connection, policy_id: str) -> uuid.UUID:
    """The DB row of a code policy (revision 1), created on first use, never drifting."""
    config = calc_policies.POLICIES[policy_id]
    payload = json.dumps(config, sort_keys=True)
    conn.execute(text(
        'INSERT INTO calculation_policies (key, revision, config, manifest_hash, state)'
        ' VALUES (:k, 1, CAST(:c AS jsonb), bazi_sha256_text(CAST(:c AS jsonb)::text), :s)'
        ' ON CONFLICT (key, revision) DO NOTHING'), {'k': policy_id, 'c': payload, 's': 'active'})
    row = conn.execute(text('SELECT id, config FROM calculation_policies WHERE key = :k'
                            ' AND revision = 1'), {'k': policy_id}).one()
    if row.config != config:
        # A changed config must ship under a new policy id (e.g. standard-v2).
        raise AppError(500, 'POLICY_DRIFT', f'stored policy {policy_id} differs from the code')
    return row.id


def policy_catalog() -> dict:
    return {'policies': [calc_policies.policy(p) | {'default': p == calc_policies.DEFAULT_POLICY}
                         for p in calc_policies.POLICIES],
            'calendars': ['gregorian', 'lunar_vn', 'lunar_cn'],
            'range': {'first_year': solar_terms.FIRST_YEAR, 'last_year': solar_terms.LAST_YEAR},
            'time_accuracy': ['minute', 'hour', 'unknown'],
            'max_uncertainty_minutes': 720}


# ---- profiles ---------------------------------------------------------------------------

PROFILE_SELECT = (
    'SELECT p.id, p.owner_id, p.label, p.revision, p.birth_input_encrypted, p.crypto_key_version,'
    ' p.created_at, p.updated_at,'
    ' (SELECT count(*) FROM bazi_charts c WHERE c.profile_id = p.id) AS charts_count'
    ' FROM birth_profiles p WHERE p.deleted_at IS NULL')


def _profile_dto(row, birth: dict | None = None) -> dict:
    dto = {'id': str(row.id), 'label': row.label, 'revision': row.revision,
           'charts_count': row.charts_count, 'created_at': row.created_at,
           'updated_at': row.updated_at}
    if birth is not None:
        dto['birth_input'] = birth
    return dto


def _check(birth: BirthInput) -> None:
    try:
        compute(birth)                       # refuse what no chart could be made from
    except CalcError as exc:
        raise calc_error(exc) from None


def create_profile(conn: Connection, principal: Principal, cipher: FieldCipher, label: str,
                   birth: BirthInput) -> dict:
    _check(birth)
    profile_id = uuid.uuid4()
    blob = cipher.encrypt(birth.model_dump_json().encode(),
                          FieldCipher.context(PROFILE, principal.user_id, profile_id))
    conn.execute(text(
        'INSERT INTO birth_profiles (id, owner_id, label, birth_input_encrypted,'
        ' crypto_key_version) VALUES (:id, :o, :l, :b, :v)'),
        {'id': profile_id, 'o': principal.user_id, 'l': label.strip(), 'b': blob,
         'v': cipher.key_version})
    return get_profile(conn, principal, cipher, profile_id)


def list_profiles(conn: Connection, limit: int, cursor: str | None) -> tuple[list, str | None]:
    after = _after(cursor)
    clause = ' AND (p.created_at, p.id) < (:at, :id)' if after else ''
    rows = conn.execute(text(f'{PROFILE_SELECT}{clause} ORDER BY p.created_at DESC, p.id DESC'
                             ' LIMIT :n'),
                        {'n': limit + 1, **({'at': after[0], 'id': after[1]} if after else {})}).all()
    page = rows[:limit]
    return [_profile_dto(r) for r in page], (_cursor(page[-1].created_at, page[-1].id)
                                             if len(rows) > limit else None)


def _profile_row(conn: Connection, profile_id, lock: bool = False):
    row = conn.execute(text(f'{PROFILE_SELECT} AND p.id = :id{" FOR UPDATE OF p" if lock else ""}'),
                       {'id': profile_id}).first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Profile not found')   # also another owner's (RLS)
    return row


def get_profile(conn: Connection, principal: Principal, cipher: FieldCipher, profile_id) -> dict:
    row = _profile_row(conn, profile_id)
    return _profile_dto(row, _decrypt(cipher, row.birth_input_encrypted, PROFILE, row.owner_id,
                                      row.id))


def update_profile(conn: Connection, principal: Principal, cipher: FieldCipher, profile_id,
                   revision: int, label: str | None, birth: BirthInput | None) -> dict:
    row = _profile_row(conn, profile_id, lock=True)
    if row.revision != revision:
        raise AppError(412, 'REVISION_MISMATCH', 'The profile changed; reload and retry',
                       headers={'ETag': f'"{row.revision}"'})
    changes = {'r': row.revision + 1, 'id': row.id, 'l': (label or row.label).strip(),
               'b': row.birth_input_encrypted, 'v': row.crypto_key_version}
    if birth is not None:
        _check(birth)
        changes['b'] = cipher.encrypt(birth.model_dump_json().encode(),
                                      FieldCipher.context(PROFILE, row.owner_id, row.id))
        changes['v'] = cipher.key_version
    conn.execute(text('UPDATE birth_profiles SET label = :l, birth_input_encrypted = :b,'
                      ' crypto_key_version = :v, revision = :r WHERE id = :id'), changes)
    return get_profile(conn, principal, cipher, profile_id)


def delete_profile(conn: Connection, profile_id, delete_linked_charts: bool) -> dict:
    row = _profile_row(conn, profile_id, lock=True)
    deleted = 0
    if delete_linked_charts:
        for (chart_id,) in conn.execute(text('SELECT id FROM bazi_charts WHERE profile_id = :p'),
                                        {'p': row.id}).all():
            deleted += delete_chart(conn, chart_id)
    conn.execute(text('UPDATE birth_profiles SET deleted_at = now() WHERE id = :id'),
                 {'id': row.id})
    return {'profile_id': str(row.id), 'charts_deleted': deleted,
            'charts_kept': row.charts_count - deleted}


# ---- charts -------------------------------------------------------------------------------

def _summary(facts: dict) -> dict:
    return {p: (f"{v['stem']}-{v['branch']}" if v else None)
            for p, v in facts['pillars'].items()}


def create_chart(conn: Connection, principal: Principal, cipher: FieldCipher,
                 birth: BirthInput | None, profile_id=None, profile_revision: int | None = None,
                 policy_id: str | None = None) -> dict:
    revision = None
    if profile_id is not None:
        profile = get_profile(conn, principal, cipher, profile_id)
        if profile_revision is not None and profile_revision != profile['revision']:
            raise AppError(409, 'PROFILE_REVISION_GONE', 'Only the latest profile revision can'
                           ' be charted; earlier charts keep their own input')
        birth = BirthInput(**profile['birth_input'])
        revision = profile['revision']
    if policy_id is not None:
        if policy_id not in calc_policies.POLICIES:
            raise AppError(422, 'VALIDATION_ERROR', f'unknown policy {policy_id}',
                           field_errors=[{'path': 'body.policy_id', 'message': 'unknown'}])
        birth = birth.model_copy(update={'policy_id': policy_id})
    try:
        facts = compute(birth)
    except CalcError as exc:
        raise calc_error(exc) from None
    policy_row = ensure_policy(conn, birth.policy_id)
    chart_id = uuid.uuid4()
    snapshot = facts.pop('input_snapshot')
    stored = json.dumps(facts, ensure_ascii=False)
    complete = all(facts['pillars'][p] for p in POSITIONS) and not facts['variants']
    conn.execute(text(
        'INSERT INTO bazi_charts (id, owner_id, profile_id, profile_revision, policy_id,'
        ' input_snapshot_encrypted, facts, facts_hash, engine_manifest, validation_status)'
        ' VALUES (:id, :o, :p, :r, :pol, :enc, CAST(:f AS jsonb),'
        ' bazi_sha256_text(CAST(:f AS jsonb)::text), CAST(:m AS jsonb), :s)'),
        {'id': chart_id, 'o': principal.user_id, 'p': profile_id, 'r': revision, 'pol': policy_row,
         'enc': cipher.encrypt(json.dumps(snapshot, sort_keys=True).encode(),
                               FieldCipher.context(CHART_INPUT, principal.user_id, chart_id)),
         'f': stored, 'm': json.dumps(facts['engine_manifest']),
         's': 'valid' if complete else 'partial'})
    return get_chart(conn, principal, cipher, chart_id)


CHART_SELECT = (
    'SELECT c.id, c.owner_id, c.profile_id, c.profile_revision, c.facts, c.facts_hash,'
    ' c.validation_status, c.input_snapshot_encrypted, c.created_at, p.label AS profile_label,'
    ' pol.key AS policy_id FROM bazi_charts c'
    ' JOIN calculation_policies pol ON pol.id = c.policy_id'
    ' LEFT JOIN birth_profiles p ON p.id = c.profile_id')


def _chart_summary(row) -> dict:
    return {'id': str(row.id), 'profile_id': str(row.profile_id) if row.profile_id else None,
            'profile_label': row.profile_label, 'profile_revision': row.profile_revision,
            'policy_id': row.policy_id, 'validation_status': row.validation_status,
            'pillars': _summary(row.facts), 'facts_hash': row.facts['facts_hash'],
            'created_at': row.created_at}


def list_charts(conn: Connection, q: str | None, limit: int, cursor: str | None):
    after = _after(cursor)
    clauses, params = [], {'n': limit + 1}
    if q:
        clauses.append('p.label ILIKE :q')
        params['q'] = f"%{q.replace('%', '').replace('_', '')}%"
    if after:
        clauses.append('(c.created_at, c.id) < (:at, :id)')
        params.update(at=after[0], id=after[1])
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    rows = conn.execute(text(f'{CHART_SELECT}{where} ORDER BY c.created_at DESC, c.id DESC'
                             ' LIMIT :n'), params).all()
    page = rows[:limit]
    return [_chart_summary(r) for r in page], (_cursor(page[-1].created_at, page[-1].id)
                                               if len(rows) > limit else None)


def chart_facts(conn: Connection, chart_id) -> tuple[dict, str]:
    """(facts without the encrypted input, facts hash) of an own chart; 404 otherwise."""
    row = conn.execute(text('SELECT facts, facts_hash FROM bazi_charts WHERE id = :id'),
                       {'id': chart_id}).first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Chart not found')
    return row.facts, row.facts_hash.strip()


def get_chart(conn: Connection, principal: Principal, cipher: FieldCipher, chart_id) -> dict:
    row = conn.execute(text(f'{CHART_SELECT} WHERE c.id = :id'), {'id': chart_id}).first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Chart not found')
    snapshot = _decrypt(cipher, row.input_snapshot_encrypted, CHART_INPUT, row.owner_id, row.id)
    facts = {**row.facts, 'input_snapshot': snapshot, 'chart_id': str(row.id),
             'computed_at': row.created_at.astimezone(timezone.utc).isoformat(timespec='seconds')}
    return {**_chart_summary(row), 'facts': facts}


def delete_chart(conn: Connection, chart_id) -> int:
    if conn.execute(text('SELECT 1 FROM chart_analyses WHERE chart_id = :c LIMIT 1'),
                    {'c': chart_id}).first():
        raise AppError(409, 'CHART_HAS_ANALYSES', 'Delete or keep its analyses first')
    return conn.execute(text('DELETE FROM bazi_charts WHERE id = :c'), {'c': chart_id}).rowcount
