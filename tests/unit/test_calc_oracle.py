"""Independent oracle and regression for the calculation engine (T029).

* Every solar term 1900-2100 from lunar-python (sxwnl) is compared with an independent
  VSOP87 ephemeris (PyEphem, apparent geocentric longitude of date). Both share no code.
* A frozen set of charts (tests/fixtures/charts/regression-v1.json) catches unintended
  changes; it is regression, not truth — truth comes from the oracle, the reference
  library cross-check (test_calc_engine) and the expert review still pending (docs/14).
"""
import json
import math
from datetime import timezone
from pathlib import Path
import unittest

from backend.app.calc import solar_terms
from backend.app.calc.chart import compute
from backend.app.calc.timebase import BirthInput

try:
    import ephem
except ImportError:  # dev dependency group
    ephem = None

FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures' / 'charts' / 'regression-v1.json'
LONGITUDE = {k: (315 + 15 * i) % 360 for i, k in enumerate(solar_terms.TERMS)}
TOLERANCE_S = 60


def apparent_longitude(when) -> float:
    sun = ephem.Sun()
    sun.compute(when, epoch=when)
    equatorial = ephem.Equatorial(sun.g_ra, sun.g_dec, epoch=when)  # apparent, of date
    return float(ephem.Ecliptic(equatorial, epoch=when).lon)


def crossing(degrees: float, guess):
    target, when = math.radians(degrees), ephem.Date(guess)
    for _ in range(30):
        error = (apparent_longitude(when) - target + math.pi) % (2 * math.pi) - math.pi
        step = error / (2 * math.pi / 365.2422)
        when = ephem.Date(when - step)
        if abs(step) < 1e-8:
            break
    return ephem.Date(when).datetime().replace(tzinfo=timezone.utc)


@unittest.skipIf(ephem is None, 'needs the dev dependency group (PyEphem)')
class SolarTermOracleTests(unittest.TestCase):
    def test_every_term_1900_2100_within_a_minute_of_vsop87(self):
        worst = 0.0
        count = 0
        for year in range(solar_terms.FIRST_YEAR, solar_terms.LAST_YEAR + 1):
            for term in (t for t in solar_terms._around(year) if t.instant.year == year):
                gap = abs((crossing(LONGITUDE[term.key], term.instant) - term.instant)
                          .total_seconds())
                worst = max(worst, gap)
                count += 1
                self.assertLessEqual(gap, TOLERANCE_S, (year, term.key))
        self.assertEqual(count, 24 * 201)
        self.assertLessEqual(worst, solar_terms.TOLERANCE_SECONDS)


def summary(facts: dict) -> dict:
    cycles = facts['cycles'] or {}
    return {
        'pillars': {p: v and [v['stem'], v['branch']] for p, v in facts['pillars'].items()},
        'birth_instant_utc': facts['normalized_time']['birth_instant_utc'],
        'pillar_clock_local': facts['normalized_time']['pillar_clock_local'],
        'direction': cycles.get('direction'),
        'start_age_components': cycles.get('start_age_components'),
        'first_da_yun': (cycles.get('da_yun') or [None])[0],
        'warnings': sorted(w['code'] for w in facts['warnings']),
        'variants': len(facts['variants']),
    }


class RegressionTests(unittest.TestCase):
    def test_frozen_charts_are_unchanged(self):
        cases = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(cases), 30)
        for case in cases:
            self.assertEqual(summary(compute(BirthInput(**case['input']))), case['expected'],
                             case['input'])


if __name__ == '__main__':
    unittest.main()
