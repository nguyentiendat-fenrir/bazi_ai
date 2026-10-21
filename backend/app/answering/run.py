"""Run a question file through the harness with Qwen and the RAG pilot retrieval.

    python -m backend.app.answering.run test_questions.txt --as reviewer@example.test
    python -m backend.app.answering.run test_questions.txt --as r@x --only 13 18 --time-budget 240

Writes ``.artifacts/answering/run-<UTC>.json`` (every result with its trace, for the judge
page and for comparing runs) and ``run-<UTC>.md`` (answers, needs and sources to read).
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


def run_all(harness: Harness, questions: list[tuple[str, str]], echo=print) -> list[tuple[str, Result]]:
    out = []
    for n, q in questions:
        result = harness.answer(q)
        echo(f'{n}: {result.status} · {result.rounds} vòng · {result.llm_calls} lần gọi'
             f' · {result.elapsed_ms / 1000:.1f} s')
        out.append((n, result))
    return out


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
    return QwenModel(config, thinking_steps=frozenset()), RagRetriever(service, principal), \
        GlossaryIndex.load()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m backend.app.answering.run')
    parser.add_argument('questions', type=Path)
    parser.add_argument('--as', dest='as_user', required=True, help='user whose library is searched')
    parser.add_argument('--only', nargs='*', help='question numbers')
    parser.add_argument('--max-rounds', type=int, default=7)
    parser.add_argument('--time-budget', type=float, help='seconds per question (default: none)')
    parser.add_argument('--out', type=Path, default=Path('.artifacts/answering'))
    args = parser.parse_args(argv)
    questions = parse_questions(args.questions.read_text(encoding='utf-8'))
    if args.only:
        questions = [(n, q) for n, q in questions if n in set(args.only)]
    model, retriever, glossary = _live(args.as_user)
    config = Config(max_rounds=args.max_rounds, time_budget_s=args.time_budget)
    try:
        results = run_all(Harness(model, retriever, glossary, config), questions)
    finally:
        model.close()
    json_path, md_path = write_run(results, config, args.out)
    print(f'{json_path}\n{md_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
