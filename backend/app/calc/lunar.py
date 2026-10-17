"""Lunar → Gregorian dates for birth input (docs/08 · lịch âm).

* ``lunar_cn``: the Chinese calendar of lunar-python (new moons and terms in UTC+8).
* ``lunar_vn``: the Vietnamese calendar, which counts days in UTC+7; computed with Hồ
  Ngọc Đức's published algorithm (Meeus new moons, low-precision solar longitude). The two
  differ in some years (e.g. Tết 1985, Tết 2007), which is why both are separate inputs.
"""
from __future__ import annotations

from datetime import date
from math import floor, pi, sin

from lunar_python import Lunar

from .timebase import CalcError

_SYNODIC = 29.530588853


def _jd(day: date) -> int:
    return day.toordinal() + 1721425


def _date(jd: int) -> date:
    return date.fromordinal(jd - 1721425)


def _new_moon(k: int) -> float:
    t = k / 1236.85
    t2, t3 = t * t, t * t * t
    dr = pi / 180
    jd1 = 2415020.75933 + 29.53058868 * k + 0.0001178 * t2 - 0.000000155 * t3
    jd1 += 0.00033 * sin((166.56 + 132.87 * t - 0.009173 * t2) * dr)
    m = 359.2242 + 29.10535608 * k - 0.0000333 * t2 - 0.00000347 * t3
    mpr = 306.0253 + 385.81691806 * k + 0.0107306 * t2 + 0.00001236 * t3
    f = 21.2964 + 390.67050646 * k - 0.0016528 * t2 - 0.00000239 * t3
    c1 = (0.1734 - 0.000393 * t) * sin(m * dr) + 0.0021 * sin(2 * dr * m)
    c1 = c1 - 0.4068 * sin(mpr * dr) + 0.0161 * sin(dr * 2 * mpr)
    c1 = c1 - 0.0004 * sin(dr * 3 * mpr)
    c1 = c1 + 0.0104 * sin(dr * 2 * f) - 0.0051 * sin(dr * (m + mpr))
    c1 = c1 - 0.0074 * sin(dr * (m - mpr)) + 0.0004 * sin(dr * (2 * f + m))
    c1 = c1 - 0.0004 * sin(dr * (2 * f - m)) - 0.0006 * sin(dr * (2 * f + mpr))
    c1 = c1 + 0.0010 * sin(dr * (2 * f - mpr)) + 0.0005 * sin(dr * (2 * mpr + m))
    if t < -11:
        delta_t = 0.001 + 0.000839 * t + 0.0002261 * t2 - 0.00000845 * t3 - 0.000000081 * t * t3
    else:
        delta_t = -0.000278 + 0.000265 * t + 0.000262 * t2
    return jd1 + c1 - delta_t


def _sun_longitude(jdn: float) -> float:
    t = (jdn - 2451545.0) / 36525
    t2 = t * t
    dr = pi / 180
    m = 357.52910 + 35999.05030 * t - 0.0001559 * t2 - 0.00000048 * t * t2
    l0 = 280.46645 + 36000.76983 * t + 0.0003032 * t2
    dl = (1.914600 - 0.004817 * t - 0.000014 * t2) * sin(dr * m)
    dl += (0.019993 - 0.000101 * t) * sin(dr * 2 * m) + 0.000290 * sin(dr * 3 * m)
    longitude = (l0 + dl) * dr
    return longitude - pi * 2 * floor(longitude / (pi * 2))


def _sun_segment(day_number: int, zone: float) -> int:
    return floor(_sun_longitude(day_number - 0.5 - zone / 24) / pi * 6)


def _new_moon_day(k: int, zone: float) -> int:
    return floor(_new_moon(k) + 0.5 + zone / 24)


def _month11(year: int, zone: float) -> int:
    k = floor((_jd(date(year, 12, 31)) - 2415021) / _SYNODIC)
    new_moon = _new_moon_day(k, zone)
    if _sun_segment(new_moon, zone) >= 9:
        new_moon = _new_moon_day(k - 1, zone)
    return new_moon


def _leap_offset(a11: int, zone: float) -> int:
    k = floor((a11 - 2415021.076998695) / _SYNODIC + 0.5)
    i = 1
    arc = _sun_segment(_new_moon_day(k + i, zone), zone)
    while True:
        last = arc
        i += 1
        arc = _sun_segment(_new_moon_day(k + i, zone), zone)
        if arc == last or i >= 14:
            break
    return i - 1


def vn_to_solar(year: int, month: int, day: int, leap: bool, zone: float = 7.0) -> date:
    if month < 11:
        a11, b11 = _month11(year - 1, zone), _month11(year, zone)
    else:
        a11, b11 = _month11(year, zone), _month11(year + 1, zone)
    k = floor(0.5 + (a11 - 2415021.076998695) / _SYNODIC)
    offset = month - 11
    if offset < 0:
        offset += 12
    if b11 - a11 > 365:
        leap_offset = _leap_offset(a11, zone)
        leap_month = leap_offset - 2
        if leap_month < 0:
            leap_month += 12
        if leap and month != leap_month:
            raise CalcError('INVALID_LUNAR_DATE', f'{year} has no leap month {month}',
                            'lunar_date')
        if leap or offset >= leap_offset:
            offset += 1
    elif leap:
        raise CalcError('INVALID_LUNAR_DATE', f'{year} has no leap month', 'lunar_date')
    start = _new_moon_day(k + offset, zone)
    if day > _new_moon_day(k + offset + 1, zone) - start:
        raise CalcError('INVALID_LUNAR_DATE', f'lunar month {month}/{year} is shorter than'
                        f' {day} days', 'lunar_date')
    return _date(start + day - 1)


def solar_to_vn(day: date, zone: float = 7.0) -> tuple[int, int, int, bool]:
    """(year, month, day, leap) of a Gregorian date in the Vietnamese calendar."""
    number = _jd(day)
    k = floor((number - 2415021.076998695) / _SYNODIC)
    month_start = _new_moon_day(k + 1, zone)
    if month_start > number:
        month_start = _new_moon_day(k, zone)
    a11 = _month11(day.year, zone)
    b11 = a11
    if a11 >= month_start:
        lunar_year = day.year
        a11 = _month11(day.year - 1, zone)
    else:
        lunar_year = day.year + 1
        b11 = _month11(day.year + 1, zone)
    lunar_day = number - month_start + 1
    diff = floor((month_start - a11) / 29)
    leap = False
    lunar_month = diff + 11
    if b11 - a11 > 365:
        leap_diff = _leap_offset(a11, zone)
        if diff >= leap_diff:
            lunar_month = diff + 10
            leap = diff == leap_diff
    if lunar_month > 12:
        lunar_month -= 12
    if lunar_month >= 11 and diff < 4:
        lunar_year -= 1
    return lunar_year, lunar_month, lunar_day, leap


def cn_to_solar(year: int, month: int, day: int, leap: bool) -> date:
    try:
        # Negative month = leap month; lunar-python refuses impossible dates itself.
        solar = Lunar.fromYmd(year, -month if leap else month, day).getSolar()
    except Exception as exc:  # it raises a plain Exception with the reason
        raise CalcError('INVALID_LUNAR_DATE', f'not a valid Chinese lunar date: {exc}',
                        'lunar_date') from None
    return date(solar.getYear(), solar.getMonth(), solar.getDay())


def to_solar(calendar: str, year: int, month: int, day: int, leap: bool) -> date:
    if calendar == 'lunar_vn':
        return vn_to_solar(year, month, day, leap)
    return cn_to_solar(year, month, day, leap)
