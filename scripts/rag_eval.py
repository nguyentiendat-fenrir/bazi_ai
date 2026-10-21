"""Ask the RAG pilot every test question, save what it answered and retrieved, publish for judges.

  python scripts/rag_eval.py run   [--api URL] [--questions FILE] [--only 3 7 ...] [--thinking]
                                   [--label TEXT] [--no-publish]
  python scripts/rag_eval.py report RESULT.json        # (re)write the Markdown report

Stdlib only. Signs in with an app account that has the reviewer role
(``BAZI_EVAL_EMAIL`` / ``BAZI_EVAL_PASSWORD``, else prompted), calls
``POST /api/v1/ask`` per question, and writes to ``.artifacts/rag_eval/``:

* ``run-<ts>.json`` — every answer with the full retrieval snapshot (parents sent
  to the model, retrieved children with dense/sparse/fused/rerank scores);
* ``run-<ts>.md``   — the same, readable: question → answer → sources → chunks.

Unless ``--no-publish``, the run is then posted to ``/api/v1/eval-runs`` so it
appears on the judging page (``/judge``, shared judge password).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import http.cookiejar
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / '.artifacts/rag_eval'
DEFAULT_QUESTIONS = ROOT / 'test_questions.txt'
NUMBERED = re.compile(r'^\s*(\d{1,3})[.)]\s+(.*)$')


def parse_questions(text: str) -> list[dict]:
    """Numbered questions ("1. …"); a question may continue over several lines."""
    questions: list[dict] = []
    for line in text.splitlines():
        match = NUMBERED.match(line)
        if match:
            questions.append({'key': match.group(1), 'question': match.group(2).strip()})
        elif line.strip() and questions:
            questions[-1]['question'] += ' ' + line.strip()
    return questions


class LoopbackPolicy(http.cookiejar.DefaultCookiePolicy):
    """Send Secure cookies to loopback over plain HTTP, as browsers do for localhost."""

    def return_ok_secure(self, cookie, request):
        host = urllib.parse.urlsplit(request.get_full_url()).hostname
        return host in ('127.0.0.1', 'localhost', '::1') or super().return_ok_secure(cookie, request)


class Client:
    def __init__(self, api: str, timeout: float):
        self.api = api.rstrip('/')
        self.timeout = timeout
        self.csrf: str | None = None
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(
            http.cookiejar.CookieJar(policy=LoopbackPolicy())))

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if self.csrf and method != 'GET':
            headers['X-CSRF-Token'] = self.csrf
        request = urllib.request.Request(
            self.api + path, method=method, headers=headers,
            data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode('utf-8') or '{}')
        except urllib.error.HTTPError as error:
            detail = error.read().decode('utf-8', 'replace')[:500]
            raise RuntimeError(f'{method} {path} → HTTP {error.code}: {detail}') from None

    def login(self, email: str, password: str) -> None:
        result = self.call('POST', '/api/v1/auth/login', {'email': email, 'password': password})
        self.csrf = result['data']['csrf_token']


def run(args) -> int:
    questions = parse_questions(Path(args.questions).read_text(encoding='utf-8'))
    if args.only:
        questions = [q for q in questions if q['key'] in set(args.only)]
    if not questions:
        print('No questions found.')
        return 1
    client = Client(args.api, args.timeout)
    email = os.environ.get('BAZI_EVAL_EMAIL') or input('Reviewer email: ')
    password = os.environ.get('BAZI_EVAL_PASSWORD') or getpass.getpass('Password: ')
    client.login(email, password)

    started = datetime.now(timezone.utc)
    record = {'run_id': started.strftime('%Y%m%dT%H%M%SZ'), 'created_at': started.isoformat(),
              'api': args.api, 'questions_file': Path(args.questions).name,
              'label': args.label or f'{Path(args.questions).name} · {started:%Y-%m-%d %H:%M} UTC',
              'settings': {}, 'versions': {}, 'results': []}
    for number, question in enumerate(questions, 1):
        print(f"[{number}/{len(questions)}] câu {question['key']} …", end=' ', flush=True)
        begin = time.perf_counter()
        body = {'question': question['question']}
        if args.thinking:
            body['thinking'] = True
        try:
            payload = client.call('POST', '/api/v1/ask', body)['data']
        except (RuntimeError, urllib.error.URLError, TimeoutError) as error:
            payload = {'status': 'request_failed', 'question': question['question'],
                       'error': str(error)[:500], 'parents': [], 'children': []}
        latency = int((time.perf_counter() - begin) * 1000)
        record['settings'] = record['settings'] or payload.get('settings') or {}
        record['versions'] = record['versions'] or payload.get('versions') or {}
        record['results'].append({'ordinal': number, 'question_key': question['key'],
                                  'question': question['question'], 'latency_ms': latency,
                                  'payload': payload})
        print(f"{payload.get('status')} · {len(payload.get('parents', []))} nguồn ·"
              f" {len(payload.get('children', []))} đoạn · {latency / 1000:.1f} s")

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"run-{record['run_id']}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    report_path = out.with_suffix('.md')
    report_path.write_text(report(record), encoding='utf-8')
    print(f'Saved {out.relative_to(ROOT)} and {report_path.relative_to(ROOT)}')

    if not args.no_publish:
        created = client.call('POST', '/api/v1/eval-runs', {
            'label': record['label'], 'questions_file': record['questions_file'],
            'settings': record['settings'], 'versions': record['versions'],
            'results': record['results']})['data']
        print(f"Published run {created['id']} ({created['results']} câu) — chấm tại /judge")
    return 0 if all(r['payload'].get('status') != 'request_failed' for r in record['results']) else 1


def _pages(item: dict) -> str:
    start, end = item.get('page_start'), item.get('page_end')
    if not start:
        return ''
    return f'tr. {start}–{end}' if end and end != start else f'tr. {start}'


def _num(value, digits: int = 3) -> str:
    return f'{value:.{digits}f}' if isinstance(value, (int, float)) else '—'


def report(record: dict) -> str:
    s, v = record.get('settings') or {}, record.get('versions') or {}
    lines = [f"# Kết quả RAG — {record['label']}", '',
             f"- Chạy lúc: {record['created_at']} · API: {record['api']}",
             f"- Trộn: {s.get('dense_weight')}·dense + {s.get('sparse_weight')}·sparse ·"
             f" rerank depth {s.get('rerank_depth')} · ngữ cảnh {s.get('context_tokens')} token ·"
             f" thinking {s.get('thinking')}",
             f"- LLM {v.get('llm')} · embedder {v.get('embedder')} · reranker {v.get('reranker')} ·"
             f" prompt {v.get('answer_prompt')}", '']
    for result in record['results']:
        p = result['payload']
        lines += ['---', '', f"## Câu {result['question_key']}. {result['question']}", '',
                  f"**Trạng thái:** {p.get('status')} · {result['latency_ms'] / 1000:.1f} s"
                  + (f" · suy giảm: {', '.join(p['degraded'])}" if p.get('degraded') else ''), '',
                  '### Câu trả lời', '', p.get('answer') or f"_(không có — {p.get('error') or p.get('status')})_", '']
        if p.get('invalid_citations'):
            lines += [f"> Mã nguồn không hợp lệ đã bỏ: {', '.join(p['invalid_citations'])}", '']
        lines += ['### Nguồn đưa cho mô hình', '']
        for parent in p.get('parents', []):
            mark = '✅ được trích' if parent.get('cited') else '— không trích'
            lines += [f"**[{parent['handle']}]** {parent['book_title']} · "
                      f"{' › '.join(parent.get('breadcrumb') or [])} · {_pages(parent)} · {mark}"
                      + (' · có quy tắc đã duyệt' if parent.get('expert_reviewed') else ''), '']
            if parent.get('summary'):
                lines += [f"> _Tóm tắt:_ {parent['summary']}", '']
            lines += ['<details><summary>Toàn văn</summary>', '', parent['text'], '', '</details>', '']
        lines += ['### Đoạn truy xuất', '',
                  '| # | Sách · mục · trang | dense | sparse | trộn | rerank | nguồn |',
                  '|---|---|---|---|---|---|---|']
        for child in p.get('children', []):
            sc = child.get('scores') or {}
            where = f"{child['book_title']} · {' › '.join(child.get('breadcrumb') or [])} · {_pages(child)}"
            lines.append(f"| {child['rank']} | {where.replace('|', '/')} | {_num(sc.get('dense'))} |"
                         f" {_num(sc.get('sparse'))} | {_num(sc.get('fused'))} | {_num(sc.get('rerank'))} |"
                         f" {child.get('parent_handle') or ''} |")
        lines.append('')
    return '\n'.join(lines)


def main(argv=None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    run_cmd = commands.add_parser('run', help='ask every question, save and publish the run')
    run_cmd.add_argument('--api', default=os.environ.get('BAZI_API', 'http://127.0.0.1:3000'))
    run_cmd.add_argument('--questions', default=str(DEFAULT_QUESTIONS))
    run_cmd.add_argument('--only', nargs='*', help='question numbers to run')
    run_cmd.add_argument('--thinking', action='store_true', help='let Qwen think before answering')
    run_cmd.add_argument('--label', help='name shown on the judging page')
    run_cmd.add_argument('--timeout', type=float, default=600)
    run_cmd.add_argument('--no-publish', action='store_true', help='only save files locally')
    report_cmd = commands.add_parser('report', help='write the Markdown report of a saved run')
    report_cmd.add_argument('file')
    args = parser.parse_args(argv)
    if args.command == 'report':
        path = Path(args.file)
        path.with_suffix('.md').write_text(report(json.loads(path.read_text(encoding='utf-8'))),
                                           encoding='utf-8')
        print(f'Wrote {path.with_suffix(".md")}')
        return 0
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
