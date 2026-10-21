"""Run a question file through the harness with Qwen and the RAG pilot retrieval.

    python -m backend.app.answering.run test_questions.txt --as reviewer@example.test
    python -m backend.app.answering.run test_questions.txt --as r@x --only 13 18 --time-budget 240
    python -m backend.app.answering.run test_questions.txt --as r@x --publish "Lượt 2 · harness"

Writes ``.artifacts/answering/run-<UTC>.json`` (every result with its trace, for the judge
page and for comparing runs) and ``run-<UTC>.md`` (answers, needs and sources to read).
``--publish LABEL`` also stores the run for the /judge page: each result in the page's
``AskOut`` shape (parents given to the model, scored chunks behind them) plus ``harness``
(needs, kept and dropped claims, chart facts, trace).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

from .harness import Config, Harness, Result

QUESTION = re.compile(r'^\s*(\d+)[.)]\s*(.+?)\s*$')
CITES = re.compile(r'\[((?:P\d+|F)(?:\s*,\s*(?:P\d+|F))+)\]')      # [P1, P3] -> [P1][P3]
HARNESS_KEYS = ('needs', 'claims', 'dropped', 'facts', 'focus', 'agreement', 'stop_reason',
                'rounds', 'llm_calls', 'prompt_version', 'trace')
STATUS_LABELS = {'ok': 'đủ', 'partial': 'một phần', 'insufficient': 'không đủ căn cứ',
                 'no_evidence': 'không tìm thấy', 'refused': 'từ chối', 'model_error': 'lỗi mô hình'}
NEED_LABELS = {'du': 'đủ', 'mot_phan': 'một phần', 'thieu': 'thiếu', 'mau_thuan': 'mâu thuẫn'}


def parse_questions(text: str) -> list[tuple[str, str]]:
    """``N. question`` blocks; a question may continue on the following lines."""
    out: list[list[str]] = []
    for line in text.splitlines():
        m = QUESTION.match(line)
        if m:
            out.append([m.group(1), m.group(2)])
        elif out and line.strip():
            out[-1][1] += ' ' + line.strip()
    return [(n, q) for n, q in out]


def markdown(run: dict) -> str:
    lines = [f"# Lượt chạy {run['run_id']}", '',
             f"Prompt {run['prompt_version']} · {len(run['results'])} câu · cấu hình: "
             + ', '.join(f'{k}={v}' for k, v in run['config'].items() if k != 'tokens'), '']
    for item in run['results']:
        r = item['result']
        lines += [f"## Câu {item['id']} · {STATUS_LABELS.get(r['status'], r['status'])}", '',
                  f"> {r['question']}", '',
                  f"{r['rounds']} vòng · dừng: {r['stop_reason'] or '—'} · {r['llm_calls']} lần gọi Qwen"
                  f" · {r['elapsed_ms'] / 1000:.1f} s" + (f" · trọng tâm {r['focus']}" if r['focus'] else ''),
                  '', '### Câu trả lời', '', r['answer'], '', '### Các ý cần biết', '']
        for n in r['needs']:
            lines.append(f"- **{n['id']}** [{NEED_LABELS[n['status']]}] ({n['kind']}"
                         + (f", {n['school']}" if n['school'] else '') + f") {n['text']}")
            for q in n['quotes'][:3]:
                lines.append(f"  - [{q['handle']}] “{q['quote'][:240]}”")
        if r['dropped']:
            lines += ['', '### Nhận định bị loại', '']
            lines += [f"- ({d['reason']}) {d['text']}" for d in r['dropped']]
        lines += ['', '### Đoạn sách đã xem', '']
        lines += [f"- [{s['handle']}]{' ✓' if s['cited'] else ''} {s['book']} {s['pages']}".rstrip()
                  for s in r['sources']]
        lines.append('')
    return '\n'.join(lines)


def write_run(results: list[tuple[str, Result]], config: Config, out_dir: Path,
              run_id: str | None = None) -> tuple[Path, Path]:
    run_id = run_id or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run = {'run_id': run_id, 'prompt_version': results[0][1].prompt_version if results else '',
           'config': {k: v for k, v in vars(config).items()},
           'results': [{'id': n, 'result': r.to_dict()} for n, r in results]}
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = out_dir / f'run-{run_id}.json', out_dir / f'run-{run_id}.md'
    json_path.write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding='utf-8')
    md_path.write_text(markdown(run), encoding='utf-8')
    return json_path, md_path


def run_all(harness: Harness, questions: list[tuple[str, str]], echo=print,
            on_result=None) -> list[tuple[str, Result]]:
    out = []
    for n, q in questions:
        result = harness.answer(q)
        echo(f'{n}: {result.status} · {result.rounds} vòng · {result.llm_calls} lần gọi'
             f' · {result.elapsed_ms / 1000:.1f} s')
        if on_result:
            on_result(n, result)
        out.append((n, result))
    return out


def judge_payload(result: Result, parents: dict, children: dict, usage: list[dict],
                  settings: dict, versions: dict) -> dict:
    """One result in the /judge page's ``AskOut`` shape. ``parents``/``children``: what
    ``RagRetriever`` saw for this question (ParentOut by parent id, ChildOut by chunk id)."""
    handle_of = {s['pid']: s['handle'] for s in result.sources}
    parents_out = [{**parents[s['pid']].model_dump(), 'handle': s['handle'], 'cited': s['cited']}
                   for s in result.sources if s['pid'] in parents]
    children_out = []
    for child in children.values():
        handle = handle_of.get(child.meta.get('parent_id'))
        if handle:
            children_out.append({**child.model_dump(), 'rank': len(children_out) + 1,
                                 'parent_handle': handle})
    data = result.to_dict()
    return {
        'status': result.status, 'question': result.question,
        'answer': CITES.sub(lambda m: ''.join(f'[{h.strip()}]' for h in m.group(1).split(',')),
                            result.answer),
        'cited': [s['handle'] for s in result.sources if s['cited']], 'invalid_citations': [],
        'parents': parents_out, 'children': children_out, 'degraded': [],
        'settings': settings, 'versions': versions, 'timings_ms': {'total': result.elapsed_ms},
        'usage': {'prompt_tokens': sum(u['prompt_tokens'] or 0 for u in usage),
                  'completion_tokens': sum(u['completion_tokens'] or 0 for u in usage),
                  'calls': len(usage)},
        'harness': {k: data[k] for k in HARNESS_KEYS}}


def publish(engine, user_id, label: str, questions_file: str, results: list[tuple[str, Result]],
            payloads: dict[str, dict], settings: dict, versions: dict) -> dict:
    from ..core.db import transaction
    from ..judging.service import create_run
    body = {'label': label, 'questions_file': questions_file, 'settings': settings,
            'versions': versions,
            'results': [{'ordinal': i, 'question_key': n, 'question': r.question,
                         'latency_ms': r.elapsed_ms, 'payload': payloads[n]}
                        for i, (n, r) in enumerate(results, start=1)]}
    with transaction(engine, user_id) as conn:
        return create_run(conn, user_id, body)


def _live(as_user: str):
    """Qwen + RAG retrieval from the environment (needs the models and the database)."""
    import uuid

    from sqlalchemy import create_engine, pool, text

    from ..auth.service import Principal
    from ..core.config import load_settings
    from ..rag.llm import config_from
    from ..rag.models import embedder, embedder_spec, reranker, reranker_spec
    from ..rag.service import RagService, SparseCache
    from .adapters import QwenModel, RagRetriever
    from .glossary_index import GlossaryIndex
    settings = load_settings()
    config = config_from(settings)
    if config is None:
        raise SystemExit('LLM_BASE_URL / LLM_MODEL are not configured')
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    with engine.begin() as conn:
        user = conn.execute(text('SELECT id, email, role FROM users WHERE email = :e AND enabled'),
                            {'e': as_user}).mappings().first()
    if user is None:
        raise SystemExit(f'no enabled user {as_user}')
    principal = Principal(user['id'], user['email'], user['role'], uuid.UUID(int=0), '')
    service = RagService(engine, settings, None, SparseCache(), embedder(embedder_spec(settings)),
                         reranker(reranker_spec(settings)) if settings.rag_rerank_depth else None)
    s = settings
    run = {'engine': engine, 'user_id': user['id'],
           'settings': {'dense_weight': s.rag_dense_weight, 'sparse_weight': s.rag_sparse_weight,
                        'dense_candidates': s.rag_dense_candidates,
                        'sparse_candidates': s.rag_sparse_candidates,
                        'rerank_depth': s.rag_rerank_depth, 'rerank_chars': s.rag_rerank_chars,
                        'context_tokens': None, 'thinking': False, 'pipeline': 'answering-harness'},
           'versions': {'llm': config.model,
                        'embedder': f'{s.rag_embedding_model}@{s.rag_embedding_revision[:12]}',
                        'reranker': f'{s.rag_reranker_model}@{s.rag_reranker_revision[:12]}'}}
    return QwenModel(config, thinking_steps=frozenset()), RagRetriever(service, principal), \
        GlossaryIndex.load(), run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m backend.app.answering.run')
    parser.add_argument('questions', type=Path)
    parser.add_argument('--as', dest='as_user', required=True, help='user whose library is searched')
    parser.add_argument('--only', nargs='*', help='question numbers')
    parser.add_argument('--max-rounds', type=int, default=7)
    parser.add_argument('--time-budget', type=float, help='seconds per question (default: none)')
    parser.add_argument('--out', type=Path, default=Path('.artifacts/answering'))
    parser.add_argument('--publish', metavar='LABEL', help='also store the run for the /judge page')
    args = parser.parse_args(argv)
    questions = parse_questions(args.questions.read_text(encoding='utf-8'))
    if args.only:
        questions = [(n, q) for n, q in questions if n in set(args.only)]
    model, retriever, glossary, live = _live(args.as_user)
    config = Config(max_rounds=args.max_rounds, time_budget_s=args.time_budget)
    settings = {**live['settings'], **{k: v for k, v in vars(config).items() if k != 'tokens'}}
    payloads: dict[str, dict] = {}
    seen_usage = 0

    def keep(n: str, result: Result) -> None:
        nonlocal seen_usage
        payloads[n] = judge_payload(result, retriever.seen_parents, retriever.seen_children,
                                    model.usage[seen_usage:], settings,
                                    {**live['versions'], 'answer_prompt': result.prompt_version})
        seen_usage = len(model.usage)
        retriever.reset()

    try:
        results = run_all(Harness(model, retriever, glossary, config), questions, on_result=keep)
    finally:
        model.close()
    json_path, md_path = write_run(results, config, args.out)
    print(f'{json_path}\n{md_path}')
    if args.publish and results:
        created = publish(live['engine'], live['user_id'], args.publish, args.questions.name,
                          results, payloads, settings,
                          {**live['versions'], 'answer_prompt': results[0][1].prompt_version})
        print(f"judge run {created['id']} ({created['results']} results)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
