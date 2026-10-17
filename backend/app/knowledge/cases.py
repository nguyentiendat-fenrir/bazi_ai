"""Case library (mệnh lệ): charts printed in books, user cases, revisions (docs/06 · Mệnh lệ).

Books print a chart as four stems over four branches (two rows, or one line of
four pairs), often after "Càn tạo" (male) / "Khôn tạo" (female) and before a luck
list ("Đại vận:", "Hành vận:", or two more rows). :func:`parse_charts` reads
those shapes from a page's blocks; every pillar must be one of the sixty
Giáp-Tý pairs (yang stem with yang branch), so a row of four names that is not
a chart is dropped instead of guessed. A chart never implies a birth date —
four pillars recur every sixty years — and what a book says happened is a
``claimed_event`` of the source, not a verified outcome.

Payload ``book-case/1``: ``pillars.{year,month,day,hour}`` with stable stem and
branch IDs (``hour`` may be null), ``sex_for_luck``, ``luck_pillars``,
``luck_start_ages`` and the printed ``source_text``.
"""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..core.errors import AppError
from ..documents.catalog import visibility_clause
from ..documents.text import nfc
from ..rules.facts import BRANCHES, STEMS
from .evidence import require_evidence

PAYLOAD_SCHEMA = 'book-case/1'
POSITIONS = ('year', 'month', 'day', 'hour')
STEM_NAMES = {'giáp': 'jia', 'ất': 'yi', 'bính': 'bing', 'đinh': 'ding', 'mậu': 'wu', 'kỷ': 'ji',
              'kỉ': 'ji', 'canh': 'geng', 'tân': 'xin', 'nhâm': 'ren', 'quý': 'gui'}
BRANCH_NAMES = {'tý': 'zi', 'tí': 'zi', 'sửu': 'chou', 'dần': 'yin', 'mão': 'mao', 'mẹo': 'mao',
                'thìn': 'chen', 'tỵ': 'si', 'tị': 'si', 'ngọ': 'wu', 'mùi': 'wei', 'vị': 'wei',
                'thân': 'shen', 'dậu': 'you', 'tuất': 'xu', 'hợi': 'hai'}
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_LUCK = re.compile(r'^\s*(đại vận|hành vận)\s*[:：]?', re.IGNORECASE)
_AGES = re.compile(r'^\s*\d{1,3}(\s+\d{1,3})+\s*$')


def valid_pair(stem: str, branch: str) -> bool:
    """One of the sixty pairs: stem and branch share yin/yang."""
    return STEMS.index(stem) % 2 == BRANCHES.index(branch) % 2


def _stems(line: str) -> list[str] | None:
    words = [w.lower() for w in _WORD.findall(line)]
    return [STEM_NAMES[w] for w in words] if words and all(w in STEM_NAMES for w in words) else None


def _branches(line: str) -> list[str] | None:
    words = [w.lower() for w in _WORD.findall(line)]
    return ([BRANCH_NAMES[w] for w in words]
            if words and all(w in BRANCH_NAMES for w in words) else None)


def _pairs(line: str) -> list[tuple[str, str]] | None:
    words = [w.lower() for w in _WORD.findall(line)]
    if not words or len(words) % 2:
        return None
    pairs = []
    for stem, branch in zip(words[::2], words[1::2]):
        if stem not in STEM_NAMES or branch not in BRANCH_NAMES:
            return None
        pairs.append((STEM_NAMES[stem], BRANCH_NAMES[branch]))
    return pairs


@dataclass
class ParsedChart:
    pillars: list[tuple[str, str]]
    sex_for_luck: str | None
    luck_pillars: list[tuple[str, str]] = field(default_factory=list)
    luck_start_ages: list[int] | None = None
    source_text: str = ''
    block_ordinals: list[int] = field(default_factory=list)   # chart and luck rows
    narrative_ordinals: list[int] = field(default_factory=list)
    narrative_lines: list[str] = field(default_factory=list)

    def payload(self) -> dict:
        return {'schema': PAYLOAD_SCHEMA,
                'pillars': {p: {'stem': s, 'branch': b}
                            for p, (s, b) in zip(POSITIONS, self.pillars)},
                'sex_for_luck': self.sex_for_luck,
                'luck_pillars': [{'stem': s, 'branch': b} for s, b in self.luck_pillars],
                'luck_start_ages': self.luck_start_ages, 'source_text': self.source_text}


def _lines(blocks: list[dict]) -> list[tuple[int, str]]:
    return [(b['ordinal'], line.strip()) for b in blocks for line in b['text'].split('\n')
            if line.strip()]


def _sex(text_: str) -> str | None:
    lowered = text_.lower()
    if 'khôn tạo' in lowered:
        return 'female'
    if 'càn tạo' in lowered:
        return 'male'
    return None


def parse_charts(blocks: list[dict]) -> list[ParsedChart]:
    """Charts printed on one page. ``blocks``: ordinal, text, kind (reading order)."""
    lines = _lines(blocks)
    charts, i = [], 0
    while i < len(lines):
        ordinal, line = lines[i]
        chart, used = None, 0
        pairs = _pairs(line)
        if pairs and len(pairs) == 4:
            chart, used = pairs, 1
        else:
            stems = _stems(line)
            branches = _branches(lines[i + 1][1]) if stems and i + 1 < len(lines) else None
            if stems and branches and len(stems) == len(branches) == 4:
                chart, used = list(zip(stems, branches)), 2
        if chart is None or not all(valid_pair(s, b) for s, b in chart):
            i += 1
            continue
        context = ' '.join(l for _, l in lines[max(0, i - 2):i])
        parsed = ParsedChart(chart, _sex(context), source_text=' / '.join(
            l for _, l in lines[i:i + used]),
            block_ordinals=sorted({o for o, _ in lines[i:i + used]}))
        j = i + used
        if j < len(lines) and _AGES.match(lines[j][1]):
            parsed.luck_start_ages = [int(n) for n in lines[j][1].split()]
            parsed.block_ordinals.append(lines[j][0])
            j += 1
        if j < len(lines) and _LUCK.match(lines[j][1]):
            rest = _LUCK.sub('', lines[j][1]).replace('/', ' ')
            luck = _pairs(rest)
            if luck and all(valid_pair(s, b) for s, b in luck):
                parsed.luck_pillars = luck
                parsed.block_ordinals.append(lines[j][0])
                j += 1
        elif j + 1 < len(lines):
            stems, branches = _stems(lines[j][1]), _branches(lines[j + 1][1])
            if stems and branches and len(stems) == len(branches) >= 2 and all(
                    valid_pair(s, b) for s, b in zip(stems, branches)):
                parsed.luck_pillars = list(zip(stems, branches))
                parsed.block_ordinals += [lines[j][0], lines[j + 1][0]]
                j += 2
        # Narrative: the following prose on the page until the next chart or a heading.
        k = j
        while k < len(lines) and len(parsed.narrative_ordinals) < 4:
            follow_ordinal, follow = lines[k]
            block = next(b for b in blocks if b['ordinal'] == follow_ordinal)
            if block['kind'] == 'heading' or _pairs(follow) or _stems(follow):
                break
            if follow_ordinal not in parsed.block_ordinals + parsed.narrative_ordinals:
                parsed.narrative_ordinals.append(follow_ordinal)
            parsed.narrative_lines.append(follow)
            k += 1
        parsed.block_ordinals = sorted(set(parsed.block_ordinals))
        charts.append(parsed)
        i = j
    return charts


def validate_payload(payload: dict) -> list[str]:
    problems = []
    if not isinstance(payload, dict) or payload.get('schema') != PAYLOAD_SCHEMA:
        return [f'chart_payload.schema must be {PAYLOAD_SCHEMA}']
    pillars = payload.get('pillars') or {}
    for position in POSITIONS:
        pillar = pillars.get(position)
        if pillar is None and position == 'hour':
            continue                              # the hour may be unknown
        if (not isinstance(pillar, dict) or pillar.get('stem') not in STEMS
                or pillar.get('branch') not in BRANCHES):
            problems.append(f'pillars.{position} needs a stem and a branch ID')
        elif not valid_pair(pillar['stem'], pillar['branch']):
            problems.append(f'pillars.{position} is not one of the sixty pairs')
    if payload.get('sex_for_luck') not in (None, 'male', 'female'):
        problems.append('sex_for_luck is male, female or null')
    for i, luck in enumerate(payload.get('luck_pillars') or []):
        if (not isinstance(luck, dict) or luck.get('stem') not in STEMS
                or luck.get('branch') not in BRANCHES or not valid_pair(luck['stem'], luck['branch'])):
            problems.append(f'luck_pillars[{i}] is not one of the sixty pairs')
    if 'birth_date' in payload:
        problems.append('a book chart does not give a birth date; keep it out of the payload')
    return problems


# ---- storage and API services --------------------------------------------------------

SELECT = ('SELECT c.id AS case_id, c.case_key, c.owner_id, c.origin, c.visibility, c.deleted_at,'
          ' r.id AS revision_id, r.revision, r.school_id, s.key AS school_key, r.method_id,'
          ' r.chart_payload, r.narrative, r.claimed_events, r.state, r.quality, r.created_at'
          ' FROM cases c JOIN case_revisions r ON r.case_id = c.id'
          ' JOIN schools s ON s.id = r.school_id')
LATEST = ('r.revision = (SELECT max(x.revision) FROM case_revisions x WHERE x.case_id = c.id)')


def _case_dto(row) -> dict:
    return {'id': str(row['case_id']), 'case_key': row['case_key'],
            'owner_id': str(row['owner_id']) if row['owner_id'] else None,
            'origin': row['origin'], 'visibility': row['visibility'],
            'revision_id': str(row['revision_id']), 'revision': row['revision'],
            'school_id': str(row['school_id']), 'school_key': row['school_key'],
            'method_id': str(row['method_id']) if row['method_id'] else None,
            'chart_payload': row['chart_payload'], 'narrative': row['narrative'],
            'claimed_events': row['claimed_events'], 'state': row['state'],
            'quality': row['quality'] or {}, 'created_at': row['created_at']}


def _readable(principal: Principal) -> tuple[str, dict]:
    """Reviewers see the library and drafts; others see approved library cases and their own."""
    if principal.has_role('reviewer'):
        return "(c.origin <> 'user_case' OR c.owner_id = :me)", {'me': principal.user_id}
    return ("((c.visibility = 'library' AND r.state = 'approved') OR c.owner_id = :me)",
            {'me': principal.user_id})


def list_cases(conn: Connection, principal: Principal, school_id, state, origin, book_version_id,
               limit: int, cursor: str | None) -> tuple[list[dict], str | None]:
    where, params = _readable(principal)
    clauses = ['c.deleted_at IS NULL', LATEST, where]
    params['limit'] = limit + 1
    for column, value, prefix in (('school_id', school_id, 'r'), ('state', state, 'r'),
                                  ('origin', origin, 'c')):
        if value is not None:
            clauses.append(f'{prefix}.{column} = :{column}')
            params[column] = value
    if book_version_id:
        clauses.append('EXISTS (SELECT 1 FROM case_sources cs JOIN evidence_spans e'
                       ' ON e.id = cs.evidence_id WHERE cs.case_revision_id = r.id'
                       ' AND e.book_version_id = :version)')
        params['version'] = book_version_id
    offset = 0
    if cursor:
        try:
            offset = int(base64.urlsafe_b64decode(cursor.encode()).decode())
        except (ValueError, UnicodeDecodeError):
            raise AppError(422, 'VALIDATION_ERROR', 'Invalid cursor') from None
    params['offset'] = offset
    rows = conn.execute(text(f"{SELECT} WHERE {' AND '.join(clauses)}"
                             ' ORDER BY c.created_at, c.id LIMIT :limit OFFSET :offset'),
                        params).mappings().all()
    more = len(rows) > limit
    return [_case_dto(r) for r in rows[:limit]], (
        base64.urlsafe_b64encode(str(offset + limit).encode()).decode() if more else None)


def get_case(conn: Connection, principal: Principal, case_id) -> dict:
    where, params = _readable(principal)
    row = conn.execute(text(f'{SELECT} WHERE c.id = :i AND c.deleted_at IS NULL AND {LATEST}'
                            f' AND {where}'), {**params, 'i': case_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Case not found')
    visible, vparams = visibility_clause(principal)
    sources = conn.execute(text(
        'SELECT e.id, p.physical_page_number, e.book_version_id, e.page_revision_id,'
        ' substr(pr.normalized_text, e.start_offset + 1, e.end_offset - e.start_offset) AS quote'
        ' FROM case_sources cs JOIN evidence_spans e ON e.id = cs.evidence_id'
        ' JOIN page_revisions pr ON pr.id = e.page_revision_id JOIN pages p ON p.id = pr.page_id'
        ' JOIN book_versions v ON v.id = e.book_version_id JOIN books b ON b.id = v.book_id'
        f' WHERE cs.case_revision_id = :r AND b.deleted_at IS NULL AND {visible}'
        ' ORDER BY p.physical_page_number, e.start_offset'),
        {**vparams, 'r': row['revision_id']}).mappings().all()
    revisions = conn.execute(text('SELECT id, revision, state FROM case_revisions'
                                  ' WHERE case_id = :c ORDER BY revision'), {'c': case_id}).all()
    return {**_case_dto(row),
            'sources': [{'evidence_id': str(s['id']), 'physical_page_number':
                         s['physical_page_number'], 'book_version_id': str(s['book_version_id']),
                         'page_revision_id': str(s['page_revision_id']), 'quote': s['quote']}
                        for s in sources],
            'revisions': [{'id': str(r[0]), 'revision': r[1], 'state': r[2]} for r in revisions]}


def _check(conn: Connection, school_id, method_id, payload: dict, events: list) -> None:
    problems = validate_payload(payload)
    if problems:
        raise AppError(422, 'VALIDATION_ERROR', '; '.join(problems))
    if not conn.execute(text('SELECT 1 FROM schools WHERE id = :s'), {'s': school_id}).first():
        raise AppError(422, 'VALIDATION_ERROR', 'unknown school')
    if method_id is not None and not conn.execute(text(
            'SELECT 1 FROM methods WHERE id = :m AND school_id = :s'),
            {'m': method_id, 's': school_id}).first():
        raise AppError(422, 'VALIDATION_ERROR', 'method does not belong to the school')
    if not isinstance(events, list):
        raise AppError(422, 'VALIDATION_ERROR', 'claimed_events is a list')


def _insert_revision(conn: Connection, case_id, revision: int, school_id, method_id,
                     payload: dict, narrative: str, events: list, quality: dict,
                     evidence_ids: list[str]):
    revision_id = conn.execute(text(
        'INSERT INTO case_revisions (case_id, revision, school_id, method_id, chart_payload,'
        ' narrative, claimed_events, quality) VALUES (:c, :r, :s, :m, CAST(:p AS jsonb), :n,'
        ' CAST(:e AS jsonb), CAST(:q AS jsonb)) RETURNING id'),
        {'c': case_id, 'r': revision, 's': school_id, 'm': method_id,
         'p': json.dumps(payload, ensure_ascii=False), 'n': nfc(narrative).strip(),
         'e': json.dumps(events, ensure_ascii=False), 'q': json.dumps(quality)}).scalar_one()
    for evidence_id in evidence_ids:
        conn.execute(text('INSERT INTO case_sources (case_revision_id, evidence_id)'
                          ' VALUES (:r, :e)'), {'r': revision_id, 'e': evidence_id})
    return revision_id


def create_case(conn: Connection, principal: Principal, origin: str, school_id, payload: dict,
                narrative: str, events: list, evidence_ids: list, method_id=None,
                case_key: str | None = None) -> dict:
    if origin != 'user_case' and not principal.has_role('reviewer'):
        raise AppError(403, 'FORBIDDEN', 'only reviewers add library cases')
    _check(conn, school_id, method_id, payload, events)
    evidence = require_evidence(conn, evidence_ids)
    if origin == 'book_case' and not evidence:
        raise AppError(422, 'VALIDATION_ERROR', 'a book case cites the page it comes from')
    owner, visibility = ((principal.user_id, 'private') if origin == 'user_case'
                         else (None, 'library'))
    case_id = conn.execute(text(
        'INSERT INTO cases (case_key, owner_id, origin, visibility) VALUES (:k, :o, :origin, :v)'
        ' ON CONFLICT (case_key) DO NOTHING RETURNING id'),
        {'k': case_key or f'case.{uuid.uuid4().hex[:20]}', 'o': owner, 'origin': origin,
         'v': visibility}).scalar()
    if case_id is None:
        raise AppError(409, 'CONFLICT', 'this case_key exists')
    _insert_revision(conn, case_id, 1, school_id, method_id, payload, narrative, events, {},
                     evidence)
    return get_case(conn, principal, case_id)


def revise_case(conn: Connection, principal: Principal, case_id, base_revision: int,
                changes: dict) -> dict:
    current = get_case(conn, principal, case_id)
    if current['origin'] == 'user_case' and current['owner_id'] != str(principal.user_id):
        raise AppError(404, 'NOT_FOUND', 'Case not found')
    if current['origin'] != 'user_case' and not principal.has_role('reviewer'):
        raise AppError(403, 'FORBIDDEN', 'only reviewers revise library cases')
    conn.execute(text('SELECT 1 FROM cases WHERE id = :c FOR UPDATE'), {'c': case_id})
    latest = conn.execute(text('SELECT max(revision) FROM case_revisions WHERE case_id = :c'),
                          {'c': case_id}).scalar_one()
    if base_revision != latest:
        raise AppError(412, 'REVISION_MISMATCH', f'Revise the latest revision ({latest})')
    merged = {key: changes[key] if changes.get(key) is not None else current[key]
              for key in ('school_id', 'method_id', 'chart_payload', 'narrative',
                          'claimed_events')}
    _check(conn, merged['school_id'], merged['method_id'], merged['chart_payload'],
           merged['claimed_events'])
    evidence = (require_evidence(conn, changes['evidence_ids'])
                if changes.get('evidence_ids') is not None
                else [s['evidence_id'] for s in current['sources']])
    _insert_revision(conn, case_id, latest + 1, merged['school_id'], merged['method_id'],
                     merged['chart_payload'], merged['narrative'], merged['claimed_events'],
                     current['quality'], evidence)
    return get_case(conn, principal, case_id)


def delete_case(conn: Connection, principal: Principal, case_id) -> None:
    current = get_case(conn, principal, case_id)
    own = current['owner_id'] == str(principal.user_id)
    if not own and (current['origin'] == 'user_case' or not principal.has_role('reviewer')):
        raise AppError(404 if current['origin'] == 'user_case' else 403,
                       'NOT_FOUND' if current['origin'] == 'user_case' else 'FORBIDDEN',
                       'Case not found' if current['origin'] == 'user_case'
                       else 'only reviewers remove library cases')
    conn.execute(text('UPDATE cases SET deleted_at = now() WHERE id = :c'), {'c': case_id})


def book_case_key(version_id, chart: ParsedChart) -> str:
    material = f"{version_id}|{json.dumps(chart.pillars)}|{chart.source_text}"
    return 'book.' + hashlib.sha256(material.encode()).hexdigest()[:24]


def chart_to_dict(chart: ParsedChart) -> dict:
    return asdict(chart)
