"""Facts of a chart given as written pillars (B1–B2 and the lookup facts for B3–B7).

A question may carry a chart as text ("Lá số nam: Mậu Ngọ – Ất Mão – Nhâm Tý – Canh Tý.
Đại vận: Bính Thìn – Đinh Tỵ …"). Everything here is table lookup, never the LLM and
never a calendar: the day master, the month command, ten gods, hidden stems (chủ → trung →
dư khí), the twelve growth stages of the day master, Lộc / Kình Dương / Thiên Mã, and the
relations among the pillars and with each luck pillar. Combinations are reported as
combinations only; no transformation (hóa) is ever claimed. The tables are the ones the
project owner reviewed (glossary-1, docs/15 · 21/10/2026).

``find_chart`` reads a chart out of a question; ``facts`` computes; ``render`` writes the
Vietnamese block the answer prompt receives, labelled as computed facts, not a source.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
import re
import unicodedata

from .tables import (BRANCH_ELEMENT, BRANCH_LABELS, BRANCHES, CLASHES, DESTRUCTIONS, DIRECTIONAL,
                     ELEMENT_LABELS, GROWTH_LABELS, HARMS, HIDDEN_STEMS, PUNISHMENT_GROUPS,
                     PUNISHMENT_PAIRS, SELF_PUNISHMENT, SIX_COMBINATIONS, STEM_CLASHES,
                     STEM_COMBINATIONS, STEM_ELEMENT, STEM_LABELS, STEMS, THREE_COMBINATIONS,
                     TEN_GOD_LABELS, growth_stage, stem_yang, ten_god)

POSITIONS = ('year', 'month', 'day', 'hour')
POSITION_LABELS = {'year': 'năm', 'month': 'tháng', 'day': 'ngày', 'hour': 'giờ', 'luck': 'vận'}
HIDDEN_RANK_LABELS = ('chủ khí', 'trung khí', 'dư khí')

# Ám hợp (MPSC tr.179): the hidden stems of the two branches combine.
DARK_COMBINATIONS = {frozenset(p) for p in (('yin', 'chou'), ('wu', 'hai'), ('mao', 'shen'))}
# Tự hợp (DOCX ¶201–202): the stem combines with a hidden stem of its own branch.
SELF_COMBINATIONS = {('ding', 'hai'), ('ji', 'hai'), ('xin', 'si'), ('gui', 'si'), ('jia', 'wu'),
                     ('wu', 'zi'), ('ren', 'wu')}
SELF_COMBINATIONS_WITH_WEI = {('bing', 'xu'), ('ren', 'xu')}   # only when Tuất meets Mùi
# Chi hợp khắc can (DOCX ¶200): within one pillar the branch combines with and controls the stem.
BRANCH_CONTROLS_STEM = {('ding', 'hai'), ('ji', 'hai'), ('xin', 'si'), ('gui', 'si')}
# Thiên Mã, traditional: from the three-harmony group of the year or day branch.
HORSE = {**dict.fromkeys(('shen', 'zi', 'chen'), 'yin'), **dict.fromkeys(('yin', 'wu', 'xu'), 'shen'),
         **dict.fromkeys(('si', 'you', 'chou'), 'hai'), **dict.fromkeys(('hai', 'mao', 'wei'), 'si')}


# ---- reading pillars out of text --------------------------------------------------------

def _fold(text: str) -> str:
    text = unicodedata.normalize('NFD', text.lower().replace('đ', 'd'))
    return unicodedata.normalize('NFC', ''.join(c for c in text if unicodedata.category(c) != 'Mn'))


_STEM_WORDS = {'giap': 'jia', 'at': 'yi', 'binh': 'bing', 'dinh': 'ding', 'mau': 'wu', 'ky': 'ji',
               'ki': 'ji', 'canh': 'geng', 'tan': 'xin', 'nham': 'ren', 'quy': 'gui', 'qui': 'gui'}
_BRANCH_WORDS = {'ty': None, 'ti': 'si', 'suu': 'chou', 'dan': 'yin', 'mao': 'mao', 'thin': 'chen',
                 'ngo': 'wu', 'mui': 'wei', 'than': 'shen', 'dau': 'you', 'tuat': 'xu', 'hoi': 'hai'}
# "Tý" and "Tỵ" fold to the same letters; tell them apart by the diacritic.
_TY = {'tý': 'zi', 'tí': 'zi', 'tỵ': 'si', 'tị': 'si'}
_PAIR = re.compile(r'([^\W\d_]+)\s+([^\W\d_]+)', re.UNICODE)


def _branch(word: str) -> str | None:
    low = unicodedata.normalize('NFC', word.lower())
    if low in _TY:
        return _TY[low]
    return _BRANCH_WORDS.get(_fold(word))


def _pairs(text: str) -> list[tuple[int, int, str, str]]:
    """Every adjacent stem+branch pair in ``text``: (start, end, stem, branch)."""
    out, pos = [], 0
    while True:
        m = _PAIR.search(text, pos)
        if not m:
            return out
        stem, branch = _STEM_WORDS.get(_fold(m.group(1))), _branch(m.group(2))
        if stem and branch:
            out.append((m.start(), m.end(), stem, branch))
            pos = m.end()
        else:
            pos = m.start() + len(m.group(1))


# Between two pillars of one list: separators, ages "(2 tuổi)", years "(2001)".
_GAP = re.compile(r'^[\s\-–—,;/·|.:]*(\(\s*\d{1,4}\s*(tuổi)?\s*\))?[\s\-–—,;/·|.:]*$')


def _run(text: str, pairs: list) -> list:
    """The leading pairs that follow each other with only separators between them."""
    out = pairs[:1]
    for prev, cur in zip(pairs, pairs[1:]):
        if not _GAP.match(text[prev[1]:cur[0]]):
            break
        out.append(cur)
    return out


@dataclass
class Chart:
    pillars: dict[str, tuple[str, str]]
    luck: list[tuple[str, str]] = field(default_factory=list)
    sex: str | None = None                    # 'male' | 'female' | None


def find_chart(question: str) -> Chart | None:
    """The first four pillars in the question, and the luck pillars written after "vận"."""
    pairs = _pairs(question)
    natal = next((_run(question, pairs[i:])[:4] for i in range(len(pairs))
                  if len(_run(question, pairs[i:])) >= 4), None)
    if natal is None:
        return None
    folded = _fold(question)
    luck_at = folded.find('dai van', natal[-1][1])
    after = [p for p in pairs if luck_at >= 0 and p[0] > luck_at]
    luck = [(s, b) for _, _, s, b in _run(question, after)] if after else []
    head = folded[:natal[0][0]]
    sex = ('female' if re.search(r'\b(nu|khon)\b', head) else
           'male' if re.search(r'\b(nam|can)\b', head) else None)
    return Chart(dict(zip(POSITIONS, [(s, b) for _, _, s, b in natal])), luck, sex)


# ---- facts -------------------------------------------------------------------------------

def _label(stem=None, branch=None) -> str:
    return ' '.join(x for x in (STEM_LABELS.get(stem), BRANCH_LABELS.get(branch)) if x)


def _month_stem(year_stem: str, month_branch: str) -> str:
    """Ngũ Hổ độn: the month stem a year stem gives the month branch."""
    first = {'jia': 'bing', 'ji': 'bing', 'yi': 'wu', 'geng': 'wu', 'bing': 'geng', 'xin': 'geng',
             'ding': 'ren', 'ren': 'ren', 'wu': 'jia', 'gui': 'jia'}[year_stem]
    steps = (BRANCHES.index(month_branch) - BRANCHES.index('yin')) % 12
    return STEMS[(STEMS.index(first) + steps) % 10]


def _hour_stem(day_stem: str, hour_branch: str) -> str:
    """Ngũ Thử độn: the hour stem a day stem gives the hour branch."""
    first = {'jia': 'jia', 'ji': 'jia', 'yi': 'bing', 'geng': 'bing', 'bing': 'wu', 'xin': 'wu',
             'ding': 'geng', 'ren': 'geng', 'wu': 'ren', 'gui': 'ren'}[day_stem]
    return STEMS[(STEMS.index(first) + BRANCHES.index(hour_branch)) % 10]


def _cycle(stem: str, branch: str) -> int:
    s, b = STEMS.index(stem), BRANCHES.index(branch)
    return (6 * s - 5 * b) % 60


def _warnings(chart: Chart) -> list[str]:
    out = []
    for pos, (stem, branch) in chart.pillars.items():
        if stem_yang(stem) != (BRANCHES.index(branch) % 2 == 0):
            out.append(f'Trụ {POSITION_LABELS[pos]} {_label(stem, branch)} không có trong lục thập hoa giáp.')
    (ys, _), (ms, mb) = chart.pillars['year'], chart.pillars['month']
    (ds, _), (hs, hb) = chart.pillars['day'], chart.pillars['hour']
    if _month_stem(ys, mb) != ms:
        out.append(f'Can tháng theo Ngũ Hổ độn phải là {STEM_LABELS[_month_stem(ys, mb)]}, đề cho {STEM_LABELS[ms]}.')
    if _hour_stem(ds, hb) != hs:
        out.append(f'Can giờ theo Ngũ Thử độn phải là {STEM_LABELS[_hour_stem(ds, hb)]}, đề cho {STEM_LABELS[hs]}.')
    if chart.luck and all(stem_yang(s) == (BRANCHES.index(b) % 2 == 0) for s, b in chart.luck):
        start = _cycle(ms, mb)
        seq = [_cycle(s, b) for s, b in chart.luck]
        forward = all(seq[i] == (start + i + 1) % 60 for i in range(len(seq)))
        backward = all(seq[i] == (start - i - 1) % 60 for i in range(len(seq)))
        if not (forward or backward):
            out.append('Đại vận không nối tiếp trụ tháng theo vòng 60 can chi.')
        elif chart.sex:
            should = stem_yang(ys) == (chart.sex == 'male')
            if should != forward:
                out.append('Chiều đại vận không khớp giới tính và âm dương can năm '
                           f"(phải {'thuận' if should else 'nghịch'}).")
    return out


def _relations(members: list[tuple[str, tuple[str, str]]]) -> list[dict]:
    """Pairwise and three-branch relations among (position, (stem, branch)) members."""
    out = []
    for (pa, (sa, ba)), (pb, (sb, bb)) in combinations(members, 2):
        stems, branches = frozenset((sa, sb)), frozenset((ba, bb))
        if stems in STEM_COMBINATIONS:
            out.append({'type': 'Thiên can ngũ hợp', 'positions': [pa, pb], 'members': [sa, sb], 'stem': True})
        if stems in STEM_CLASHES:
            out.append({'type': 'Thiên can tương xung', 'positions': [pa, pb], 'members': [sa, sb], 'stem': True})
        for name, table in (('Lục hợp', SIX_COMBINATIONS), ('Lục xung', CLASHES), ('Lục hại', HARMS),
                            ('Lục phá', DESTRUCTIONS), ('Tương hình', PUNISHMENT_PAIRS),
                            ('Ám hợp', DARK_COMBINATIONS)):
            if branches in table:
                out.append({'type': name, 'positions': [pa, pb], 'members': [ba, bb]})
        if ba == bb and ba in SELF_PUNISHMENT:
            out.append({'type': 'Tự hình', 'positions': [pa, pb], 'members': [ba, bb]})
    branches = [(pos, b) for pos, (_, b) in members]
    for frames, full_name in ((THREE_COMBINATIONS, 'Tam hợp'), (DIRECTIONAL, 'Tam hội')):
        for frame, element in frames:
            found = [(p, b) for p, b in branches if b in frame]
            distinct = {b for _, b in found}
            if len(distinct) == 3:
                kind = f'{full_name} {ELEMENT_LABELS[element]} cục (đủ ba chi)'
            elif len(distinct) == 2 and full_name == 'Tam hợp':
                kind = ('Bán hợp' if frame[1] in distinct else 'Củng') + \
                    f' {ELEMENT_LABELS[element]} (thiếu {BRANCH_LABELS[(set(frame) - distinct).pop()]})'
            elif len(distinct) == 2:
                kind = f'Tam hội {ELEMENT_LABELS[element]} thiếu {BRANCH_LABELS[(set(frame) - distinct).pop()]}'
            else:
                continue
            out.append({'type': kind, 'positions': [p for p, _ in found], 'members': [b for _, b in found]})
    for group in PUNISHMENT_GROUPS:
        found = [(p, b) for p, b in branches if b in group]
        distinct = {b for _, b in found}
        if len(distinct) == 3:
            out.append({'type': 'Tam hình (đủ ba chi)', 'positions': [p for p, _ in found],
                        'members': [b for _, b in found]})
        elif len(distinct) == 2:
            out.append({'type': 'Tương hình', 'positions': [p for p, _ in found],
                        'members': [b for _, b in found]})
    return out


def _self_combination(stem: str, branch: str, branches_present: set[str]) -> list[str]:
    out = []
    if (stem, branch) in SELF_COMBINATIONS:
        out.append('Tự hợp')
    elif (stem, branch) in SELF_COMBINATIONS_WITH_WEI and 'wei' in branches_present:
        out.append('Tự hợp (Tuất gặp Mùi hình)')
    if (stem, branch) in BRANCH_CONTROLS_STEM:
        out.append('Chi hợp khắc can')
    return out


def facts(chart: Chart) -> dict:
    day_stem, day_branch = chart.pillars['day']
    month_branch = chart.pillars['month'][1]
    natal_branches = {b for _, b in chart.pillars.values()}

    def pillar(pos: str, stem: str, branch: str, present: set[str]) -> dict:
        return {
            'position': pos, 'stem': stem, 'branch': branch,
            'stem_ten_god': None if pos == 'day' else ten_god(stem, day_stem),
            'hidden': [{'stem': h, 'rank': HIDDEN_RANK_LABELS[i], 'ten_god': ten_god(h, day_stem)}
                       for i, h in enumerate(HIDDEN_STEMS[branch])],
            'growth': growth_stage(day_stem, branch),
            'self': _self_combination(stem, branch, present),
        }

    natal = [pillar(pos, s, b, natal_branches) for pos, (s, b) in chart.pillars.items()]
    natal_relations = _relations(list(chart.pillars.items()))
    natal_full = {r['type'] for r in natal_relations if 'đủ ba chi' in r['type']}
    lu = next(b for b in BRANCHES if growth_stage(day_stem, b) == 'linguan')
    blade = next(b for b in BRANCHES if growth_stage(day_stem, b) == 'diwang') if stem_yang(day_stem) else None
    horses = {src: HORSE[chart.pillars[src][1]] for src in ('year', 'day')}
    where = lambda b: [p for p, (_, x) in chart.pillars.items() if x == b]  # noqa: E731
    luck = []
    for i, (s, b) in enumerate(chart.luck, start=1):
        members = [('luck', (s, b))] + list(chart.pillars.items())
        with_luck = [r for r in _relations(members) if 'luck' in r['positions']]
        for r in with_luck:          # a full frame: there already, or only with this luck pillar
            if 'đủ ba chi' in r['type']:
                r['type'] += ', đã đủ trong tứ trụ' if r['type'] in natal_full else ', đủ nhờ vận'
        luck.append({'index': i, 'stem': s, 'branch': b, 'stem_ten_god': ten_god(s, day_stem),
                     'hidden': [{'stem': h, 'rank': HIDDEN_RANK_LABELS[k], 'ten_god': ten_god(h, day_stem)}
                                for k, h in enumerate(HIDDEN_STEMS[b])],
                     'growth': growth_stage(day_stem, b),
                     'self': _self_combination(s, b, natal_branches | {b}),
                     'relations': with_luck,
                     'stars': [name for name, target in (('Lộc', lu), ('Kình Dương', blade))
                               if target == b]
                     + [f'Thiên Mã (theo chi {POSITION_LABELS[src]})' for src, h in horses.items() if h == b]})
    return {
        'day_master': {'stem': day_stem, 'element': STEM_ELEMENT[day_stem], 'yang': stem_yang(day_stem)},
        'month_command': {'branch': month_branch, 'element': BRANCH_ELEMENT[month_branch],
                          'main_qi': HIDDEN_STEMS[month_branch][0],
                          'main_qi_ten_god': ten_god(HIDDEN_STEMS[month_branch][0], day_stem)},
        'sex': chart.sex, 'pillars': natal,
        'lu': {'branch': lu, 'positions': where(lu)},
        'blade': {'branch': blade, 'positions': where(blade) if blade else []},
        'horse': {src: {'branch': h, 'positions': where(h)} for src, h in horses.items()},
        'relations': natal_relations,
        'luck': luck, 'warnings': _warnings(chart),
    }


# ---- Vietnamese block for the prompt ------------------------------------------------------

def _members(rel: dict) -> str:
    labels = STEM_LABELS if rel.get('stem') else BRANCH_LABELS
    return ' – '.join(f'{labels[m]} ({POSITION_LABELS[p]})' for p, m in zip(rel['positions'], rel['members']))


def _where(positions: list[str]) -> str:
    return ', '.join(POSITION_LABELS[p] for p in positions) if positions else 'không có trong tứ trụ'


def render(f: dict) -> str:
    dm, mc = f['day_master'], f['month_command']
    sex = {'male': ' (nam)', 'female': ' (nữ)'}.get(f['sex'], '')
    lines = ['DỮ KIỆN LÁ SỐ — tính bằng bảng tra, không phải trích sách',
             'Tứ trụ' + sex + ': ' + ' · '.join(
                 f"{POSITION_LABELS[p['position']].capitalize()} {_label(p['stem'], p['branch'])}" for p in f['pillars']),
             f"B1 Nhật chủ: {STEM_LABELS[dm['stem']]} ({'Dương' if dm['yang'] else 'Âm'} {ELEMENT_LABELS[dm['element']]})",
             f"B2 Nguyệt lệnh: {BRANCH_LABELS[mc['branch']]} ({ELEMENT_LABELS[mc['element']]}), chủ khí "
             f"{STEM_LABELS[mc['main_qi']]} ({TEN_GOD_LABELS[mc['main_qi_ten_god']]})"]
    for p in f['pillars']:
        head = f"Trụ {POSITION_LABELS[p['position']]} {_label(p['stem'], p['branch'])}: "
        can = 'can là Nhật chủ' if p['stem_ten_god'] is None else \
            f"can {STEM_LABELS[p['stem']]} {TEN_GOD_LABELS[p['stem_ten_god']]}"
        hidden = ', '.join(f"{STEM_LABELS[h['stem']]} {TEN_GOD_LABELS[h['ten_god']]} ({h['rank']})"
                           for h in p['hidden'])
        extra = f"; {', '.join(p['self'])}" if p['self'] else ''
        lines.append(f"{head}{can}; tàng can {hidden}; Nhật chủ tại {BRANCH_LABELS[p['branch']]}: "
                     f"{GROWTH_LABELS[p['growth']]}{extra}")
    lines.append(f"Lộc của Nhật chủ: {BRANCH_LABELS[f['lu']['branch']]} — {_where(f['lu']['positions'])}")
    blade = f['blade']
    lines.append('Kình Dương: không có (Nhật chủ là can âm)' if blade['branch'] is None else
                 f"Kình Dương: {BRANCH_LABELS[blade['branch']]} — {_where(blade['positions'])}")
    lines.append('Thiên Mã: ' + '; '.join(
        f"theo chi {POSITION_LABELS[src]} là {BRANCH_LABELS[h['branch']]} — {_where(h['positions'])}"
        for src, h in f['horse'].items()))
    lines.append('Quan hệ trong tứ trụ: ' + ('; '.join(f"{r['type']}: {_members(r)}" for r in f['relations'])
                                           or 'không có'))
    for v in f['luck']:
        hidden = ', '.join(f"{STEM_LABELS[h['stem']]} {TEN_GOD_LABELS[h['ten_god']]}" for h in v['hidden'])
        rel = '; '.join(f"{r['type']}: {_members(r)}" for r in v['relations']) or 'không có quan hệ với tứ trụ'
        stars = f"; {', '.join(v['stars'])}" if v['stars'] else ''
        own = f"; {', '.join(v['self'])}" if v['self'] else ''
        lines.append(f"Đại vận {v['index']} {_label(v['stem'], v['branch'])}: can {TEN_GOD_LABELS[v['stem_ten_god']]};"
                     f" tàng can {hidden}; Nhật chủ tại {BRANCH_LABELS[v['branch']]}: "
                     f"{GROWTH_LABELS[v['growth']]}{stars}{own}; {rel}")
    for w in f['warnings']:
        lines.append(f'Cảnh báo: {w}')
    lines.append('Hợp chỉ ghi là hợp; không xét hóa.')
    return '\n'.join(lines)
