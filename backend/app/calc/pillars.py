"""The four pillars from instants and clocks (docs/08 · Chính sách thời gian).

* year: changes at the Lập Xuân instant (physical time), not at lunar new year;
* month: changes at each of the twelve jie instants; stem by the five-tigers rule;
* day: the 60-day cycle of the pillar clock's calendar date (Julian day number);
* hour: two-hour branches with Zi from 23:00; stem by the five-rats rule from the day
  whose Zi hour it is, so 23:00-24:00 takes the next day's Zi stem in every policy;
  ``zi_start_23`` also moves the day pillar to the next day at 23:00.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import solar_terms
from .tables import BRANCHES, STEMS, cycle_index
from .timebase import julian_day_number


def year_index(instant: datetime) -> tuple[int, int]:
    """(60-cycle index, solar year) of the year pillar at a physical instant."""
    li_chun = solar_terms.term_in_year('li_chun', instant.year)
    solar_year = instant.year if instant >= li_chun.instant else instant.year - 1
    return (solar_year - 4) % 60, solar_year


def month_index(instant: datetime, year_stem: str) -> tuple[int, solar_terms.Term,
                                                             solar_terms.Term]:
    """(60-cycle index, jie that opened the month, next jie)."""
    previous, following = solar_terms.neighbours(instant)
    branch = solar_terms.JIE_BRANCH[previous.key]
    months_since_yin = (BRANCHES.index(branch) - 2) % 12
    stem = STEMS[(STEMS.index(year_stem) * 2 + 2 + months_since_yin) % 10]
    return cycle_index(stem, branch), previous, following


def day_index(day: date) -> int:
    return (julian_day_number(day) + 49) % 60


def hour_branch(clock: datetime) -> str:
    return BRANCHES[((clock.hour + 1) // 2) % 12]


def day_and_hour(clock: datetime, day_rollover: str) -> tuple[int, int, date]:
    """(day index, hour index, date of the day pillar) for a naive pillar clock."""
    late_zi = clock.hour == 23
    zi_day = clock.date() + timedelta(days=1) if late_zi else clock.date()
    pillar_date = zi_day if day_rollover == 'zi_start_23' else clock.date()
    branch = hour_branch(clock)
    stem = STEMS[(STEMS.index(STEMS[day_index(zi_day) % 10]) * 2 + BRANCHES.index(branch)) % 10]
    return day_index(pillar_date), cycle_index(stem, branch), pillar_date


def day_only(day: date) -> int:
    """Day pillar when the hour is unknown (midnight rollover)."""
    return day_index(day)
