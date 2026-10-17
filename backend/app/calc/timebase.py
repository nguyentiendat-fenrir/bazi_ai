"""Birth input and the instants it names (docs/08 · BirthInput, Chính sách thời gian).

* The wall clock is never given an offset by the caller: the IANA zone decides, from the
  pinned ``tzdata`` package only (not the host's copy), so every machine and every host
  TZ gives the same offset. A time that does not exist (DST gap) is refused; one that
  exists twice (DST fold) needs ``fold``.
* ``birth_instant_utc`` is the physical instant; the clock the day and hour pillars read
  (``pillar_clock_local``) is kept apart: the civil wall clock, or apparent solar time
  computed once from the instant (longitude + equation of time), never both.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from importlib import resources
from importlib.metadata import version
import math
import re
from typing import Literal
import zoneinfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .policies import DEFAULT_POLICY, POLICIES

TZDATA = f'tzdata {version("tzdata")}'
_LOCAL = re.compile(r'^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$')
_TIME = re.compile(r'^(\d{2}):(\d{2})(?::(\d{2}))?$')


class CalcError(ValueError):
    """A birth input the engine refuses; ``field`` names the input to fix."""

    def __init__(self, code: str, message: str, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.field = field


class LunarDate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    year: int = Field(ge=1900, le=2100)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=30)
    is_leap_month: bool = False


class BirthInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    calendar_system: Literal['gregorian', 'lunar_vn', 'lunar_cn'] = 'gregorian'
    local_datetime: str | None = Field(default=None, description='YYYY-MM-DDTHH:MM[:SS], no offset')
    lunar_date: LunarDate | None = None
    local_time: str | None = Field(default=None, description='HH:MM[:SS] with lunar_date')
    timezone: str = Field(min_length=1, max_length=64, description='IANA zone, e.g. Asia/Ho_Chi_Minh')
    fold: Literal[0, 1] | None = None
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    sex_for_luck: Literal['male', 'female', 'unspecified'] = 'unspecified'
    time_accuracy: Literal['minute', 'hour', 'unknown'] = 'minute'
    uncertainty_minutes: int = Field(default=0, ge=0, le=720)
    policy_id: str = DEFAULT_POLICY

    @model_validator(mode='after')
    def one_date_form(self) -> 'BirthInput':
        if self.calendar_system == 'gregorian':
            if self.local_datetime is None or self.lunar_date or self.local_time:
                raise ValueError('gregorian input takes local_datetime only')
        elif self.lunar_date is None or self.local_time is None or self.local_datetime:
            raise ValueError('lunar input takes lunar_date and local_time only')
        if self.policy_id not in POLICIES:
            raise ValueError(f'unknown policy {self.policy_id}')
        return self


@lru_cache(maxsize=64)
def zone(name: str) -> zoneinfo.ZoneInfo:
    """IANA zone from the pinned tzdata package; CalcError for an unknown name."""
    parts = name.split('/')
    if not all(re.fullmatch(r'[A-Za-z0-9_+\-]+', p) for p in parts):
        raise CalcError('TIMEZONE_UNKNOWN', f'{name} is not an IANA time zone', 'timezone')
    try:
        source = resources.files('tzdata.zoneinfo').joinpath(*parts)
        with source.open('rb') as handle:
            return zoneinfo.ZoneInfo.from_file(handle, key=name)
    except (OSError, ValueError):
        raise CalcError('TIMEZONE_UNKNOWN', f'{name} is not an IANA time zone',
                        'timezone') from None


def parse_local(text: str, field: str = 'local_datetime') -> datetime:
    match = _LOCAL.match(text or '')
    if not match:
        raise CalcError('INVALID_DATETIME', 'use YYYY-MM-DDTHH:MM[:SS] without an offset; the'
                        ' time zone gives the offset', field)
    try:
        return datetime(*(int(g or 0) for g in match.groups()))
    except ValueError as exc:
        raise CalcError('INVALID_DATETIME', str(exc), field) from None


def parse_time(text: str) -> time:
    match = _TIME.match(text or '')
    if not match:
        raise CalcError('INVALID_DATETIME', 'use HH:MM[:SS]', 'local_time')
    try:
        return time(*(int(g or 0) for g in match.groups()))
    except ValueError as exc:
        raise CalcError('INVALID_DATETIME', str(exc), 'local_time') from None


def to_instant(local: datetime, tz: zoneinfo.ZoneInfo, fold: int | None) -> datetime:
    """Wall clock → aware instant; refuses a DST gap, needs ``fold`` in a DST fold."""
    options = []
    for candidate_fold in (0, 1):
        aware = local.replace(tzinfo=tz, fold=candidate_fold)
        back = aware.astimezone(timezone.utc).astimezone(tz)
        if back.replace(tzinfo=None) == local:
            options.append((candidate_fold, aware))
    if not options:
        raise CalcError('NONEXISTENT_TIME', f'{local.isoformat()} does not exist in {tz.key}'
                        ' (clocks moved forward); check the time', 'local_datetime')
    offsets = {aware.utcoffset() for _, aware in options}
    if len(offsets) > 1:
        if fold is None:
            raise CalcError('AMBIGUOUS_TIME', f'{local.isoformat()} happened twice in {tz.key};'
                            ' set fold 0 (first) or 1 (second)', 'fold')
        return dict(options)[fold]
    return options[0][1]


def equation_of_time(instant: datetime) -> float:
    """Minutes apparent minus mean solar time (NOAA, after Spencer 1971; ~±30 s)."""
    utc = instant.astimezone(timezone.utc)
    day = utc.timetuple().tm_yday
    hours = utc.hour + utc.minute / 60 + utc.second / 3600
    leap = 366 if utc.year % 4 == 0 and (utc.year % 100 != 0 or utc.year % 400 == 0) else 365
    g = 2 * math.pi / leap * (day - 1 + (hours - 12) / 24)
    return 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                     - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))


@dataclass(frozen=True)
class Moment:
    instant: datetime            # physical, aware UTC
    civil: datetime              # aware civil wall clock in the birth zone
    pillar_clock: datetime       # naive clock the day/hour pillars read
    eot_minutes: float | None
    longitude_correction_minutes: float | None


def moment(instant: datetime, tz: zoneinfo.ZoneInfo, clock_basis: str,
           longitude: float | None) -> Moment:
    civil = instant.astimezone(tz)
    if clock_basis == 'civil':
        return Moment(instant.astimezone(timezone.utc), civil, civil.replace(tzinfo=None),
                      None, None)
    if longitude is None:
        raise CalcError('LONGITUDE_REQUIRED', 'apparent solar time needs the birth longitude',
                        'longitude')
    eot = equation_of_time(instant)
    solar = instant.astimezone(timezone.utc).replace(tzinfo=None) + timedelta(
        minutes=4 * longitude + eot)
    offset = civil.utcoffset().total_seconds() / 60
    return Moment(instant.astimezone(timezone.utc), civil, solar, round(eot, 2),
                  round(4 * longitude - offset, 2))


def julian_day_number(day: date) -> int:
    return day.toordinal() + 1721425
