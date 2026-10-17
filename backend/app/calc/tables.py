"""Stems, branches and the fixed tables of the four pillars (docs/08 · ChartFacts).

IDs are stable ASCII pinyin; Vietnamese labels are for presentation only. The stem
``wu`` (戊) and the branch ``wu`` (午) never meet outside their own type.
"""
from __future__ import annotations

STEMS = ('jia', 'yi', 'bing', 'ding', 'wu', 'ji', 'geng', 'xin', 'ren', 'gui')
BRANCHES = ('zi', 'chou', 'yin', 'mao', 'chen', 'si', 'wu', 'wei', 'shen', 'you', 'xu', 'hai')
STEM_LABELS = dict(zip(STEMS, ('Giáp', 'Ất', 'Bính', 'Đinh', 'Mậu', 'Kỷ', 'Canh', 'Tân',
                               'Nhâm', 'Quý')))
BRANCH_LABELS = dict(zip(BRANCHES, ('Tý', 'Sửu', 'Dần', 'Mão', 'Thìn', 'Tỵ', 'Ngọ', 'Mùi',
                                    'Thân', 'Dậu', 'Tuất', 'Hợi')))
ELEMENTS = ('wood', 'fire', 'earth', 'metal', 'water')
ELEMENT_LABELS = {'wood': 'Mộc', 'fire': 'Hỏa', 'earth': 'Thổ', 'metal': 'Kim', 'water': 'Thủy'}
STEM_ELEMENT = dict(zip(STEMS, ('wood', 'wood', 'fire', 'fire', 'earth', 'earth', 'metal',
                                'metal', 'water', 'water')))
BRANCH_ELEMENT = dict(zip(BRANCHES, ('water', 'earth', 'wood', 'wood', 'earth', 'fire', 'fire',
                                     'earth', 'metal', 'metal', 'earth', 'water')))
GENERATES = {'wood': 'fire', 'fire': 'earth', 'earth': 'metal', 'metal': 'water', 'water': 'wood'}
CONTROLS = {'wood': 'earth', 'earth': 'water', 'water': 'fire', 'fire': 'metal', 'metal': 'wood'}


def stem_yang(stem: str) -> bool:
    return STEMS.index(stem) % 2 == 0


def branch_yang(branch: str) -> bool:
    return BRANCHES.index(branch) % 2 == 0


# ---- sexagenary cycle -----------------------------------------------------------------

def ganzhi(index: int) -> tuple[str, str]:
    """(stem, branch) of position 0..59 in the 60-cycle (0 = jia zi)."""
    return STEMS[index % 10], BRANCHES[index % 12]


def cycle_index(stem: str, branch: str) -> int:
    """Position 0..59 of a valid pair (same polarity); ValueError otherwise."""
    s, b = STEMS.index(stem), BRANCHES.index(branch)
    if s % 2 != b % 2:
        raise ValueError(f'{stem} {branch} is not a sexagenary pair')
    return (6 * s - 5 * b) % 60


# ---- ten gods -------------------------------------------------------------------------

TEN_GODS = ('peer', 'rob_wealth', 'eating_god', 'hurting_officer', 'indirect_wealth',
            'direct_wealth', 'seven_killings', 'direct_officer', 'indirect_resource',
            'direct_resource')
TEN_GOD_LABELS = dict(zip(TEN_GODS, ('Tỷ Kiên', 'Kiếp Tài', 'Thực Thần', 'Thương Quan',
                                     'Thiên Tài', 'Chính Tài', 'Thất Sát', 'Chính Quan',
                                     'Thiên Ấn', 'Chính Ấn')))


def ten_god(stem: str, day_stem: str) -> str:
    """Ten god of ``stem`` seen from the day stem (standard Tử Bình relation)."""
    me, other = STEM_ELEMENT[day_stem], STEM_ELEMENT[stem]
    same = stem_yang(stem) == stem_yang(day_stem)
    if other == me:
        return 'peer' if same else 'rob_wealth'
    if GENERATES[me] == other:
        return 'eating_god' if same else 'hurting_officer'
    if CONTROLS[me] == other:
        return 'indirect_wealth' if same else 'direct_wealth'
    if CONTROLS[other] == me:
        return 'seven_killings' if same else 'direct_officer'
    return 'indirect_resource' if same else 'direct_resource'


# ---- hidden stems (tàng can): main, middle, residual qi -------------------------------

HIDDEN_RANKS = ('main', 'middle', 'residual')
HIDDEN_STEMS: dict[str, tuple[str, ...]] = {
    'zi': ('gui',), 'chou': ('ji', 'gui', 'xin'), 'yin': ('jia', 'bing', 'wu'),
    'mao': ('yi',), 'chen': ('wu', 'yi', 'gui'), 'si': ('bing', 'wu', 'geng'),
    'wu': ('ding', 'ji'), 'wei': ('ji', 'yi', 'ding'), 'shen': ('geng', 'ren', 'wu'),
    'you': ('xin',), 'xu': ('wu', 'xin', 'ding'), 'hai': ('ren', 'jia'),
}

# ---- twelve growth stages (trường sinh) ------------------------------------------------

GROWTH = ('changsheng', 'muyu', 'guandai', 'linguan', 'diwang', 'shuai', 'bing', 'si', 'mu',
          'jue', 'tai', 'yang')
GROWTH_LABELS = dict(zip(GROWTH, ('Trường sinh', 'Mộc dục', 'Quan đới', 'Lâm quan', 'Đế vượng',
                                  'Suy', 'Bệnh', 'Tử', 'Mộ', 'Tuyệt', 'Thai', 'Dưỡng')))
GROWTH_START = {'jia': 'hai', 'yi': 'wu', 'bing': 'yin', 'wu': 'yin', 'ding': 'you',
                'ji': 'you', 'geng': 'si', 'xin': 'zi', 'ren': 'shen', 'gui': 'mao'}


def growth_stage(stem: str, branch: str) -> str:
    """Yang stems run forward from their changsheng branch, yin stems backward."""
    start, at = BRANCHES.index(GROWTH_START[stem]), BRANCHES.index(branch)
    step = (at - start) % 12 if stem_yang(stem) else (start - at) % 12
    return GROWTH[step]


# ---- na yin (nạp âm): one sound per pair of the 60-cycle --------------------------------

NA_YIN = (
    ('hai_zhong_jin', 'Hải trung Kim'), ('lu_zhong_huo', 'Lư trung Hỏa'),
    ('da_lin_mu', 'Đại lâm Mộc'), ('lu_pang_tu', 'Lộ bàng Thổ'),
    ('jian_feng_jin', 'Kiếm phong Kim'), ('shan_tou_huo', 'Sơn đầu Hỏa'),
    ('jian_xia_shui', 'Giản hạ Thủy'), ('cheng_tou_tu', 'Thành đầu Thổ'),
    ('bai_la_jin', 'Bạch lạp Kim'), ('yang_liu_mu', 'Dương liễu Mộc'),
    ('quan_zhong_shui', 'Tuyền trung Thủy'), ('wu_shang_tu', 'Ốc thượng Thổ'),
    ('pi_li_huo', 'Tích lịch Hỏa'), ('song_bai_mu', 'Tùng bách Mộc'),
    ('chang_liu_shui', 'Trường lưu Thủy'), ('sha_zhong_jin', 'Sa trung Kim'),
    ('shan_xia_huo', 'Sơn hạ Hỏa'), ('ping_di_mu', 'Bình địa Mộc'),
    ('bi_shang_tu', 'Bích thượng Thổ'), ('jin_bo_jin', 'Kim bạch Kim'),
    ('fu_deng_huo', 'Phúc đăng Hỏa'), ('tian_he_shui', 'Thiên hà Thủy'),
    ('da_yi_tu', 'Đại dịch Thổ'), ('chai_chuan_jin', 'Thoa xuyến Kim'),
    ('sang_zhe_mu', 'Tang đố Mộc'), ('da_xi_shui', 'Đại khê Thủy'),
    ('sha_zhong_tu', 'Sa trung Thổ'), ('tian_shang_huo', 'Thiên thượng Hỏa'),
    ('shi_liu_mu', 'Thạch lựu Mộc'), ('da_hai_shui', 'Đại hải Thủy'),
)
NA_YIN_ELEMENT = {'jin': 'metal', 'huo': 'fire', 'mu': 'wood', 'tu': 'earth', 'shui': 'water'}


def na_yin(index: int) -> tuple[str, str, str]:
    """(id, Vietnamese label, element) of the 60-cycle position."""
    key, label = NA_YIN[index // 2]
    return key, label, NA_YIN_ELEMENT[key.rsplit('_', 1)[1]]


def void_branches(index: int) -> tuple[str, str]:
    """The two branches left out of the decade (tuần) that contains position ``index``."""
    start = index - index % 10
    return BRANCHES[(start + 10) % 12], BRANCHES[(start + 11) % 12]


# ---- relations --------------------------------------------------------------------------

STEM_COMBINATIONS = {frozenset(p): e for p, e in ((('jia', 'ji'), 'earth'),
                     (('yi', 'geng'), 'metal'), (('bing', 'xin'), 'water'),
                     (('ding', 'ren'), 'wood'), (('wu', 'gui'), 'fire'))}
STEM_CLASHES = {frozenset(p) for p in (('jia', 'geng'), ('yi', 'xin'), ('bing', 'ren'),
                                       ('ding', 'gui'))}
SIX_COMBINATIONS = {frozenset(p): e for p, e in ((('zi', 'chou'), 'earth'),
                    (('yin', 'hai'), 'wood'), (('mao', 'xu'), 'fire'), (('chen', 'you'), 'metal'),
                    (('si', 'shen'), 'water'), (('wu', 'wei'), 'fire'))}
CLASHES = {frozenset(p) for p in (('zi', 'wu'), ('chou', 'wei'), ('yin', 'shen'),
                                  ('mao', 'you'), ('chen', 'xu'), ('si', 'hai'))}
HARMS = {frozenset(p) for p in (('zi', 'wei'), ('chou', 'wu'), ('yin', 'si'), ('mao', 'chen'),
                                ('shen', 'hai'), ('you', 'xu'))}
DESTRUCTIONS = {frozenset(p) for p in (('zi', 'you'), ('chou', 'chen'), ('yin', 'hai'),
                                       ('mao', 'wu'), ('shen', 'si'), ('wei', 'xu'))}
# (members, element); the middle member is the cardinal branch of the frame.
THREE_COMBINATIONS = ((('shen', 'zi', 'chen'), 'water'), (('hai', 'mao', 'wei'), 'wood'),
                      (('yin', 'wu', 'xu'), 'fire'), (('si', 'you', 'chou'), 'metal'))
DIRECTIONAL = ((('yin', 'mao', 'chen'), 'wood'), (('si', 'wu', 'wei'), 'fire'),
               (('shen', 'you', 'xu'), 'metal'), (('hai', 'zi', 'chou'), 'water'))
PUNISHMENT_GROUPS = (('yin', 'si', 'shen'), ('chou', 'xu', 'wei'))
PUNISHMENT_PAIRS = {frozenset(('zi', 'mao'))}
SELF_PUNISHMENT = ('chen', 'wu', 'you', 'hai')
