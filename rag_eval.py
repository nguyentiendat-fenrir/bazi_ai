"""Run the pilot RAG question set against the API and browse saved results.

  python scripts/rag_eval.py run  [--api URL] [--mode hybrid|dense] [--top-k 8] [--only ID ...]
  python scripts/rag_eval.py view [RESULT.json]   # opens a Tkinter window

Stdlib only. Results go to .artifacts/rag_eval/ (git-ignored); each result keeps the
final answer (null when no LLM is configured) and every retrieved chunk.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / 'tests/rag_eval/questions.json'
RESULTS = ROOT / '.artifacts/rag_eval'
SCHOOLS = {'manh_phai': 'Manh phái', 'vuong_suy': 'Tử Bình/vượng suy'}


def call(api: str, method: str, path: str, body: dict | None = None, timeout: float = 600) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(api.rstrip('/') + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def run(args) -> int:
    questions = json.loads(QUESTIONS.read_text(encoding='utf-8'))['questions']
    if args.only:
        questions = [q for q in questions if q['id'] in set(args.only)]
    models = call(args.api, 'GET', '/api/v1/models')
    started = datetime.now(timezone.utc)
    record = {'run_id': started.strftime('%Y%m%dT%H%M%SZ'), 'created_at': started.isoformat(),
              'api': args.api, 'questions_file': QUESTIONS.relative_to(ROOT).as_posix(),
              'settings': {'mode': args.mode, 'top_k': args.top_k, **models}, 'results': []}
    for number, question in enumerate(questions, 1):
        print(f'[{number}/{len(questions)}] {question["id"]} ...', end=' ', flush=True)
        begin = time.perf_counter()
        try:
            reply = call(args.api, 'POST', '/api/v1/ask',
                         {'question': question['question'], 'top_k': args.top_k, 'mode': args.mode})
        except (urllib.error.URLError, TimeoutError) as error:
            reply = {'status': 'request_failed', 'answer': None, 'chunks': [], 'error': str(error)}
        latency = int((time.perf_counter() - begin) * 1000)
        record['results'].append({**question, 'status': reply.get('status'),
                                  'answer': reply.get('answer'), 'provider': reply.get('provider'),
                                  'model': reply.get('model'), 'error': reply.get('error'),
                                  'cited_chunk_ids': reply.get('cited_chunk_ids', []),
                                  'invalid_citations': reply.get('invalid_citations', []),
                                  'latency_ms': latency, 'chunks': reply.get('chunks', [])})
        print(f'{reply.get("status")} · {len(reply.get("chunks", []))} chunks · {latency} ms')
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f'run-{record["run_id"]}-{args.mode}.json'
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Saved {out.relative_to(ROOT).as_posix()}')
    return 0 if all(r['status'] != 'request_failed' for r in record['results']) else 1


def pages(chunk: dict) -> str:
    if chunk.get('page_start'):
        end = chunk.get('page_end')
        return f'tr. {chunk["page_start"]}' + (f'–{end}' if end and end != chunk['page_start'] else '')
    return f'mục {chunk["section_path"]}' if chunk.get('section_path') else ''


def score(value) -> str:
    return f'{value:.4f}' if isinstance(value, (int, float)) else '-'


class Viewer:
    """Tkinter browser: result file → question → answer, chunk table and full chunk text."""

    def __init__(self, root, files: list[Path]):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.root, self.files = tk, root, files
        self.data: dict = {}
        self.result: dict = {}
        self.font = ('Segoe UI', 10)
        root.title('BaZi RAG eval viewer')
        root.geometry('1400x860')
        ttk.Style().configure('Treeview', rowheight=24)

        top = ttk.Frame(root, padding=(8, 8, 8, 0))
        top.pack(fill='x')
        ttk.Label(top, text='Result file:').pack(side='left')
        self.file_box = ttk.Combobox(top, state='readonly', width=50, values=[p.name for p in files])
        self.file_box.pack(side='left', padx=6)
        self.file_box.bind('<<ComboboxSelected>>', lambda _: self.load(self.file_box.current()))
        ttk.Button(top, text='Open…', command=self.open_file).pack(side='left')
        self.run_info = ttk.Label(top, foreground='#555')
        self.run_info.pack(side='left', padx=12)

        panes = ttk.PanedWindow(root, orient='horizontal')
        panes.pack(fill='both', expand=True, padx=8, pady=8)

        left = ttk.Frame(panes)
        self.questions = ttk.Treeview(left, columns=('status', 'chunks'), show='tree headings',
                                      selectmode='browse')
        for column, label, width in (('#0', 'Question', 230), ('status', 'Status', 160),
                                     ('chunks', 'Chunks', 55)):
            self.questions.heading(column, text=label)
            self.questions.column(column, width=width, anchor='w' if column == '#0' else 'center')
        self.questions.pack(fill='both', expand=True)
        self.questions.bind('<<TreeviewSelect>>', lambda _: self.show_question())
        panes.add(left, weight=1)

        right = ttk.PanedWindow(panes, orient='vertical')
        panes.add(right, weight=3)
        head = ttk.Frame(right, padding=4)
        self.question_text = self.text_box(head, 3, self.font + ('bold',))
        self.meta = ttk.Label(head, foreground='#555')
        self.meta.pack(anchor='w', pady=(4, 2))
        ttk.Label(head, text='Answer').pack(anchor='w')
        self.answer_text = self.text_box(head, 8, self.font, expand=True)
        right.add(head, weight=2)

        middle = ttk.Frame(right, padding=4)
        columns = (('rank', 45), ('title', 330), ('where', 150), ('school', 130),
                   ('extraction', 80), ('fused', 70), ('rerank', 70), ('cited', 50))
        self.chunks = ttk.Treeview(middle, columns=[c for c, _ in columns], show='headings',
                                   height=8, selectmode='browse')
        for column, width in columns:
            self.chunks.heading(column, text=column.capitalize())
            self.chunks.column(column, width=width,
                               anchor='w' if column in ('title', 'where') else 'center')
        self.chunks.pack(fill='both', expand=True)
        self.chunks.bind('<<TreeviewSelect>>', lambda _: self.show_chunk())
        right.add(middle, weight=1)

        bottom = ttk.Frame(right, padding=4)
        self.chunk_title = ttk.Label(bottom, foreground='#555')
        self.chunk_title.pack(anchor='w')
        self.chunk_text = self.text_box(bottom, 10, self.font, expand=True)
        right.add(bottom, weight=2)

        if files:
            self.file_box.current(0)
            self.load(0)
        else:
            self.run_info.configure(text=f'No result files in {RESULTS} — run: python scripts/rag_eval.py run')

    def text_box(self, parent, height: int, font, expand: bool = False):
        from tkinter import ttk
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=expand)
        box = self.tk.Text(frame, height=height, wrap='word', font=font, relief='flat',
                           padx=8, pady=6, background='#fbfbfb')
        bar = ttk.Scrollbar(frame, command=box.yview)
        box.configure(yscrollcommand=bar.set, state='disabled')
        bar.pack(side='right', fill='y')
        box.pack(side='left', fill='both', expand=True)
        return box

    @staticmethod
    def set_text(box, text: str) -> None:
        box.configure(state='normal')
        box.delete('1.0', 'end')
        box.insert('1.0', text)
        box.configure(state='disabled')

    def open_file(self) -> None:
        from tkinter import filedialog
        name = filedialog.askopenfilename(initialdir=RESULTS, filetypes=[('Result JSON', '*.json')])
        if not name:
            return
        path = Path(name).resolve()
        if path not in self.files:
            self.files.insert(0, path)
            self.file_box.configure(values=[p.name for p in self.files])
        index = self.files.index(path)
        self.file_box.current(index)
        self.load(index)

    def load(self, index: int) -> None:
        from tkinter import messagebox
        try:
            self.data = json.loads(self.files[index].read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            messagebox.showerror('Cannot read result file', str(error))
            return
        settings = self.data.get('settings', {})
        llm = settings.get('llm') or {}
        self.run_info.configure(text=f'run {self.data.get("run_id")} · mode {settings.get("mode")} · '
                                     f'top_k {settings.get("top_k")} · LLM {llm.get("provider", "none")}')
        self.questions.delete(*self.questions.get_children())
        for i, result in enumerate(self.data.get('results', [])):
            self.questions.insert('', 'end', iid=str(i), text=result['id'],
                                  values=(result.get('status'), len(result.get('chunks', []))))
        if self.data.get('results'):
            self.questions.selection_set('0')

    def show_question(self) -> None:
        selected = self.questions.selection()
        if not selected:
            return
        result = self.result = self.data['results'][int(selected[0])]
        self.set_text(self.question_text, result['question'])
        meta = (f'{result["id"]} · {result.get("category")} · status {result.get("status")} · '
                f'provider {result.get("provider") or "-"} · model {result.get("model") or "-"} · '
                f'{result.get("latency_ms")} ms')
        if result.get('expected_sources'):
            meta += '\nExpected sources (hint): ' + '; '.join(result['expected_sources'])
        self.meta.configure(text=meta)
        answer = result.get('answer') or f'(no answer — {result.get("error") or result.get("status")})'
        if result.get('invalid_citations'):
            answer += '\n\n! Citations outside the retrieved set: ' + ', '.join(result['invalid_citations'])
        self.set_text(self.answer_text, answer)
        cited = set(result.get('cited_chunk_ids', []))
        self.chunks.delete(*self.chunks.get_children())
        for i, chunk in enumerate(result.get('chunks', [])):
            self.chunks.insert('', 'end', iid=str(i), values=(
                chunk.get('rank'), chunk.get('title'), pages(chunk),
                SCHOOLS.get(chunk.get('school'), chunk.get('school')), chunk.get('extraction'),
                score(chunk.get('fused_score')), score(chunk.get('rerank_score')),
                '✓' if chunk.get('chunk_id') in cited else ''))
        if result.get('chunks'):
            self.chunks.selection_set('0')
        else:
            self.chunk_title.configure(text='')
            self.set_text(self.chunk_text, '')

    def show_chunk(self) -> None:
        selected = self.chunks.selection()
        if not selected:
            return
        chunk = self.result['chunks'][int(selected[0])]
        self.chunk_title.configure(text=f'#{chunk.get("rank")} {chunk.get("title")} · {pages(chunk)} · '
                                        f'{chunk.get("word_count", "?")} words · {chunk.get("chunk_id")}')
        self.set_text(self.chunk_text, chunk.get('text', ''))


def view(args) -> int:
    files = [Path(args.file).resolve()] if args.file else sorted(RESULTS.glob('*.json'), reverse=True)
    try:
        import tkinter as tk
        root = tk.Tk()
    except Exception as error:  # no display (SSH/container) or Python built without Tk
        print(f'Cannot open the viewer window: {error}')
        return 1
    Viewer(root, files)
    root.mainloop()
    return 0


def main(argv=None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    run_cmd = commands.add_parser('run', help='ask every question and save a result file')
    run_cmd.add_argument('--api', default='http://127.0.0.1:8000')
    run_cmd.add_argument('--mode', choices=('hybrid', 'dense'), default='hybrid')
    run_cmd.add_argument('--top-k', type=int, default=8, choices=range(1, 21), metavar='1..20')
    run_cmd.add_argument('--only', nargs='*', help='question ids to run')
    view_cmd = commands.add_parser('view', help='browse result files in a window')
    view_cmd.add_argument('file', nargs='?')
    args = parser.parse_args(argv)
    return run(args) if args.command == 'run' else view(args)


if __name__ == '__main__':
    sys.exit(main())
