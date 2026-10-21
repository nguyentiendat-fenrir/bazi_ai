"""Facts of a written chart: parsing, the reviewed tables, relations with the luck pillars."""
import unittest

from backend.app.calc.pillar_facts import Chart, facts, find_chart, render

Q13 = ('Lá số nam: Mậu Ngọ – Ất Mão – Nhâm Tý – Canh Tý. Đại vận: Bính Thìn – Đinh Tỵ – Mậu Ngọ'
       ' – Kỷ Mùi – Canh Thân – Tân Dậu – Nhâm Tuất (vào vận Mùi năm 41 tuổi). Theo Tử Bình Chân'
       ' Thuyên, lá số này lấy gì làm dụng thần? Vì sao vận Ngọ tốt mà vận Mùi xấu, dù Kỷ Mùi là'
       ' Thổ trợ Sát?')
ONASSIS = ('Lá số Onassis, nam: Ất Tỵ – Kỷ Sửu – Kỷ Mùi – Canh Ngọ. Đại vận: Mậu Tý (3) – Đinh Hợi'
           ' (13) – Bính Tuất (23) – Ất Dậu (33) – Giáp Thân (43) – Quý Mùi (53) – Nhâm Ngọ (63).')
Q18 = ('Lá số nam: Đinh Sửu – Kỷ Dậu – Ất Sửu – Giáp Thân. Đại vận: Mậu Thân (2001) – Đinh Mùi'
       ' (2011) – Bính Ngọ (2021) – Ất Tỵ (2031) – Giáp Thìn (2041) – Quý Mão (2051).')


def chart(*pairs, luck=(), sex='male'):
    return Chart(dict(zip(('year', 'month', 'day', 'hour'), pairs)), list(luck), sex)


class ParseTests(unittest.TestCase):
    def test_pillars_luck_and_sex_come_out_of_the_question(self):
        c = find_chart(Q13)
        self.assertEqual(c.pillars, {'year': ('wu', 'wu'), 'month': ('yi', 'mao'),
                                     'day': ('ren', 'zi'), 'hour': ('geng', 'zi')})
        self.assertEqual(c.sex, 'male')
        # "Kỷ Mùi là Thổ trợ Sát" later in the question is not an eighth luck pillar
        self.assertEqual([b for _, b in c.luck], ['chen', 'si', 'wu', 'wei', 'shen', 'you', 'xu'])
        self.assertEqual(len(find_chart(ONASSIS).luck), 7)        # ages between the pillars
        self.assertEqual(len(find_chart(Q18).luck), 6)            # years between the pillars

    def test_ty_and_ti_spellings(self):
        c = find_chart('Khôn tạo: Quý Tị – Ất Mão – Kỷ Hợi – Giáp Tý')
        self.assertEqual((c.pillars['year'], c.pillars['hour'], c.sex),
                         (('gui', 'si'), ('jia', 'zi'), 'female'))
        self.assertIsNone(find_chart('Tử Bình Chân Thuyên nói gì về dụng thần?'))


class FactTests(unittest.TestCase):
    def test_day_master_month_command_and_hidden_stem_order(self):
        f = facts(find_chart(Q18))
        self.assertEqual((f['day_master']['stem'], f['month_command']['branch'],
                          f['month_command']['main_qi_ten_god']), ('yi', 'you', 'seven_killings'))
        chou = f['pillars'][0]['hidden']
        self.assertEqual([(h['stem'], h['rank']) for h in chou],
                         [('ji', 'chủ khí'), ('gui', 'trung khí'), ('xin', 'dư khí')])

    def test_lu_blade_and_horse(self):
        onassis = facts(find_chart(ONASSIS))
        self.assertEqual(onassis['lu'], {'branch': 'wu', 'positions': ['hour']})  # Kỷ lộc tại Ngọ
        self.assertEqual(onassis['blade'], {'branch': None, 'positions': []})     # can âm
        self.assertEqual(onassis['horse']['day'], {'branch': 'si', 'positions': ['year']})
        q13 = facts(find_chart(Q13))
        self.assertEqual(q13['blade'], {'branch': 'zi', 'positions': ['day', 'hour']})
        self.assertEqual(q13['lu']['positions'], [])
        clashes = [r for r in q13['relations'] if r['type'] == 'Lục xung']
        self.assertEqual([r['positions'] for r in clashes], [['year', 'day'], ['year', 'hour']])

    def test_a_frame_completed_by_the_luck_pillar_says_so(self):
        f = facts(find_chart(Q18))
        self.assertIn('Bán hợp Kim (thiếu Tỵ)', [r['type'] for r in f['relations']])
        at_ty = f['luck'][3]
        self.assertEqual((at_ty['stem'], at_ty['branch']), ('yi', 'si'))
        self.assertIn('Tam hợp Kim cục (đủ ba chi), đủ nhờ vận', [r['type'] for r in at_ty['relations']])
        onassis = facts(find_chart(ONASSIS))
        quy_mui = onassis['luck'][5]['relations']
        self.assertIn('Tam hội Hỏa cục (đủ ba chi), đã đủ trong tứ trụ', [r['type'] for r in quy_mui])

    def test_self_combination_dark_combination_and_branch_controls_stem(self):
        f = facts(chart(('gui', 'si'), ('wu', 'wu'), ('bing', 'xu'), ('jia', 'yin')))
        self.assertEqual(f['pillars'][0]['self'], ['Tự hợp', 'Chi hợp khắc can'])
        self.assertEqual(f['pillars'][2]['self'], [])                 # Bính Tuất needs Mùi
        with_wei = facts(chart(('gui', 'wei'), ('jia', 'yin'), ('bing', 'xu'), ('gui', 'si')))
        self.assertEqual(with_wei['pillars'][2]['self'], ['Tự hợp (Tuất gặp Mùi hình)'])
        dark = facts(chart(('jia', 'yin'), ('ding', 'chou'), ('wu', 'wu'), ('gui', 'hai')))
        self.assertEqual(sorted(r['members'] for r in dark['relations'] if r['type'] == 'Ám hợp'),
                         [['wu', 'hai'], ['yin', 'chou']])

    def test_warnings_for_charts_that_cannot_exist(self):
        bad_month = facts(chart(('wu', 'wu'), ('jia', 'mao'), ('ren', 'zi'), ('geng', 'zi')))
        self.assertTrue(any('Ngũ Hổ độn' in w for w in bad_month['warnings']))
        bad_hour = facts(chart(('wu', 'wu'), ('yi', 'mao'), ('ren', 'zi'), ('jia', 'zi')))
        self.assertTrue(any('Ngũ Thử độn' in w for w in bad_hour['warnings']))
        reversed_luck = facts(chart(('wu', 'wu'), ('yi', 'mao'), ('ren', 'zi'), ('geng', 'zi'),
                                    luck=[('bing', 'chen'), ('ding', 'si')], sex='female'))
        self.assertTrue(any('nghịch' in w for w in reversed_luck['warnings']))
        self.assertEqual(facts(find_chart(Q13))['warnings'], [])

    def test_render_is_labelled_and_never_claims_a_transformation(self):
        text = render(facts(find_chart(Q13)))
        self.assertTrue(text.startswith('DỮ KIỆN LÁ SỐ — tính bằng bảng tra, không phải trích sách'))
        self.assertIn('B1 Nhật chủ: Nhâm (Dương Thủy)', text)
        self.assertIn('Kình Dương: Tý — ngày, giờ', text)
        self.assertEqual(text.count('hóa'), 1)                     # only "không xét hóa"
        self.assertEqual(text.count('Đại vận '), 7)


if __name__ == '__main__':
    unittest.main()
