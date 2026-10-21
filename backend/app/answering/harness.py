"""The answering loop (steps 3–8). See the package docstring for the flow."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
import time

from ..calc import pillar_facts
from ..calc.tables import BRANCH_LABELS, STEM_LABELS, TEN_GOD_LABELS
from ..documents.text import fold, nfc
from . import prompts, schemas, verify
from .glossary_index import GlossaryIndex
from .ports import SCHOOL_LABELS, SCHOOLS, Model, ModelError, Passage, Retriever

RANK = {'thieu': 0, 'mot_phan': 1, 'du': 2, 'mau_thuan': 2}
DONE = ('du', 'mau_thuan')
REFUSAL = ('Không thể trả lời chắc chắn về sinh tử, bệnh tật, tai nạn hay hôn nhân của một người.'
           ' Mệnh lý là hệ diễn giải truyền thống, không phải dự báo; sách chỉ cho biết cách các'
           ' trường phái luận cấu trúc lá số.')
_TU_BINH = re.compile(r'tử bình|trích thiên t[ủu]y|chân thuyên|nhậm thiết tiều|từ nhạc ngô', re.I)
_MANH_PHAI = re.compile(r'manh phái', re.I)


@dataclass
class Config:
    max_rounds: int = 7
    k: int = 4                       # passages per query
    passage_chars: int = 2500        # per passage in a prompt
    max_needs: int = 10
    max_concepts: int = 4
    max_luck: int = 3
    time_budget_s: float | None = None
    min_support: float = 0.5
    decompose_min_chars: int = 100   # shorter single questions skip ①
    tokens: dict = field(default_factory=lambda: {'decompose': 400, 'judge': 900, 'rewrite': 200,
                                                  'branch': 1500, 'synthesize': 1800})


@dataclass
class Need:
    id: str
    text: str
    kind: str                        # concept | sub | analysis | main
    school: str | None
    query: str
    status: str = 'thieu'
    quotes: list[dict] = field(default_factory=list)   # {handle, pid, quote}
    missing: str = ''
    tried: list[str] = field(default_factory=list)
    seen: set[str] = field(default_factory=set)
    stalled: bool = False


@dataclass
class Result:
    question: str
    status: str                      # ok | partial | insufficient | no_evidence | refused | model_error
    answer: str
    claims: list[dict]
    dropped: list[dict]
    needs: list[dict]
    sources: list[dict]
    facts: str | None
    focus: str | None
    agreement: str
    stop_reason: str | None
    rounds: int
    llm_calls: int
    elapsed_ms: int
    trace: list[dict]
    prompt_version: str = prompts.PROMPT_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


class Harness:
    def __init__(self, model: Model, retriever: Retriever, glossary: GlossaryIndex | None = None,
                 config: Config | None = None, clock=time.monotonic):
        self.model, self.retriever, self.glossary = model, retriever, glossary
        self.config, self.clock = config or Config(), clock

    # ---- public ------------------------------------------------------------------------------
    def answer(self, question: str) -> Result:
        run = _Run(self, ' '.join(nfc(question).split()))
        return run.go()


class _Run:
    """State of one question."""

    def __init__(self, harness: Harness, question: str):
        self.h, self.c, self.q = harness, harness.config, question
        self.started = harness.clock()
        self.trace: list[dict] = []
        self.calls = 0
        self.handles: dict[str, str] = {}          # pid -> P#
        self.passages: dict[str, Passage] = {}     # P# -> passage
        self.chart = pillar_facts.find_chart(question)
        self.facts_data = pillar_facts.facts(self.chart) if self.chart else None
        self.facts = pillar_facts.render(self.facts_data) if self.chart else None
        self.focus = _focus(question)
        self.stop_reason: str | None = None
        self.rounds = 0

    # ---- helpers -------------------------------------------------------------------------------
    def elapsed(self) -> float:
        return self.h.clock() - self.started

    def out_of_time(self) -> bool:
        return self.c.time_budget_s is not None and self.elapsed() >= self.c.time_budget_s

    def call(self, step: str, messages: list[dict], schema):
        self.calls += 1
        began = self.h.clock()
        result = self.h.model.structured(step, messages, schema, self.c.tokens[step])
        self.trace.append({'step': f'llm.{step}', 'ms': int((self.h.clock() - began) * 1000)})
        return result

    def handle(self, p: Passage) -> str:
        if p.pid not in self.handles:
            self.handles[p.pid] = f'P{len(self.handles) + 1}'
            self.passages[self.handles[p.pid]] = p
        return self.handles[p.pid]

    # ---- flow ----------------------------------------------------------------------------------
    def go(self) -> Result:
        if verify.risky_question(self.q):
            self.trace.append({'step': 'guard', 'decision': 'refused'})
            return self.result('refused', REFUSAL, [], [], [], 'khong_ap_dung')
        if verify.injection(self.q):
            self.trace.append({'step': 'guard', 'decision': 'injection_ignored'})
        if self.facts_data and self.facts_data['warnings']:
            self.trace.append({'step': 'chart', 'warnings': self.facts_data['warnings']})
        try:
            needs = self.plan()
            self.evidence(needs)
            branches = self.analyse(needs) if self.chart else {}
            return self.synthesize(needs, branches)
        except ModelError as exc:
            self.trace.append({'step': 'error', 'code': exc.code})
            self.needs = getattr(self, 'needs', [])
            return self.result('model_error', f'Mô hình lỗi ({exc.code}); chưa có câu trả lời.',
                               [], [], self.needs, 'khong_ap_dung')

    # ---- ① plan ------------------------------------------------------------------------------
    def plan(self) -> list[Need]:
        needs: list[Need] = []

        def add(text, kind, school, query=None):
            if any(fold(n.text) == fold(text) for n in needs):
                return
            needs.append(Need(f'N{len(needs) + 1}', text, kind, school, query or text))

        add(self.q, 'main', self.focus)
        if self.h.glossary is not None:
            for term in self.h.glossary.find(self.q)[:self.c.max_concepts]:
                school = term.school or self.focus
                where = f' theo {SCHOOL_LABELS[school]}' if school else ''
                add(f'{term.label} là gì{where}?', 'concept', school, f'{term.label} là gì')
        if self.chart or self.q.count('?') > 1 or len(self.q) > self.c.decompose_min_chars:
            plan = self.call('decompose', prompts.decompose(self.q, self.facts), schemas.Decomposition)
            for sub in plan.sub_questions:
                if sub.strip():
                    add(nfc(sub).strip(), 'sub', self.focus)
        if self.chart:
            for text, school, query in self.analysis_needs():
                add(text, 'analysis', school, query)
        keep = [n for n in needs if n.kind in ('main', 'analysis')]
        rest = [n for n in needs if n.kind not in ('main', 'analysis')]
        self.needs = (keep + rest)[:self.c.max_needs]
        self.needs.sort(key=lambda n: int(n.id[1:]))
        self.trace.append({'step': 'plan', 'needs': [
            {'id': n.id, 'kind': n.kind, 'school': n.school, 'text': n.text} for n in self.needs]})
        return self.needs

    def analysis_needs(self) -> list[tuple[str, str, str]]:
        f = self.facts_data
        dm = STEM_LABELS[f['day_master']['stem']]
        mc = BRANCH_LABELS[f['month_command']['branch']]
        mq = STEM_LABELS[f['month_command']['main_qi']]
        tg = TEN_GOD_LABELS[f['month_command']['main_qi_ten_god']]
        relations = ' '.join(r['type'].split(' (')[0] for r in f['relations'][:3])
        out = [
            (f'Theo Tử Bình, Nhật chủ {dm} sinh tháng {mc} vượng hay suy, căn cứ thế nào? (B3)',
             'tu_binh', f'{dm} sinh tháng {mc} vượng suy thông căn đắc lệnh'),
            (f'Theo Tử Bình, Nhật chủ {dm} tháng {mc} (chủ khí {mq} là {tg}) lấy cách cục và dụng'
             ' thần thế nào? (B4)', 'tu_binh', f'{dm} sinh tháng {mc} {tg} cách cục dụng thần'),
            (f'Theo Manh phái, lá số Nhật chủ {dm} tháng {mc} tố công thế nào (khách chủ, thể dụng,'
             ' chế)? (B5)', 'manh_phai', f'tố công {relations} {dm} {mc}'),
        ]
        lucks = self.asked_luck()
        if lucks:
            names = ', '.join(lucks)
            for school in SCHOOLS:
                out.append((f'Theo {SCHOOL_LABELS[school]}, các vận {names} tác động lên lá số Nhật'
                            f' chủ {dm} tháng {mc} thế nào? (B7)', school, f'vận {names} {dm}'))
        return out

    def asked_luck(self) -> list[str]:
        """Luck pillars of the chart that the question asks about ("vận Ngọ", "vận Ất Tỵ")."""
        folded = fold(self.q)
        out = []
        for stem, branch in self.chart.luck:
            full, short = f'{STEM_LABELS[stem]} {BRANCH_LABELS[branch]}', BRANCH_LABELS[branch]
            for name in (full, short):
                if re.search(rf'\bvan {re.escape(fold(name))}\b', folded) and full not in out:
                    out.append(full)
        return out[:self.c.max_luck]

    # ---- ②③④ evidence loop -------------------------------------------------------------------
    def evidence(self, needs: list[Need]) -> None:
        quiet = 0
        for round_no in range(1, self.c.max_rounds + 1):
            if self.out_of_time():
                self.stop_reason = 'het_gio'
                break
            active = [n for n in needs if n.status not in DONE and not n.stalled]
            if not active:
                self.stop_reason = 'du_het' if all(n.status in DONE for n in needs) else 'khong_co_gi_moi'
                break
            self.rounds = round_no
            progress, any_new = False, False
            for need in active:
                if self.out_of_time():
                    break
                before = RANK[need.status]
                queries = [need.query] if round_no == 1 else self.rewrite(need)
                new = self.retrieve(need, queries)
                if not new and round_no > 1:
                    need.stalled = True
                    self.trace.append({'step': 'retrieve', 'round': round_no, 'need': need.id,
                                       'queries': queries, 'new': []})
                    continue
                any_new = any_new or bool(new)
                self.judge(need, new, round_no)
                progress = progress or RANK[need.status] > before
            if self.out_of_time():
                self.stop_reason = 'het_gio'
                break
            if round_no > 1 and not any_new:
                self.stop_reason = 'khong_co_gi_moi'
                break
            quiet = 0 if progress else quiet + 1
            if quiet >= 2:
                self.stop_reason = 'khong_tien_trien'
                break
        else:
            self.stop_reason = 'het_vong' if any(n.status not in DONE for n in needs) else 'du_het'
        if self.stop_reason is None:
            self.stop_reason = 'du_het'
        self.trace.append({'step': 'stop', 'reason': self.stop_reason, 'rounds': self.rounds,
                           'needs': {n.id: n.status for n in needs}})

    def rewrite(self, need: Need) -> list[str]:
        out = self.call('rewrite', prompts.rewrite(need.text, need.missing, need.tried), schemas.Rewrite)
        return [nfc(q).strip() for q in out.queries if q.strip() and q.strip() not in need.tried] or \
            [need.text]

    def retrieve(self, need: Need, queries: list[str]) -> list[Passage]:
        new: list[Passage] = []
        for query in queries:
            need.tried.append(query)
            for p in self.h.retriever.search(query, need.school, self.c.k):
                if p.pid not in need.seen and p.pid not in {x.pid for x in new}:
                    new.append(p)
        need.seen.update(p.pid for p in new)
        return new

    def judge(self, need: Need, new: list[Passage], round_no: int) -> None:
        quoted = [self.passages[q['handle']] for q in need.quotes]
        shown = list({p.pid: p for p in quoted + new}.values())
        if not shown:                      # nothing to judge: no model call
            need.missing = 'không tìm thấy đoạn nào'
            self.trace.append({'step': 'judge', 'round': round_no, 'need': need.id,
                               'queries': need.tried[-2:], 'shown': [], 'status': need.status})
            return
        items = [(self.handle(p), p) for p in shown]
        facts = self.facts if need.kind in ('analysis', 'main', 'sub') else None
        out = self.call('judge', prompts.judge(need.text, facts, items, self.c.passage_chars),
                        schemas.Judgement)
        allowed = {h for h, _ in items}
        verified, rejected = [], []
        for q in out.quotes:
            handle = q.handle.strip('[] ').upper()
            if handle in allowed and verify.quote_found(q.quote, self.passages[handle].text):
                verified.append({'handle': handle, 'pid': self.passages[handle].pid, 'quote': q.quote})
            else:
                rejected.append({'handle': handle, 'quote': q.quote[:200]})
        merged = {(q['handle'], verify.norm(q['quote'])): q for q in need.quotes + verified}
        need.quotes = list(merged.values())
        pids = {q['pid'] for q in need.quotes}
        if out.status == 'mau_thuan' and len(pids) >= 2:
            status = 'mau_thuan'
        elif out.status in ('du', 'mau_thuan') and need.quotes:
            status = 'du'
        elif need.quotes:
            status = 'mot_phan'
        else:
            status = 'thieu'
        if RANK[status] >= RANK[need.status]:
            need.status = status
        need.missing = out.missing
        self.trace.append({'step': 'judge', 'round': round_no, 'need': need.id,
                           'queries': need.tried[-2:], 'shown': [h for h, _ in items],
                           'model_status': out.status, 'status': need.status,
                           'verified': [q['handle'] for q in verified], 'rejected': rejected})

    # ---- B3–B7 per school --------------------------------------------------------------------
    def evidence_text(self, needs: list[Need]) -> tuple[str, set[str]]:
        handles = sorted({q['handle'] for n in needs for q in n.quotes}, key=lambda h: int(h[1:]))
        blocks = []
        for h in handles:
            p = self.passages[h]
            quotes = [' '.join(q['quote'].split()) for n in needs for q in n.quotes if q['handle'] == h]
            head = ' '.join((p.header or p.book).split())       # one line each: PDF text wraps
            blocks.append(f'[{h}] {head}\nCâu trích: ' + prompts._fence(' | '.join(dict.fromkeys(quotes)))
                          + f'\n<<<\n{prompts._fence(p.text[:self.c.passage_chars])}\n>>>')
        return '\n\n'.join(blocks), set(handles)

    def analyse(self, needs: list[Need]) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        order = [self.focus] + [s for s in SCHOOLS if s != self.focus] if self.focus else list(SCHOOLS)
        for school in order:
            mine = [n for n in needs if n.school == school and n.quotes]
            if not mine:
                self.trace.append({'step': 'branch', 'school': school, 'skipped': 'no_evidence'})
                continue
            evidence, allowed = self.evidence_text(mine)
            result = self.call('branch', prompts.branch(school, self.q, self.facts, evidence),
                               schemas.BranchAnalysis)
            kept, dropped = self.validate(result.claims, allowed, with_facts=True)
            out[school] = kept
            self.trace.append({'step': 'branch', 'school': school, 'kept': len(kept),
                               'dropped': dropped})
        return out

    # ---- synthesis + validation ----------------------------------------------------------------
    def validate(self, claims, allowed: set[str], with_facts: bool) -> tuple[list[dict], list[dict]]:
        kept, dropped = [], []
        for claim in claims:
            sources = [s.strip('[] ').upper() for s in claim.sources]
            sources = list(dict.fromkeys(s for s in sources if s))
            texts = [self.passages[s].text for s in sources if s in allowed]
            if with_facts and 'F' in sources and self.facts:
                texts.append(self.facts)
            bad = [s for s in sources if s not in allowed and not (s == 'F' and with_facts and self.facts)]
            item = {'text': claim.text.strip(), 'sources': sources,
                    'part': getattr(claim, 'part', 'chinh')}
            if not sources:
                reason = 'khong_nguon'
            elif bad:
                reason = f'nguon_khong_hop_le:{",".join(bad)}'
            elif verify.risky_claim(item['text']):
                reason = 'khang_dinh_rui_ro'
            elif verify.support(item['text'], texts) < self.c.min_support:
                reason = 'khong_du_ung_ho'
            else:
                kept.append(item)
                continue
            dropped.append({**item, 'reason': reason})
        return kept, dropped

    def synthesize(self, needs: list[Need], branches: dict[str, list[dict]]) -> Result:
        evidence, allowed = self.evidence_text(needs)
        if not allowed and not branches:
            self.trace.append({'step': 'synthesize', 'skipped': 'no_evidence'})
            text = 'Không tìm thấy đoạn sách nào đủ căn cứ để trả lời câu hỏi này.'
            return self.result('no_evidence', text + self.missing_text(needs), [], [], needs,
                               'khong_ap_dung')
        branch_text = '\n'.join(
            f"- [{SCHOOL_LABELS[s]}] {c['text']} [{', '.join(c['sources'])}]"
            for s, claims in branches.items() for c in claims)
        out = self.call('synthesize', prompts.synthesize(self.q, self.facts, evidence, branch_text,
                                                         self.focus if self.chart else None),
                        schemas.Synthesis)
        kept, dropped = self.validate(out.claims, allowed, with_facts=bool(self.chart))
        agreement = out.agreement if len(branches) == 2 else ('mot_ben' if branches else 'khong_ap_dung')
        self.trace.append({'step': 'synthesize', 'kept': len(kept), 'dropped': dropped,
                           'agreement': agreement, 'model_insufficient': out.insufficient})
        main = [c for c in kept if c['part'] == 'chinh']
        if not main:
            text = 'Không đủ căn cứ trong các đoạn sách đã tìm để trả lời câu hỏi này.'
            return self.result('insufficient', text + self.missing_text(needs), [], dropped, needs,
                               agreement)
        status = 'ok' if all(n.status in DONE for n in needs) else 'partial'
        return self.result(status, self.render(kept, agreement, needs), kept, dropped, needs, agreement)

    def missing_text(self, needs: list[Need]) -> str:
        missing = [n for n in needs if n.status not in DONE and n.kind != 'main']
        if not missing:
            return ''
        return '\n\nChưa đủ căn cứ trong sách cho:\n' + '\n'.join(
            f'- {n.text}' + (' (chỉ có một phần)' if n.status == 'mot_phan' else '') for n in missing)

    def render(self, claims: list[dict], agreement: str, needs: list[Need]) -> str:
        def line(c):
            return f"- {c['text']} [{', '.join(c['sources'])}]"
        parts = [line(c) for c in claims if c['part'] == 'chinh']
        if agreement == 'giong':
            parts.append('\nHai trường phái cho cùng một kết luận.')
        elif agreement == 'khac':
            parts.append('\nHai trường phái cho kết luận khác nhau (xem từng nhận định).')
        other = [line(c) for c in claims if c['part'] == 'goc_nhin_khac']
        if other:
            parts.append('\nGóc nhìn khác:\n' + '\n'.join(other))
        text = '\n'.join(parts) + self.missing_text(needs)
        cited = sorted({s for c in claims for s in c['sources'] if s != 'F'}, key=lambda h: int(h[1:]))
        if cited:
            text += '\n\nNguồn:\n' + '\n'.join(
                f'[{h}] {self.passages[h].book}' + (f', {self.passages[h].pages}' if self.passages[h].pages else '')
                for h in cited)
        if any('F' in c['sources'] for c in claims):
            text += '\n[F] Dữ kiện lá số tính bằng bảng tra, không phải trích sách.'
        return text

    def result(self, status, answer, claims, dropped, needs, agreement) -> Result:
        cited = {s for c in claims for s in c['sources']}
        sources = [{'handle': h, 'pid': p.pid, 'book': p.book, 'pages': p.pages, 'school': p.school,
                    'cited': h in cited} for h, p in self.passages.items()]
        return Result(
            question=self.q, status=status, answer=answer, claims=claims, dropped=dropped,
            needs=[{'id': n.id, 'kind': n.kind, 'school': n.school, 'text': n.text,
                    'status': n.status, 'quotes': n.quotes, 'tried': n.tried, 'missing': n.missing,
                    'stalled': n.stalled} for n in needs],
            sources=sources, facts=self.facts, focus=self.focus, agreement=agreement,
            stop_reason=self.stop_reason, rounds=self.rounds, llm_calls=self.calls,
            elapsed_ms=int(self.elapsed() * 1000), trace=self.trace)


def _focus(question: str) -> str | None:
    tb, mp = bool(_TU_BINH.search(question)), bool(_MANH_PHAI.search(question))
    return 'tu_binh' if tb and not mp else 'manh_phai' if mp and not tb else None
