"""One reasoning run: a fixed state machine per mode (docs/09 · Chế độ và orchestration).

research:        search (scope of the conversation) → evidence → model → validate
chart_analysis:  chart facts → active ruleset → targeted search → model → validate
comparison:      one search per selected school → shared bundle → model → validate

There is no agent loop: the server calls its own tools in that order (at most 8 per
run), every step is a durable event, and the run checks for cancellation between
steps. Without a usable model (none configured, a provider error, or book text that
may not leave the server) the run still answers deterministically from facts, rule
results and verbatim sources, and says so. Nothing is shown before validation; the
assistant message gets the canonical Answer, claims and citations in one commit.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from ..auth.service import Principal
from ..calc.tables import ELEMENT_LABELS
from ..charts import analyses, service as charts
from ..core.db import transaction
from ..core.errors import AppError
from ..llm import providers, service as llm
from ..retrieval.citations import save_bundle
from ..retrieval.packing import pack
from ..retrieval.search import Spec, search
from ..rules.dsl import MISSING, _lookup
from ..rules.facts import FACTS
from .answer import Answer, DraftAnswer, DraftClaim
from .prompts import messages
from .validate import validate

log = logging.getLogger('bazi.reasoning')
EVENT_TTL = timedelta(days=7)
MAX_TOKENS = 1500
MAX_TOOL_CALLS = 8
POSITIONS = ('year', 'month', 'day', 'hour')
POSITION_LABELS = {'year': 'năm', 'month': 'tháng', 'day': 'ngày', 'hour': 'giờ'}


class Cancelled(Exception):
    pass


# ---- events and state ---------------------------------------------------------------------

def emit(engine: Engine, owner_id, run_id, event_type: str, payload: dict) -> int:
    with transaction(engine, owner_id) as conn:
        conn.execute(text('SELECT 1 FROM chat_runs WHERE id = :r FOR UPDATE'), {'r': run_id})
        seq = conn.execute(text('SELECT coalesce(max(seq), 0) + 1 FROM run_events'
                                ' WHERE run_id = :r'), {'r': run_id}).scalar_one()
        conn.execute(text(
            'INSERT INTO run_events (run_id, seq, event_type, payload, expires_at)'
            ' VALUES (:r, :s, :t, CAST(:p AS jsonb), :e)'),
            {'r': run_id, 's': seq, 't': event_type, 'e': datetime.now(timezone.utc) + EVENT_TTL,
             'p': json.dumps(payload, ensure_ascii=False, default=str)})
        conn.execute(text('UPDATE chat_runs SET updated_at = now() WHERE id = :r'), {'r': run_id})
    return seq


def _state(engine: Engine, owner_id, run_id) -> str:
    with transaction(engine, owner_id) as conn:
        return conn.execute(text('SELECT state FROM chat_runs WHERE id = :r'),
                            {'r': run_id}).scalar_one()


def _move(engine: Engine, owner_id, run_id, state: str) -> None:
    with transaction(engine, owner_id) as conn:
        current = conn.execute(text('SELECT state FROM chat_runs WHERE id = :r FOR UPDATE'),
                               {'r': run_id}).scalar_one()
        if current == 'cancelled':
            raise Cancelled()
        if current != state:
            conn.execute(text('UPDATE chat_runs SET state = :s WHERE id = :r'),
                         {'s': state, 'r': run_id})


class Tools:
    """The server's own tools, in a fixed order, counted against the per-run cap."""

    def __init__(self, engine: Engine, principal: Principal, run_id):
        self.engine, self.principal, self.run_id, self.calls = engine, principal, run_id, 0

    def __call__(self, name: str, step, summary=lambda result: {}):
        if _state(self.engine, self.principal.user_id, self.run_id) == 'cancelled':
            raise Cancelled()
        self.calls += 1
        if self.calls > MAX_TOOL_CALLS:
            raise AppError(500, 'TOOL_LIMIT', f'more than {MAX_TOOL_CALLS} tool calls')
        emit(self.engine, self.principal.user_id, self.run_id, 'tool.started', {'tool': name})
        with transaction(self.engine, self.principal.user_id) as conn:
            result = step(conn)
        emit(self.engine, self.principal.user_id, self.run_id, 'tool.completed',
             {'tool': name, **summary(result)})
        return result


# ---- facts, rules, evidence -----------------------------------------------------------------

def allowed_paths(facts: dict) -> dict[str, object]:
    """Registered fact paths that have a value in these facts (the model may cite them)."""
    found = {}
    for path in FACTS:
        value = _lookup(facts, path) if not path.startswith('query.') else MISSING
        if value is not MISSING and value is not None:
            found[path] = value
    return found


def _spec(context: dict, query: str, schools: list | None = None, top_k: int = 8,
          bundle: bool = True) -> Spec:
    return Spec(query=query, top_k=top_k,
                school_ids=context.get('school_ids') or [] if schools is None else schools,
                book_ids=context.get('book_ids') or [], pack=bundle)


def _deterministic(facts: dict | None, paths: dict, rule_claims: list[dict],
                   groups: list[dict], reason: str) -> DraftAnswer:
    claims: list[DraftClaim] = []
    pillars = (facts or {}).get('pillars') or {}
    if pillars.get('day'):
        day = pillars['day']
        claims.append(DraftClaim(
            text=f"Nhật chủ là {day['stem_label']} (hành {ELEMENT_LABELS[day['stem_element']]}).",
            kind='calculation', fact_paths=['pillars.day.stem', 'pillars.day.stem_element']))
        known = [p for p in POSITIONS if pillars.get(p)]
        claims.append(DraftClaim(
            text='Tứ trụ: ' + '; '.join(f"trụ {POSITION_LABELS[p]} {pillars[p]['stem_label']} "
                                        f"{pillars[p]['branch_label']}" for p in known) + '.',
            kind='calculation', fact_paths=[f'pillars.{p}.stem' for p in known
                                            if f'pillars.{p}.stem' in paths]))
    for claim in rule_claims:
        claims.append(DraftClaim(text=claim['explanation'], kind='rule_result',
                                 rule_keys=[claim['rule_key']]))
    for group in groups[:3]:
        claims.append(DraftClaim(text=group['excerpt'][:300], kind='source_statement',
                                 evidence=[group['evidence_id']], school_key=group.get('school_key')))
    return DraftAnswer(summary=reason, claims=claims[:12])


def _principal(conn: Connection, owner_id) -> Principal:
    user = conn.execute(text('SELECT id, email, role FROM users WHERE id = :u'),
                        {'u': owner_id}).one()
    return Principal(user.id, user.email, user.role, uuid.uuid4(), '')


def _load(engine: Engine, run_id, owner_id) -> tuple[Principal, dict]:
    with transaction(engine, owner_id) as conn:
        principal = _principal(conn, owner_id)
        run = conn.execute(text(
            'SELECT r.id, r.mode, r.context_snapshot, r.assistant_message_id,'
            ' m.content AS question FROM chat_runs r JOIN messages m ON m.id = r.user_message_id'
            ' WHERE r.id = :r'), {'r': run_id}).mappings().one()
    return principal, dict(run)


# ---- the run ----------------------------------------------------------------------------------

def process(engine: Engine, run_id, owner_id, app_env: str = 'dev', transport=None) -> str:
    """Execute a run already moved to ``running``; returns its final state."""
    principal, run = _load(engine, run_id, owner_id)
    context, mode, question = run['context_snapshot'], run['mode'], run['question']
    emit(engine, owner_id, run_id, 'run.started', {'mode': mode})
    tools = Tools(engine, principal, run_id)
    if mode == 'research' and _rag_enabled():
        return _research(engine, owner_id, run, principal, question, context)
    try:
        facts, analysis, rule_claims, notes = None, None, [], []
        paths: dict = {}
        query = question
        if mode == 'chart_analysis':
            if not context.get('chart_id'):
                raise AppError(422, 'CHART_REQUIRED', 'chart analysis needs an active chart')
            facts, _ = tools('get_chart_facts',
                             lambda conn: charts.chart_facts(conn, context['chart_id']),
                             lambda r: {'pillars': sum(1 for v in r[0]['pillars'].values() if v)})
            paths = allowed_paths(facts)
            if context.get('school_ids') and context.get('method_ids'):
                try:
                    analysis = tools('evaluate_rules', lambda conn: analyses.run_analysis(
                        conn, principal, context['chart_id'], context['school_ids'][0],
                        context['method_ids'][0], None, context.get('as_of'), run_id),
                        lambda r: {'fired': r['answer']['counters']['fired'],
                                   'conflicts': len(r['answer']['conflicts'])})
                    rule_claims = analysis['answer']['claims']
                except AppError as exc:
                    if exc.code not in ('NO_ACTIVE_RULESET', 'RULESET_HAS_REVOKED_RULE'):
                        raise
                    notes.append('Chưa có bộ quy tắc đã duyệt dùng được cho phương pháp này;'
                                 ' chỉ có dữ kiện và nguồn.')
            else:
                notes.append('Chưa chọn trường phái và phương pháp nên chưa chạy quy tắc.')
            day = (facts.get('pillars') or {}).get('day') or {}
            query = ' '.join(filter(None, [question, day.get('stem_label'), 'nhật chủ']))

        if mode == 'comparison':
            schools = context.get('school_ids') or []
            if len(schools) < 2:
                raise AppError(422, 'SCHOOLS_REQUIRED', 'comparison needs at least two schools')

            def compare(conn):
                hits, statuses, release, epoch = [], [], None, None
                for school in schools[:4]:
                    result = search(conn, principal, _spec(context, query, [school], 4, False),
                                    app_env, transport)
                    hits += result['hits']
                    statuses.append(result['status'])
                    release = result['release_id'] or release
                    epoch = result['visibility_epoch'] if result['visibility_epoch'] is not None \
                        else epoch
                if not hits:
                    status = 'empty_corpus' if set(statuses) == {'empty_corpus'} else 'no_match'
                    return {'status': status, 'groups': [], 'bundle_id': None,
                            'release_id': release}
                bundle = pack(hits, per_book=2)
                bundle_id = save_bundle(conn, principal, release, epoch, query, bundle)
                return {'status': 'ok', 'groups': bundle['groups'], 'bundle_id': bundle_id,
                        'release_id': release}
            found = tools('search_knowledge', compare,
                          lambda r: {'status': r['status'], 'groups': len(r['groups'])})
        else:
            def lookup(conn):
                result = search(conn, principal, _spec(context, query), app_env, transport)
                bundle = result.get('bundle') or {}
                return {'status': result['status'], 'groups': bundle.get('groups', []),
                        'bundle_id': bundle.get('bundle_id'), 'release_id': result['release_id']}
            found = tools('search_knowledge', lookup,
                          lambda r: {'status': r['status'], 'groups': len(r['groups'])})
        emit(engine, owner_id, run_id, 'retrieval.ready',
             {'status': found['status'], 'groups': len(found['groups'])})

        with transaction(engine, owner_id) as conn:
            profile = providers.load(conn)
            shareable = [g for g in found['groups'] if profile is None
                         or providers.may_send_book_text(conn, profile, [g['book_version_id']])]
        withheld = len(found['groups']) - len(shareable)
        groups = {g['evidence_id']: g for g in found['groups']}
        trace_ref = {'run_id': str(run_id), 'bundle_id': found['bundle_id'],
                     'analysis_id': analysis['id'] if analysis else None,
                     'corpus_release_id': found['release_id']}
        override = None
        if found['status'] == 'empty_corpus' and mode != 'chart_analysis':
            draft = DraftAnswer(summary='Kho tra cứu chưa có sách nào được publish: hãy tải sách'
                                ' lên và publish để tra cứu có nguồn.', claims=[])
            override = 'empty_corpus'
        elif profile is None or (found['groups'] and not shareable):
            reason = ('Chưa cấu hình mô hình ngôn ngữ' if profile is None else
                      'Mô hình hiện tại ở bên ngoài và các sách liên quan không cho gửi nội dung ra')
            draft = _deterministic(facts, paths, rule_claims, found['groups'],
                                   f'{reason}: dưới đây là dữ kiện, quy tắc và đoạn nguồn liên quan,'
                                   ' chưa có phần diễn giải.')
            override = 'provider_not_configured'
        else:
            _move(engine, owner_id, run_id, 'waiting_provider')
            emit(engine, owner_id, run_id, 'provider.waiting', {'model': profile.model_name})
            prompt = messages(mode, question, context.get('history') or [], facts, paths,
                              rule_claims, notes[0] if notes else None, shareable)
            try:
                result, _ = llm.generate(engine, principal, prompt, MAX_TOKENS, DraftAnswer,
                                         app_env, transport, None, run_id)
                draft = result.data
            except AppError as exc:
                if exc.code == 'BUDGET_EXCEEDED':
                    raise
                # Fail safe: what the system knows without the model, labelled as such.
                draft = _deterministic(facts, paths, rule_claims, found['groups'],
                                       f'Mô hình không trả lời được ({exc.code}): chỉ có dữ kiện,'
                                       ' quy tắc và đoạn nguồn.')
                notes.append(f'Mô hình lỗi ({exc.code}); chưa có phần diễn giải.')
            _move(engine, owner_id, run_id, 'running')
            if withheld:
                notes.append(f'{withheld} đoạn nguồn không được gửi tới mô hình bên ngoài.')

        if _state(engine, owner_id, run_id) == 'cancelled':
            raise Cancelled()
        with transaction(engine, owner_id) as conn:
            answer = validate(conn, principal, draft, mode=mode, bundle_id=found['bundle_id'],
                              groups=groups, fact_paths=paths,
                              fired={c['rule_key']: c for c in rule_claims},
                              method_key=analysis['answer']['ruleset']['method_key']
                              if analysis else None, trace_ref=trace_ref)
        if override:
            answer.status = override
        answer.limitations += notes
        for claim in answer.claims:
            emit(engine, owner_id, run_id, 'answer.claim', {'claim': claim.model_dump()})
        _finish(engine, owner_id, run, answer, context)
        emit(engine, owner_id, run_id, 'answer.completed', {'answer': answer.model_dump()})
        return 'completed'
    except Cancelled:
        _close(engine, owner_id, run, 'cancelled', None)
        emit(engine, owner_id, run_id, 'run.cancelled', {})
        return 'cancelled'
    except AppError as exc:
        _close(engine, owner_id, run, 'failed', {'code': exc.code, 'message': str(exc)[:300]})
        emit(engine, owner_id, run_id, 'run.failed', {'code': exc.code, 'message': str(exc)[:300]})
        return 'failed'
    except Exception:  # noqa: BLE001 - never leave a run running; the log has the stack
        log.exception('reasoning run failed', extra={'event': 'run_failed'})
        _close(engine, owner_id, run, 'failed', {'code': 'INTERNAL', 'message': 'internal error'})
        emit(engine, owner_id, run_id, 'run.failed', {'code': 'INTERNAL'})
        return 'failed'


def _rag_enabled() -> bool:
    from ..rag.chat import enabled
    return enabled()


def _research(engine: Engine, owner_id, run: dict, principal: Principal, question: str,
              context: dict) -> str:
    """Research mode on the RAG pilot: parent/child retrieval + grounded Qwen answer."""
    from ..rag.chat import run_research, to_answer
    run_id = run['id']
    try:
        if _state(engine, owner_id, run_id) == 'cancelled':
            raise Cancelled()
        with transaction(engine, owner_id) as conn:
            keys = [r[0] for r in conn.execute(text(
                'SELECT key FROM schools WHERE id = ANY(CAST(:ids AS uuid[]))'),
                {'ids': [str(s) for s in context.get('school_ids') or []]})]
        emit(engine, owner_id, run_id, 'tool.started', {'tool': 'rag_answer'})
        _move(engine, owner_id, run_id, 'waiting_provider')
        out = run_research(engine, principal, question, keys, context.get('book_ids') or [])
        _move(engine, owner_id, run_id, 'running')
        emit(engine, owner_id, run_id, 'tool.completed',
             {'tool': 'rag_answer', 'status': out.status, 'parents': len(out.parents)})
        emit(engine, owner_id, run_id, 'retrieval.ready',
             {'status': out.status, 'groups': len(out.parents)})
        answer = to_answer(out, {'run_id': str(run_id), 'bundle_id': None, 'analysis_id': None,
                                 'corpus_release_id': None})
        if _state(engine, owner_id, run_id) == 'cancelled':
            raise Cancelled()
        for claim in answer.claims:
            emit(engine, owner_id, run_id, 'answer.claim', {'claim': claim.model_dump()})
        _finish(engine, owner_id, run, answer, context)
        emit(engine, owner_id, run_id, 'answer.completed', {'answer': answer.model_dump()})
        return 'completed'
    except Cancelled:
        _close(engine, owner_id, run, 'cancelled', None)
        emit(engine, owner_id, run_id, 'run.cancelled', {})
        return 'cancelled'
    except Exception:  # noqa: BLE001 - never leave a run running; the log has the stack
        log.exception('research run failed', extra={'event': 'run_failed'})
        _close(engine, owner_id, run, 'failed', {'code': 'INTERNAL', 'message': 'internal error'})
        emit(engine, owner_id, run_id, 'run.failed', {'code': 'INTERNAL'})
        return 'failed'


def _close(engine: Engine, owner_id, run: dict, state: str, error: dict | None) -> None:
    with transaction(engine, owner_id) as conn:
        current = conn.execute(text('SELECT state FROM chat_runs WHERE id = :r FOR UPDATE'),
                               {'r': run['id']}).scalar_one()
        if current not in ('completed', 'failed', 'cancelled'):
            conn.execute(text('UPDATE chat_runs SET state = :s, error = CAST(:e AS jsonb)'
                              ' WHERE id = :r'),
                         {'s': state, 'e': json.dumps(error) if error else None, 'r': run['id']})
        conn.execute(text("UPDATE messages SET status = :s WHERE id = :m AND status IN"
                          " ('pending', 'streaming')"),
                     {'s': 'cancelled' if state == 'cancelled' else 'failed',
                      'm': run['assistant_message_id']})


def _finish(engine: Engine, owner_id, run: dict, answer: Answer, context: dict) -> None:
    with transaction(engine, owner_id) as conn:
        state = conn.execute(text('SELECT state FROM chat_runs WHERE id = :r FOR UPDATE'),
                             {'r': run['id']}).scalar_one()
        if state == 'cancelled':
            raise Cancelled()
        schools = dict(conn.execute(text('SELECT key, id FROM schools')).all())
        conn.execute(text(
            "UPDATE messages SET content = :c, structured_answer = CAST(:a AS jsonb),"
            " status = 'completed' WHERE id = :m"),
            {'c': answer.summary, 'a': answer.model_dump_json(), 'm': run['assistant_message_id']})
        release = answer.trace_ref.get('corpus_release_id')
        for claim in answer.claims:
            claim_id = conn.execute(text(
                'INSERT INTO claims (message_id, local_key, text, kind, school_id, support_status,'
                ' inference_level, fact_paths, trace_refs) VALUES (:m, :k, :t, :kind, :s, :st,'
                ' :i, CAST(:f AS jsonb), CAST(:r AS jsonb)) RETURNING id'),
                {'m': run['assistant_message_id'], 'k': claim.id, 't': claim.text,
                 'kind': claim.kind, 's': schools.get(claim.school_key),
                 'st': claim.support_status, 'i': claim.inference_level,
                 'f': json.dumps(claim.fact_paths),
                 'r': json.dumps(claim.rule_trace_ids)}).scalar_one()
            for citation in claim.citations:
                for span_id in citation.evidence_span_ids:
                    conn.execute(text(
                        'INSERT INTO citations (claim_id, evidence_id, corpus_release_id,'
                        ' validation, display_snapshot) VALUES (:c, :e, :r, CAST(:v AS jsonb),'
                        ' CAST(:d AS jsonb)) ON CONFLICT (claim_id, evidence_id) DO NOTHING'),
                        {'c': claim_id, 'e': span_id, 'r': release,
                         'v': json.dumps({'support': citation.support,
                                          'status': claim.support_status}),
                         'd': json.dumps({'book_title': citation.book_title,
                                          'pages': citation.pages, 'quote': citation.quote},
                                         ensure_ascii=False)})
        for kind, entity in (('chart', context.get('chart_id')),
                             ('analysis', answer.trace_ref.get('analysis_id')),
                             ('corpus_release', release)):
            if entity:
                conn.execute(text('INSERT INTO analysis_dependencies (run_id, dependency_kind,'
                                  ' dependency_id) VALUES (:r, :k, :i)'),
                             {'r': run['id'], 'k': kind, 'i': entity})
        conn.execute(text("UPDATE chat_runs SET state = 'completed' WHERE id = :r"),
                     {'r': run['id']})
