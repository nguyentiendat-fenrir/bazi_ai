"""Birth input → ChartFacts ``chart-facts/1`` (docs/08 · ChartFacts schema v1).

An exact birth time gives one set of pillars. A time interval (unknown hour, a stated
hour only, or ± minutes) is cut at every instant where a pillar can change — the jie
terms, the day rollover, the two-hour boundaries of the pillar clock — and a pillar
that differs across the pieces is null in the main facts and spelled out in
``variants`` with the bounds and the reason, never guessed (no assumed 12:00).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json

from . import lunar, solar_terms
from .pillars import day_and_hour, day_index, month_index, year_index
from .policies import canonical, policy as policy_snapshot
from .relations import relations
from .tables import (BRANCH_ELEMENT, BRANCH_LABELS, BRANCHES, HIDDEN_RANKS, HIDDEN_STEMS,
                     STEM_ELEMENT, STEM_LABELS, STEMS, cycle_index, ganzhi, growth_stage, na_yin,
                     stem_yang, ten_god, void_branches)
from .timebase import (TZDATA, BirthInput, CalcError, Moment, equation_of_time, moment,
                       parse_local, parse_time, to_instant, zone)

SCHEMA_VERSION = 'chart-facts/1'
ENGINE = 'bazi-calc/1'
POSITIONS = ('year', 'month', 'day', 'hour')
DA_YUN_COUNT = 10
LIU_NIAN_YEARS = 100


def engine_manifest(policy: dict) -> dict:
    return {'engine': ENGINE, 'solar_terms': solar_terms.SOURCE, 'tzdata': TZDATA,
            'astronomical_model': 'sxwnl solar longitude with ΔT, via lunar-python',
            'eot_model': policy['eot_model'], 'lunar_vn': 'ho-ngoc-duc-1 (UTC+7)',
            'legacy_version': 'legacy/bazi tables, re-keyed to ASCII ids',
            'policy_hash': policy['policy_hash']}


# ---- pillars at one instant -------------------------------------------------------------

def _indexes(instant: datetime, clock: datetime, rollover: str) -> dict[str, int]:
    year, _ = year_index(instant)
    month, _, _ = month_index(instant, ganzhi(year)[0])
    day, hour, _ = day_and_hour(clock, rollover)
    return {'year': year, 'month': month, 'day': day, 'hour': hour}


def _pillar(index: int, position: str, day_stem: str, void: tuple[str, str]) -> dict:
    stem, branch = ganzhi(index)
    sound, sound_label, sound_element = na_yin(index)
    return {
        'stem': stem, 'branch': branch, 'stem_label': STEM_LABELS[stem],
        'branch_label': BRANCH_LABELS[branch], 'stem_element': STEM_ELEMENT[stem],
        'branch_element': BRANCH_ELEMENT[branch], 'polarity': 'yang' if stem_yang(stem) else 'yin',
        'cycle_index': index,
        # The day stem is the day master itself, not one of its ten gods.
        'ten_god': None if position == 'day' else ten_god(stem, day_stem),
        'hidden_stems': [{'stem': s, 'rank': HIDDEN_RANKS[i], 'ten_god': ten_god(s, day_stem)}
                         for i, s in enumerate(HIDDEN_STEMS[branch])],
        'growth_stage': growth_stage(day_stem, branch), 'na_yin': sound,
        'na_yin_label': sound_label, 'na_yin_element': sound_element, 'void': branch in void,
    }


# ---- intervals ----------------------------------------------------------------------------

def _clock(instant: datetime, tz, basis: str, longitude: float | None) -> datetime:
    return moment(instant, tz, basis, longitude).pillar_clock


def _clock_to_instant(wall: datetime, tz, basis: str, longitude: float | None) -> datetime | None:
    if basis == 'civil':
        try:
            return to_instant(wall, tz, 0)
        except CalcError:
            return None                      # inside a DST gap: no instant has this clock
    guess = wall - timedelta(minutes=4 * longitude)
    for _ in range(3):                       # the equation of time moves slowly
        guess = wall - timedelta(minutes=4 * longitude + equation_of_time(
            guess.replace(tzinfo=timezone.utc)))
    return guess.replace(tzinfo=timezone.utc)


def _breakpoints(lo: datetime, hi: datetime, tz, basis: str, longitude) -> list[tuple[datetime, str]]:
    """Instants in (lo, hi] where a pillar may change: jie terms (by key) and 'clock'."""
    points = [(t.instant, t.key) for t in solar_terms.between(lo, hi, jie_only=True)]
    first, last = _clock(lo, tz, basis, longitude), _clock(hi, tz, basis, longitude)
    wall = first.replace(minute=0, second=0, microsecond=0)
    while wall <= last + timedelta(hours=1):
        if wall.hour % 2 == 1 or wall.hour == 0:
            instant = _clock_to_instant(wall, tz, basis, longitude)
            if instant is not None and lo < instant <= hi:
                points.append((instant, 'clock'))
        wall += timedelta(hours=1)
    return sorted(set(points))


def _segments(lo: datetime, hi: datetime, tz, policy: dict, longitude, with_hour: bool) -> list[dict]:
    basis, rollover = policy['clock_basis'], policy['day_rollover']

    def state(instant: datetime) -> dict[str, int]:
        found = _indexes(instant, _clock(instant, tz, basis, longitude), rollover)
        if not with_hour:
            found.pop('hour')
        return found

    segments = [{'from': lo, 'reasons': [], 'indexes': state(lo)}]
    for instant, kind in _breakpoints(lo, hi, tz, basis, longitude):
        current = state(instant)
        if current != segments[-1]['indexes']:
            changed = [p for p in current if current[p] != segments[-1]['indexes'][p]]
            causes = {'day': 'day_rollover', 'hour': 'hour_boundary'}
            segments.append({'from': instant, 'indexes': current, 'reasons': [
                {'position': p, 'cause': kind if kind != 'clock' else causes.get(p, 'clock')}
                for p in changed]})
    for here, following in zip(segments, segments[1:]):
        here['to'] = following['from']
    segments[-1]['to'] = hi
    return segments


# ---- luck cycles ----------------------------------------------------------------------------

def _add_months(moment_: datetime, months: int) -> datetime:
    month = moment_.month - 1 + months
    year, month = moment_.year + month // 12, month % 12 + 1
    last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
    return moment_.replace(year=year, month=month, day=min(moment_.day, last))


def _slot(clock: datetime) -> int:
    # Two-hour slots counted through the civil day; 23:00-24:00 is the day's last slot.
    return 11 if clock.hour == 23 else ((clock.hour + 1) // 2) % 12


def _start_components(start: datetime, end: datetime, method: str) -> dict:
    """Age at which the first luck pillar starts, from the span birth↔jie (civil clocks).

    traditional_units: calendar days and two-hour slots between the two civil clocks;
    3 days = 1 year, 1 day = 4 months, 1 slot = 10 days (lunar-python sect 1).
    minute_units: exact minutes; 4320 min = 1 year, 360 = 1 month, 12 = 1 day, 1 = 2 hours
    (lunar-python sect 2).
    """
    if method == 'minute_units':
        # Whole minutes of both clocks (seconds dropped), as in lunar-python sect 2.
        minutes = int((end.replace(second=0, microsecond=0)
                       - start.replace(second=0, microsecond=0)).total_seconds() // 60)
        years, rest = divmod(minutes, 4320)
        months, rest = divmod(rest, 360)
        days, rest = divmod(rest, 12)
        return {'years': years, 'months': months, 'days': days, 'hours': rest * 2}
    slots = _slot(end) - _slot(start)
    days = (end.date() - start.date()).days
    if slots < 0:
        slots += 12
        days -= 1
    extra_months = slots * 10 // 30
    years, months = divmod(days * 4 + extra_months, 12)
    return {'years': years, 'months': months, 'days': slots * 10 - extra_months * 30, 'hours': 0}


def _start_instant(birth_civil: datetime, parts: dict, tz) -> datetime:
    """Add the components on the civil calendar of the birth place, then back to UTC."""
    moved = _add_months(birth_civil, parts['years'] * 12 + parts['months'])
    moved += timedelta(days=parts['days'], hours=parts['hours'])
    try:
        return to_instant(moved, tz, 0)
    except CalcError:                        # lands in a DST gap: the clock skips ahead
        return to_instant(moved + timedelta(hours=1), tz, 0)


def cycles(instant: datetime, month: int, year_stem: str, sex: str, method: str,
           exact: bool, window: tuple[datetime, datetime], tz) -> dict:
    forward = None if sex == 'unspecified' else (stem_yang(year_stem) == (sex == 'male'))
    result: dict = {'direction': None if forward is None else ('forward' if forward else 'backward'),
                    'start_method': method, 'start_age_components': None,
                    'start_instant': None, 'start_range_utc': None, 'da_yun': None}
    if forward is not None:
        def start(at: datetime) -> tuple[dict, datetime]:
            previous, following = solar_terms.neighbours(at)
            civil = at.astimezone(tz).replace(tzinfo=None)
            jie = (following if forward else previous).instant.astimezone(tz).replace(tzinfo=None)
            parts = _start_components(civil, jie, method) if forward else _start_components(
                jie, civil, method)
            return parts, _start_instant(civil, parts, tz)
        if exact:
            parts, begins = start(instant)
            result.update(start_age_components=parts, start_instant=solar_terms.iso_utc(begins))
        else:
            first, last = (start(window[0])[1], start(window[1])[1])
            result['start_range_utc'] = sorted([solar_terms.iso_utc(first), solar_terms.iso_utc(last)])
            begins = None
        step = 1 if forward else -1
        result['da_yun'] = []
        for k in range(1, DA_YUN_COUNT + 1):
            stem, branch = ganzhi((month + step * k) % 60)
            entry = {'index': k, 'stem': stem, 'branch': branch, 'start': None, 'end': None}
            if begins is not None:
                entry['start'] = solar_terms.iso_utc(_add_months(begins, 120 * (k - 1)))
                entry['end'] = solar_terms.iso_utc(_add_months(begins, 120 * k))
            result['da_yun'].append(entry)
    _, solar_year = year_index(instant)
    liu_nian = []
    for year in range(solar_year, solar_year + LIU_NIAN_YEARS + 1):
        if year + 1 > solar_terms.LAST_YEAR:
            break
        stem, branch = ganzhi((year - 4) % 60)
        opens = solar_terms.term_in_year('li_chun', year).instant
        liu_nian.append({'solar_term_year': year, 'stem': stem, 'branch': branch,
                         # The first year is only the part after the birth.
                         'start_instant': solar_terms.iso_utc(max(opens, window[0])),
                         'end_instant': solar_terms.iso_utc(
                             solar_terms.term_in_year('li_chun', year + 1).instant)})
    result['liu_nian'] = liu_nian
    return result


# ---- the chart ---------------------------------------------------------------------------------

def _local_date_time(birth: BirthInput) -> tuple[date, time | None]:
    if birth.calendar_system == 'gregorian':
        local = parse_local(birth.local_datetime)
        return local.date(), local.time()
    lunar_date = birth.lunar_date
    day = lunar.to_solar(birth.calendar_system, lunar_date.year, lunar_date.month,
                         lunar_date.day, lunar_date.is_leap_month)
    return day, parse_time(birth.local_time)


def _window(birth: BirthInput, day: date, clock: time, tz) -> tuple[datetime, datetime, datetime]:
    """(anchor, lo, hi): the stated instant and the interval the birth may lie in."""
    spread = timedelta(minutes=birth.uncertainty_minutes)
    if birth.time_accuracy == 'unknown':
        lo = to_instant(datetime.combine(day, time()), tz, 0)
        hi = to_instant(datetime.combine(day + timedelta(days=1), time()), tz, 0) - timedelta(
            seconds=1)
        return lo, lo, hi
    local = datetime.combine(day, clock)
    if birth.time_accuracy == 'hour':
        start = to_instant(local.replace(minute=0, second=0), tz, birth.fold)
        return to_instant(local, tz, birth.fold), start - spread, start + timedelta(
            minutes=59, seconds=59) + spread
    anchor = to_instant(local, tz, birth.fold)
    return anchor, anchor - spread, anchor + spread


def _time_facts(moment_: Moment, previous, following) -> dict:
    return {'birth_instant_utc': solar_terms.iso_utc(moment_.instant),
            'civil_local': moment_.civil.replace(tzinfo=None).isoformat(),
            'pillar_clock_local': moment_.pillar_clock.replace(microsecond=0).isoformat(),
            'utc_offset_seconds': int(moment_.civil.utcoffset().total_seconds()),
            'fold': moment_.civil.fold, 'eot_minutes': moment_.eot_minutes,
            'longitude_correction_minutes': moment_.longitude_correction_minutes,
            'previous_jie': previous.as_fact(), 'next_jie': following.as_fact()}


def compute(birth: BirthInput) -> dict:
    policy = policy_snapshot(birth.policy_id)
    tz = zone(birth.timezone)
    day, clock = _local_date_time(birth)
    anchor, lo, hi = _window(birth, day, clock, tz)
    if not (solar_terms.in_range(lo) and solar_terms.in_range(hi)):
        raise CalcError('UNSUPPORTED_RANGE', f'births {solar_terms.FIRST_YEAR}–'
                        f'{solar_terms.LAST_YEAR} only (oracle range)', 'local_datetime')
    basis, rollover = policy['clock_basis'], policy['day_rollover']
    exact = lo == hi
    with_hour = birth.time_accuracy != 'unknown'
    warnings: list[dict] = []
    segments = _segments(lo, hi, tz, policy, birth.longitude, with_hour)
    stable = {p: segments[0]['indexes'][p] for p in segments[0]['indexes']
              if all(s['indexes'][p] == segments[0]['indexes'][p] for s in segments)}
    if exact:
        stable = _indexes(anchor, _clock(anchor, tz, basis, birth.longitude), rollover)
    uncertain = [p for p in POSITIONS if p not in stable and (p != 'hour' or with_hour)]
    if uncertain:
        warnings.append({'code': 'boundary_uncertainty', 'positions': uncertain,
                         'detail': 'the time interval crosses a pillar boundary; see variants'})
    if not with_hour:
        warnings.append({'code': 'approximate_time', 'positions': ['hour'],
                         'detail': 'hour unknown: no hour pillar, nothing assumed'})

    day_idx = stable.get('day')
    day_stem = ganzhi(day_idx)[0] if day_idx is not None else None
    void = void_branches(day_idx) if day_idx is not None else ()
    pillars: dict = {}
    for position in POSITIONS:
        index = stable.get(position)
        pillars[position] = (_pillar(index, position, day_stem, void)
                             if index is not None and day_stem is not None else None)
    if day_stem is None:
        # Without a day master no ten god or stage exists; keep the bare pairs visible.
        warnings.append({'code': 'day_master_uncertain', 'positions': ['day'],
                         'detail': 'ten gods, stages and void depend on the day stem'})
        for position, index in stable.items():
            stem, branch = ganzhi(index)
            pillars[position] = {'stem': stem, 'branch': branch, 'stem_label': STEM_LABELS[stem],
                                 'branch_label': BRANCH_LABELS[branch], 'cycle_index': index}

    variants = [] if len(segments) == 1 else [
        {'from_utc': solar_terms.iso_utc(s['from']), 'to_utc': solar_terms.iso_utc(s['to']),
         'reasons': s['reasons'],
         'pillars': {p: dict(zip(('stem', 'branch'), ganzhi(i))) for p, i in s['indexes'].items()}}
        for s in segments]

    anchor_moment = moment(anchor, tz, basis, birth.longitude)
    previous, following = solar_terms.neighbours(anchor)
    year_idx = stable.get('year', segments[0]['indexes']['year'])
    month_idx = stable.get('month')
    luck = None
    if month_idx is not None:
        luck = cycles(anchor, month_idx, ganzhi(year_idx)[0], birth.sex_for_luck,
                      policy['yun_method'], exact, (lo, hi), tz)
        if luck['direction'] is None:
            warnings.append({'code': 'luck_direction_unknown', 'positions': [],
                             'detail': 'sex_for_luck unspecified: luck pillars not computed'})
    present = {p: (v['stem'], v['branch']) for p, v in pillars.items() if v}
    auxiliary = _auxiliary(pillars, present)
    if auxiliary['ming_gong'] is not None:
        warnings.append({'code': 'pending_auxiliary_validation', 'positions': [],
                         'detail': 'ming_gong/tai_yuan follow the legacy formulas; not rule facts'})
    nearest = min((abs((t.instant - anchor).total_seconds()), t) for t in (previous, following))
    if exact and nearest[0] <= solar_terms.TOLERANCE_SECONDS:
        warnings.append({'code': 'near_solar_term', 'positions': ['year', 'month'] if
                         nearest[1].key == 'li_chun' else ['month'],
                         'detail': f'{int(nearest[0])} s from {nearest[1].key}; the solar-term'
                                   f' model is accurate to about {solar_terms.TOLERANCE_SECONDS} s'})
    if (birth.timezone == 'Asia/Ho_Chi_Minh' and 1942 <= day.year <= 1975
            and anchor_moment.civil.utcoffset() != timedelta(hours=7)):
        warnings.append({'code': 'historical_offset', 'positions': [],
                         'detail': 'Asia/Ho_Chi_Minh follows Saigon (UTC+8 in parts of 1942-1975);'
                                   ' northern births of that period used UTC+7 (Asia/Bangkok)'})

    facts = {
        'schema_version': SCHEMA_VERSION,
        'input_snapshot': birth.model_dump(mode='json'),
        'normalized_time': {**_time_facts(anchor_moment, previous, following),
                            'clock_basis': basis, 'time_accuracy': birth.time_accuracy,
                            'interval_utc': None if exact else [solar_terms.iso_utc(lo),
                                                                solar_terms.iso_utc(hi)]},
        'policy_snapshot': policy,
        'engine_manifest': engine_manifest(policy),
        'pillars': pillars,
        'relations': relations(present),
        'cycles': luck,
        'auxiliary': auxiliary,
        'warnings': warnings,
        'variants': variants,
    }
    facts['facts_hash'] = facts_hash(facts)
    return facts


def facts_hash(facts: dict) -> str:
    """SHA-256 of the canonical facts, without the hash itself."""
    body = {k: v for k, v in facts.items() if k not in ('facts_hash', 'chart_id', 'computed_at')}
    return hashlib.sha256(canonical(body).encode('utf-8')).hexdigest()


def _auxiliary(pillars: dict, present: dict) -> dict:
    counts = {e: 0 for e in ('wood', 'fire', 'earth', 'metal', 'water')}
    for stem, branch in present.values():
        counts[STEM_ELEMENT[stem]] += 1
        counts[BRANCH_ELEMENT[branch]] += 1
    month = present.get('month')
    tai_yuan = None
    if month:
        stem = STEMS[(STEMS.index(month[0]) + 1) % 10]
        branch = BRANCHES[(BRANCHES.index(month[1]) + 3) % 12]
        tai_yuan = {'stem': stem, 'branch': branch, 'method': 'month+1/+3'}
    ming_gong = None
    if month and present.get('hour') and present.get('year'):
        # Legacy formula: branch number counted from yin = 1, 26 − (month + hour).
        month_no = (BRANCHES.index(month[1]) - 2) % 12 + 1
        hour_no = (BRANCHES.index(present['hour'][1]) - 2) % 12 + 1
        number = 26 - (month_no + hour_no)
        number = number if number <= 12 else number - 12
        branch = BRANCHES[(number - 1 + 2) % 12]
        stem = STEMS[(STEMS.index(present['year'][0]) * 2 + 2 + (number - 1)) % 10]
        ming_gong = {'stem': stem, 'branch': branch, 'method': 'legacy-26-minus'}
    return {'element_counts': {**counts, 'basis': 'visible stems + branch elements'},
            'tai_yuan': tai_yuan, 'ming_gong': ming_gong,
            'heuristic_weighted_scores': None, 'interpretation_ready': False}


def cycle_pair(stem: str, branch: str) -> int:
    return cycle_index(stem, branch)
