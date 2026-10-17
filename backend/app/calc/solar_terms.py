"""Solar terms as physical instants in UTC (docs/08 · Chính sách thời gian, point 3).

The astronomy is lunar-python's port of 寿星天文历 (sxwnl). It reports every term in
Beijing civil time (UTC+8) for all years; this adapter converts to UTC once, so a birth
anywhere is compared instant to instant and Beijing time is never mistaken for local.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib.metadata import version

from lunar_python import Lunar

SOURCE = f'lunar-python {version("lunar-python")} (sxwnl)'
FIRST_YEAR, LAST_YEAR = 1900, 2100          # range covered by the oracle (T029)
# Measured against an independent VSOP87 ephemeris (PyEphem) for every term 1900-2100:
# median 10 s, max 57 s (ΔT extrapolation after 2025). Births closer than this to a jie
# are flagged, since the month (or year) pillar may flip within the model error.
TOLERANCE_SECONDS = 120
_BEIJING = timezone(timedelta(hours=8))

TERMS = ('li_chun', 'yu_shui', 'jing_zhe', 'chun_fen', 'qing_ming', 'gu_yu', 'li_xia',
         'xiao_man', 'mang_zhong', 'xia_zhi', 'xiao_shu', 'da_shu', 'li_qiu', 'chu_shu',
         'bai_lu', 'qiu_fen', 'han_lu', 'shuang_jiang', 'li_dong', 'xiao_xue', 'da_xue',
         'dong_zhi', 'xiao_han', 'da_han')
TERM_LABELS = dict(zip(TERMS, ('Lập Xuân', 'Vũ Thủy', 'Kinh Trập', 'Xuân Phân', 'Thanh Minh',
                               'Cốc Vũ', 'Lập Hạ', 'Tiểu Mãn', 'Mang Chủng', 'Hạ Chí', 'Tiểu Thử',
                               'Đại Thử', 'Lập Thu', 'Xử Thử', 'Bạch Lộ', 'Thu Phân', 'Hàn Lộ',
                               'Sương Giáng', 'Lập Đông', 'Tiểu Tuyết', 'Đại Tuyết', 'Đông Chí',
                               'Tiểu Hàn', 'Đại Hàn')))
# The twelve "jie" open the solar months; each gives the month branch.
JIE_BRANCH = {'li_chun': 'yin', 'jing_zhe': 'mao', 'qing_ming': 'chen', 'li_xia': 'si',
              'mang_zhong': 'wu', 'xiao_shu': 'wei', 'li_qiu': 'shen', 'bai_lu': 'you',
              'han_lu': 'xu', 'li_dong': 'hai', 'da_xue': 'zi', 'xiao_han': 'chou'}
_CHINESE = dict(zip(('立春', '雨水', '惊蛰', '春分', '清明', '谷雨', '立夏', '小满', '芒种', '夏至',
                     '小暑', '大暑', '立秋', '处暑', '白露', '秋分', '寒露', '霜降', '立冬', '小雪',
                     '大雪', '冬至', '小寒', '大寒'), TERMS))


@dataclass(frozen=True, order=True)
class Term:
    instant: datetime            # aware, UTC
    key: str

    @property
    def is_jie(self) -> bool:
        return self.key in JIE_BRANCH

    def as_fact(self) -> dict:
        return {'key': self.key, 'instant_utc': iso_utc(self.instant), 'source_version': SOURCE}


def iso_utc(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _key(name: str) -> str:
    # The table also lists neighbouring years' terms under upper-case pinyin keys.
    return _CHINESE.get(name) or name.lower()


@lru_cache(maxsize=256)
def _lunar_year(year: int) -> tuple[Term, ...]:
    terms = []
    for name, solar in Lunar.fromYmd(year, 1, 1).getJieQiTable().items():
        beijing = datetime(solar.getYear(), solar.getMonth(), solar.getDay(), solar.getHour(),
                           solar.getMinute(), solar.getSecond(), tzinfo=_BEIJING)
        terms.append(Term(beijing.astimezone(timezone.utc), _key(name)))
    return tuple(terms)


@lru_cache(maxsize=256)
def _around(year: int) -> tuple[Term, ...]:
    """Every term from about November of year-1 to March of year+1, sorted, unique."""
    merged = {t for y in (year - 1, year, year + 1) for t in _lunar_year(y)}
    return tuple(sorted(merged))


def in_range(instant: datetime) -> bool:
    return FIRST_YEAR <= instant.astimezone(timezone.utc).year <= LAST_YEAR


def neighbours(instant: datetime, jie_only: bool = True) -> tuple[Term, Term]:
    """The term at or before ``instant`` and the first one after it."""
    terms = [t for t in _around(instant.astimezone(timezone.utc).year)
             if t.is_jie or not jie_only]
    at = bisect_right([t.instant for t in terms], instant)
    if at == 0 or at == len(terms):
        raise ValueError('instant outside the computed solar-term window')
    return terms[at - 1], terms[at]


def term_in_year(key: str, year: int) -> Term:
    """The occurrence of ``key`` inside Gregorian year ``year`` (UTC)."""
    for term in _around(year):
        if term.key == key and term.instant.year == year:
            return term
    raise ValueError(f'{key} not found in {year}')


def between(start: datetime, end: datetime, jie_only: bool = False) -> list[Term]:
    """Terms with start < instant <= end (both aware)."""
    years = range(start.astimezone(timezone.utc).year, end.astimezone(timezone.utc).year + 1)
    found = {t for y in years for t in _around(y) if start < t.instant <= end}
    return sorted(t for t in found if t.is_jie or not jie_only)
