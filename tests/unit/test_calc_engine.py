"""Calculation engine (T026-T028): pillars, time policies, uncertainty, cycles, lunar input."""
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import unittest
from datetime import datetime, timedelta

from pydantic import ValidationError

from backend.app.calc import policies, solar_terms
from backend.app.calc.chart import compute
from backend.app.calc.relations import relations
from backend.app.calc.tables import cycle_index, ganzhi, growth_stage, void_branches
from backend.app.calc.timebase import BirthInput, CalcError

ROOT = Path(__file__).resolve().parents[2]


def chart(**kwargs) -> dict:
    kwargs.setdefault('timezone', 'Asia/Ho_Chi_Minh')
    return compute(BirthInput(**kwargs))


def pairs(facts: dict) -> dict:
    return {p: v and (v['stem'], v['branch']) for p, v in facts['pillars'].items()}


class TableTests(unittest.TestCase):
    def test_sexagenary_cycle_and_fixed_tables(self):
        self.assertEqual([cycle_index(*ganzhi(i)) for i in range(60)], list(range(60)))
        with self.assertRaises(ValueError):
            cycle_index('jia', 'chou')                       # mixed polarity is no pair
        self.assertEqual(growth_stage('jia', 'hai'), 'changsheng')
        self.assertEqual(growth_stage('yi', 'wu'), 'changsheng')
        self.assertEqual(growth_stage('yi', 'si'), 'muyu')   # yin stems run backward
        self.assertEqual(void_branches(0), ('xu', 'hai'))     # jia zi decade
        self.assertEqual(void_branches(cycle_index('jia', 'yin')), ('zi', 'chou'))

    def test_relations_keep_multiplicity_and_completeness(self):
        found = relations({'year': ('jia', 'zi'), 'month': ('geng', 'wu'), 'day': ('bing', 'zi'),
                           'hour': ('wu', 'chen')})
        clashes = [r for r in found if r['type'] == 'clash']
        self.assertEqual([r['positions'] for r in clashes], [['year', 'month'], ['month', 'day']])
        three = [r for r in found if r['type'] == 'three_combination']
        self.assertEqual((three[0]['completeness'], three[0]['members'], three[0]['element']),
                         ('partial', ['zi', 'zi', 'chen'], 'water'))
        self.assertTrue(any(r['type'] == 'half_combination' for r in found))
        self.assertTrue(any(r['type'] == 'stem_clash' and r['members'] == ['jia', 'geng']
                            for r in found))
        full = relations({'year': ('geng', 'shen'), 'month': ('bing', 'zi'),
                          'day': ('jia', 'chen'), 'hour': None})
        self.assertEqual([r['completeness'] for r in full if r['type'] == 'three_combination'],
                         ['full'])
        self.assertFalse(any(r['conditions_evaluated'] for r in found + full))


class PillarTests(unittest.TestCase):
    def test_pillar_details_follow_the_day_master(self):
        facts = chart(local_datetime='2024-02-04T23:30:00', timezone='Asia/Shanghai')
        self.assertEqual(pairs(facts), {'year': ('jia', 'chen'), 'month': ('bing', 'yin'),
                                        'day': ('wu', 'xu'), 'hour': ('jia', 'zi')})
        day, month = facts['pillars']['day'], facts['pillars']['month']
        self.assertIsNone(day['ten_god'])                   # the day master itself
        self.assertEqual(month['ten_god'], 'indirect_resource')  # bing for a wu day master
        self.assertEqual([(h['stem'], h['rank']) for h in month['hidden_stems']],
                         [('jia', 'main'), ('bing', 'middle'), ('wu', 'residual')])
        self.assertEqual(month['growth_stage'], 'changsheng')  # wu at yin
        self.assertEqual((day['na_yin'], day['na_yin_label']), ('ping_di_mu', 'Bình địa Mộc'))
        self.assertTrue(facts['pillars']['day']['void'] is False)
        self.assertRegex(facts['facts_hash'], r'^[0-9a-f]{64}$')

    def test_year_and_month_change_at_the_li_chun_instant(self):
        li_chun = solar_terms.term_in_year('li_chun', 2024).instant      # 08:27:07 UTC
        for zone, hours in (('Asia/Ho_Chi_Minh', 7), ('Asia/Shanghai', 8)):
            for delta, after in ((-1, False), (1, True), (-60, False), (60, True),
                                 (-3600, False), (3600, True)):
                local = li_chun + timedelta(hours=hours, seconds=delta)
                facts = chart(local_datetime=local.strftime('%Y-%m-%dT%H:%M:%S'), timezone=zone)
                expected = (('jia', 'chen'), ('bing', 'yin')) if after else (('gui', 'mao'),
                                                                              ('yi', 'chou'))
                self.assertEqual((pairs(facts)['year'], pairs(facts)['month']), expected,
                                 (zone, delta))
                near = any(w['code'] == 'near_solar_term' for w in facts['warnings'])
                self.assertEqual(near, abs(delta) <= solar_terms.TOLERANCE_SECONDS, (zone, delta))

    def test_zi_hour_under_each_day_policy(self):
        expected = {
            'standard-v1': [('wu', 'xu'), ('wu', 'xu'), ('wu', 'xu'), ('ji', 'hai'), ('ji', 'hai')],
            'zi23-v1': [('wu', 'xu'), ('ji', 'hai'), ('ji', 'hai'), ('ji', 'hai'), ('ji', 'hai')],
        }
        times = ('2024-02-04T22:59', '2024-02-04T23:00', '2024-02-04T23:59', '2024-02-05T00:00',
                 '2024-02-05T00:01')
        for policy, days in expected.items():
            found = [pairs(chart(local_datetime=t, policy_id=policy)) for t in times]
            self.assertEqual([f['day'] for f in found], days, policy)
            # 23:00-24:00 is the next day's Zi hour in both policies.
            self.assertEqual([f['hour'] for f in found],
                             [('gui', 'hai')] + [('jia', 'zi')] * 4, policy)

    def test_matches_the_reference_library_at_a_fixed_utc_plus_8(self):
        from lunar_python import Solar
        policies.POLICIES.setdefault('minute-units-test', {**policies.POLICIES['standard-v1'],
                                                           'yun_method': 'minute_units'})
        cn = dict(zip('甲乙丙丁戊己庚辛壬癸', ('jia', 'yi', 'bing', 'ding', 'wu', 'ji', 'geng',
                                            'xin', 'ren', 'gui')))
        zh = dict(zip('子丑寅卯辰巳午未申酉戌亥', ('zi', 'chou', 'yin', 'mao', 'chen', 'si', 'wu',
                                                'wei', 'shen', 'you', 'xu', 'hai')))
        rng = random.Random(26)
        for _ in range(120):
            t = datetime(1901, 1, 1) + timedelta(minutes=rng.randrange(0, 199 * 365 * 1440))
            sex = rng.choice(('male', 'female'))
            ref = Solar.fromYmdHms(t.year, t.month, t.day, t.hour, t.minute, 0).getLunar()
            eight = ref.getEightChar()
            expected = {p: (cn[g[0]], zh[g[1]]) for p, g in zip(
                ('year', 'month', 'day', 'hour'),
                (eight.getYear(), eight.getMonth(), eight.getDay(), eight.getTime()))}
            for policy, sect in (('standard-v1', 1), ('minute-units-test', 2)):
                facts = chart(local_datetime=t.strftime('%Y-%m-%dT%H:%M'), timezone='Etc/GMT-8',
                              sex_for_luck=sex, policy_id=policy)
                self.assertEqual(pairs(facts), expected, t)
                yun = eight.getYun(1 if sex == 'male' else 0, sect)
                parts = facts['cycles']['start_age_components']
                self.assertEqual((parts['years'], parts['months'], parts['days'], parts['hours']),
                                 (yun.getStartYear(), yun.getStartMonth(), yun.getStartDay(),
                                  yun.getStartHour()), (t, policy))
                self.assertEqual([(d['stem'], d['branch']) for d in facts['cycles']['da_yun'][:3]],
                                 [(cn[d.getGanZhi()[0]], zh[d.getGanZhi()[1]])
                                  for d in yun.getDaYun()[1:4]])


class TimeTests(unittest.TestCase):
    def test_dst_gap_is_refused_and_a_fold_must_be_chosen(self):
        with self.assertRaises(CalcError) as caught:
            chart(local_datetime='2021-03-14T02:30', timezone='America/New_York')
        self.assertEqual((caught.exception.code, caught.exception.field),
                         ('NONEXISTENT_TIME', 'local_datetime'))
        with self.assertRaises(CalcError) as caught:
            chart(local_datetime='2021-11-07T01:30', timezone='America/New_York')
        self.assertEqual(caught.exception.code, 'AMBIGUOUS_TIME')
        first = chart(local_datetime='2021-11-07T01:30', timezone='America/New_York', fold=0)
        second = chart(local_datetime='2021-11-07T01:30', timezone='America/New_York', fold=1)
        self.assertEqual((first['normalized_time']['birth_instant_utc'],
                          second['normalized_time']['birth_instant_utc']),
                         ('2021-11-07T05:30:00Z', '2021-11-07T06:30:00Z'))

    def test_input_is_validated_before_anything_is_computed(self):
        for bad, code in ((dict(local_datetime='2024-01-01T10:00+07:00'), 'INVALID_DATETIME'),
                          (dict(local_datetime='1900-02-29T10:00'), 'INVALID_DATETIME'),
                          (dict(local_datetime='2024-01-01T10:00', timezone='Mars/Base'),
                           'TIMEZONE_UNKNOWN'),
                          (dict(local_datetime='1899-12-01T10:00'), 'UNSUPPORTED_RANGE'),
                          (dict(local_datetime='2024-06-01T10:00', policy_id='solar-time-v1'),
                           'LONGITUDE_REQUIRED')):
            with self.assertRaises(CalcError) as caught:
                chart(**bad)
            self.assertEqual(caught.exception.code, code, bad)
        for bad in (dict(local_datetime='2024-01-01T10:00', color='red'),
                    dict(local_datetime='2024-01-01T10:00', policy_id='nope'),
                    dict(calendar_system='lunar_vn', local_datetime='2024-01-01T10:00'),
                    dict(local_datetime='2024-01-01T10:00', longitude=181)):
            with self.assertRaises(ValidationError):
                BirthInput(timezone='Asia/Ho_Chi_Minh', **bad)
        # Leap day exists: 25 days after wu xu (2024-02-04) is gui hai.
        self.assertEqual(pairs(chart(local_datetime='2024-02-29T08:00'))['day'],
                         ganzhi((cycle_index('wu', 'xu') + 25) % 60))

    def test_apparent_solar_time_corrects_once_from_the_instant(self):
        facts = chart(local_datetime='2024-06-15T12:00', longitude=105.85,
                      policy_id='solar-time-v1')
        normal = facts['normalized_time']
        self.assertEqual((normal['longitude_correction_minutes'], normal['eot_minutes']),
                         (3.4, -0.08))
        self.assertEqual(normal['pillar_clock_local'], '2024-06-15T12:03:19')
        self.assertEqual(normal['birth_instant_utc'], '2024-06-15T05:00:00Z')  # unchanged
        for longitude in (-180, 180):                    # the clock runs a day apart, no crash
            far = chart(local_datetime='2024-06-15T12:00', timezone='UTC', longitude=longitude,
                        policy_id='solar-time-v1')
            self.assertIsNotNone(far['pillars']['hour'])

    def test_historical_vietnam_offset_is_flagged(self):
        facts = chart(local_datetime='1965-06-01T10:00')
        self.assertEqual(facts['normalized_time']['utc_offset_seconds'], 8 * 3600)
        self.assertIn('historical_offset', [w['code'] for w in facts['warnings']])
        north = chart(local_datetime='1965-06-01T10:00', timezone='Asia/Bangkok')
        self.assertEqual(north['normalized_time']['utc_offset_seconds'], 7 * 3600)

    def test_same_chart_hash_under_any_host_time_zone(self):
        code = ('import json,sys; from backend.app.calc.chart import compute;'
                ' from backend.app.calc.timebase import BirthInput;'
                ' print(compute(BirthInput(local_datetime="1990-08-17T06:45",'
                ' timezone="Asia/Ho_Chi_Minh", sex_for_luck="male"))["facts_hash"])')
        hashes = set()
        for host in ('UTC', 'Asia/Ho_Chi_Minh', 'America/New_York'):
            out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True,
                                 text=True, env={**os.environ, 'TZ': host}, check=True)
            hashes.add(out.stdout.strip())
        self.assertEqual(len(hashes), 1)


class UncertaintyTests(unittest.TestCase):
    def test_unknown_hour_gives_no_hour_and_never_assumes_noon(self):
        facts = chart(local_datetime='2024-03-20T00:00', time_accuracy='unknown')
        self.assertIsNone(facts['pillars']['hour'])
        self.assertEqual(facts['variants'], [])
        self.assertEqual(pairs(facts)['month'], ('ding', 'mao'))
        self.assertIn('approximate_time', [w['code'] for w in facts['warnings']])

    def test_a_term_inside_the_interval_leaves_the_pillars_open(self):
        facts = chart(local_datetime='2024-02-04T00:00', time_accuracy='unknown')
        self.assertEqual((facts['pillars']['year'], facts['pillars']['month']), (None, None))
        self.assertEqual(pairs(facts)['day'], ('wu', 'xu'))
        first, second = facts['variants']
        self.assertEqual(first['to_utc'], second['from_utc'])
        self.assertEqual(second['from_utc'], '2024-02-04T08:27:07Z')
        self.assertEqual({r['cause'] for r in second['reasons']}, {'li_chun'})
        self.assertEqual(second['pillars']['year'], {'stem': 'jia', 'branch': 'chen'})
        self.assertIsNone(facts['cycles'])                 # month unknown: no luck pillars
        window = chart(local_datetime='2024-02-04T23:00', uncertainty_minutes=30)
        self.assertIsNone(window['pillars']['hour'])
        self.assertEqual([r['cause'] for v in window['variants'] for r in v['reasons']],
                         ['hour_boundary'])
        zi23 = chart(local_datetime='2024-02-04T00:00', time_accuracy='unknown',
                     policy_id='zi23-v1')
        self.assertIsNone(zi23['pillars']['day'])          # the day turns at 23:00
        self.assertIn('day_master_uncertain', [w['code'] for w in zi23['warnings']])


class CycleAndCalendarTests(unittest.TestCase):
    def test_luck_direction_pillars_and_years(self):
        male = chart(local_datetime='2024-02-04T23:30', timezone='Asia/Shanghai',
                     sex_for_luck='male')
        female = chart(local_datetime='2024-02-04T23:30', timezone='Asia/Shanghai',
                       sex_for_luck='female')
        self.assertEqual((male['cycles']['direction'], female['cycles']['direction']),
                         ('forward', 'backward'))            # jia is a yang year
        self.assertEqual([(d['stem'], d['branch']) for d in male['cycles']['da_yun'][:2]],
                         [('ding', 'mao'), ('wu', 'chen')])
        self.assertEqual([(d['stem'], d['branch']) for d in female['cycles']['da_yun'][:2]],
                         [('yi', 'chou'), ('jia', 'zi')])
        years = male['cycles']['liu_nian']
        self.assertEqual((years[0]['solar_term_year'], years[0]['start_instant']),
                         (2024, '2024-02-04T15:30:00Z'))     # the part after the birth
        self.assertTrue(all(a['end_instant'] == b['start_instant'] for a, b in zip(years, years[1:])))
        unspecified = chart(local_datetime='2024-02-04T23:30', timezone='Asia/Shanghai')
        self.assertIsNone(unspecified['cycles']['da_yun'])
        self.assertIn('luck_direction_unknown', [w['code'] for w in unspecified['warnings']])

    def test_lunar_dates_of_both_calendars(self):
        vn = chart(calendar_system='lunar_vn', lunar_date={'year': 1985, 'month': 1, 'day': 1},
                   local_time='08:00')
        cn = chart(calendar_system='lunar_cn', lunar_date={'year': 1985, 'month': 1, 'day': 1},
                   local_time='08:00', timezone='Asia/Shanghai')
        self.assertEqual((vn['normalized_time']['civil_local'][:10],
                          cn['normalized_time']['civil_local'][:10]), ('1985-01-21', '1985-02-20'))
        self.assertEqual(pairs(vn)['year'], ('jia', 'zi'))   # before Lập Xuân: still 1984
        leap = chart(calendar_system='lunar_vn',
                     lunar_date={'year': 2023, 'month': 2, 'day': 1, 'is_leap_month': True},
                     local_time='08:00')
        self.assertEqual(leap['normalized_time']['civil_local'][:10], '2023-03-22')
        for calendar in ('lunar_vn', 'lunar_cn'):
            with self.assertRaises(CalcError) as caught:
                chart(calendar_system=calendar, local_time='08:00',
                      lunar_date={'year': 2024, 'month': 5, 'day': 1, 'is_leap_month': True})
            self.assertEqual(caught.exception.code, 'INVALID_LUNAR_DATE')

    def test_facts_are_plain_json(self):
        facts = chart(local_datetime='1990-08-17T06:45', sex_for_luck='male')
        self.assertEqual(json.loads(json.dumps(facts)), facts)
        self.assertEqual(facts['schema_version'], 'chart-facts/1')
        self.assertEqual(facts['policy_snapshot']['id'], 'standard-v1')


if __name__ == '__main__':
    unittest.main()
