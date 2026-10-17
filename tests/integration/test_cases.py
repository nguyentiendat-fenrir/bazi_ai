"""Case library: charts parsed from book pages, user cases, revisions and review (T023)."""
import unittest
import uuid

from backend.app.knowledge.cases import parse_charts, validate_payload
from tests.fixtures.pdf_factory import PdfBuilder
from tests.integration.env import BLACK, PipelineTestCase


def blocks(*texts, kinds=None):
    return [{'ordinal': i, 'text': t, 'kind': (kinds or {}).get(i, 'paragraph')}
            for i, t in enumerate(texts)]


class ParseTests(unittest.TestCase):
    def test_two_rows_with_ages_and_luck_rows(self):
        charts = parse_charts(blocks('Càn tạo:', 'GIÁP ĐINH CANH ĐINH\nDẦN MÃO TUẤT HỢI\n09 19 29',
                                     'Mậu Kỷ Canh\nThìn Tỵ Ngọ\nNguyên cục: Canh nhật chủ bị khắc.'))
        self.assertEqual(len(charts), 1)
        chart = charts[0]
        self.assertEqual(chart.pillars, [('jia', 'yin'), ('ding', 'mao'), ('geng', 'xu'),
                                         ('ding', 'hai')])
        self.assertEqual((chart.sex_for_luck, chart.luck_start_ages, chart.luck_pillars),
                         ('male', [9, 19, 29], [('wu', 'chen'), ('ji', 'si'), ('geng', 'wu')]))
        self.assertEqual(chart.narrative_lines, ['Nguyên cục: Canh nhật chủ bị khắc.'])

    def test_inline_pairs_and_luck_line(self):
        chart = parse_charts(blocks(
            '1- Khôn tạo mệnh:', 'Tân mão đinh dậu canh ngọ bính tý',
            'Đại vận: bính thân ất mùi quý tỵ nhâm thìn đinh vị'))[0]
        self.assertEqual((chart.sex_for_luck, chart.pillars[0], len(chart.luck_pillars)),
                         ('female', ('xin', 'mao'), 5))
        self.assertEqual(chart.luck_pillars[-1], ('ding', 'wei'))     # "vị" is Mùi

    def test_ten_god_label_row_and_slash_luck(self):
        chart = parse_charts(blocks('Ấn Quan nhật chủ Thực', 'Quý Tân Giáp Bính', 'Mùi Dậu Thân Dần',
                                    'Hành vận: Canh thân / kỷ mùi / mậu ngọ'))[0]
        self.assertEqual((chart.pillars[2], chart.sex_for_luck, len(chart.luck_pillars)),
                         (('jia', 'shen'), None, 3))

    def test_rows_that_are_not_charts(self):
        self.assertEqual(parse_charts(blocks('Giáp Ất Bính Đinh', 'Sửu Dần Mão Thìn')), [])
        self.assertEqual(parse_charts(blocks('Giáp Kỷ hợp hóa thổ', 'Thìn Tuất xung')), [])
        self.assertEqual(parse_charts(blocks('Giáp Ất Bính', 'Tý Sửu Dần')), [])

    def test_payload_rules(self):
        good = {'schema': 'book-case/1', 'pillars': {
            'year': {'stem': 'jia', 'branch': 'zi'}, 'month': {'stem': 'bing', 'branch': 'yin'},
            'day': {'stem': 'wu', 'branch': 'chen'}, 'hour': None}}
        self.assertEqual(validate_payload(good), [])                  # unknown hour is fine
        bad = {**good, 'pillars': {**good['pillars'], 'day': {'stem': 'wu', 'branch': 'mao'}}}
        self.assertIn('not one of the sixty pairs', validate_payload(bad)[0])
        self.assertTrue(validate_payload({**good, 'birth_date': '1990-01-01'}))
        self.assertTrue(validate_payload({'schema': 'x'}))


class CaseLibraryTests(PipelineTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reader, cls.reader_id = cls.client('reader')

    def book(self) -> bytes:
        builder = PdfBuilder()
        builder.page(lines=[('CHƯƠNG 1: ỨNG KỲ', 72, 720, 18, BLACK), ('Càn tạo:', 72, 680, 11, BLACK),
                            ('GIÁP ĐINH CANH ĐINH', 72, 650, 11, BLACK),
                            ('DẦN MÃO TUẤT HỢI', 72, 636, 11, BLACK),
                            ('Hành vận: Mậu thìn / Kỷ tỵ / Canh ngọ', 72, 600, 11, BLACK),
                            ('Nguyên cục: Canh nhật chủ bị quan tinh khắc.', 72, 560, 11, BLACK)])
        builder.page(lines=[('CHƯƠNG 2: MỆNH LỆ', 72, 720, 18, BLACK),
                            ('Khôn tạo mệnh:', 72, 680, 11, BLACK),
                            ('Tân mão đinh dậu canh ngọ bính tý', 72, 650, 11, BLACK),
                            ('Lời bàn: mệnh này thân nhược mà tài vượng.', 72, 610, 11, BLACK)])
        return builder.save(self.tmp / f'{uuid.uuid4().hex}.pdf').read_bytes()

    def review(self, kind, entity_id, decision='approve', base=1):
        return self.c.post('/api/v1/reviews', headers={'Idempotency-Key': uuid.uuid4().hex},
                           json={'entity_kind': kind, 'entity_id': entity_id,
                                 'decision': decision, 'base_revision': base,
                                 'reason': 'đã đối chiếu'})

    def school(self, key):
        return next(s for s in self.c.get('/api/v1/schools').json()['data'] if s['key'] == key)

    def test_book_cases_from_pages(self):
        version, _ = self.ready(data=self.book())
        listed = lambda client: client.get('/api/v1/cases', params={
            'book_version_id': version}).json()['data']
        self.assertEqual(listed(self.c), [])                          # no school yet
        scope = self.c.post(f'/api/v1/book-versions/{version}/school-scopes',
                            json={'school_id': self.school('manh_phai')['id'],
                                  'reason': 'sách Manh phái'}).json()['data']
        job = self.review('school_scope', scope['id']).json()['data']['job_id']
        self.assertEqual(self.run_pipeline(job), 'succeeded')
        found = sorted(listed(self.c), key=lambda c: c['quality']['page'])
        self.assertEqual([(c['origin'], c['state'], c['chart_payload']['sex_for_luck'])
                          for c in found],
                         [('book_case', 'draft', 'male'), ('book_case', 'draft', 'female')])
        first = found[0]['chart_payload']
        self.assertEqual((first['pillars']['day'], len(first['luck_pillars'])),
                         ({'stem': 'geng', 'branch': 'xu'}, 3))
        self.assertIn('Canh nhật chủ', found[0]['narrative'])
        detail = self.c.get(f"/api/v1/cases/{found[0]['id']}").json()['data']
        quotes = ' '.join(s['quote'] for s in detail['sources'])
        self.assertIn('GIÁP ĐINH CANH ĐINH', quotes)
        items = self.c.get('/api/v1/review-items', params={
            'book_version_id': version, 'reason': 'CANDIDATE_CASE'}).json()['data']
        self.assertEqual(len(items), 2)
        self.assertEqual(listed(self.reader), [])                     # drafts are not public

        again = self.c.post(f'/api/v1/book-versions/{version}/process', json={},
                            headers={'Idempotency-Key': uuid.uuid4().hex}).json()['data']
        self.assertEqual(self.run_pipeline(again['id']), 'succeeded')
        self.assertEqual(len(listed(self.c)), 2)                      # no duplicates
        approved = self.review('case_revision', found[0]['revision_id'])
        self.assertEqual(approved.json()['data']['state'], 'approved', approved.text)
        self.assertEqual([c['id'] for c in listed(self.reader)], [found[0]['id']])
        self.assertEqual(self.c.get('/api/v1/review-items', params={
            'book_version_id': version, 'reason': 'CANDIDATE_CASE',
            'state': 'resolved'}).json()['data'][0]['entity_id'], found[0]['revision_id'])

    def test_user_cases_are_private(self):
        tu_binh = self.school('tu_binh')
        payload = {'schema': 'book-case/1', 'sex_for_luck': None, 'luck_pillars': [],
                   'pillars': {'year': {'stem': 'jia', 'branch': 'zi'},
                               'month': {'stem': 'bing', 'branch': 'yin'},
                               'day': {'stem': 'wu', 'branch': 'chen'}, 'hour': None}}
        mine = self.reader.post('/api/v1/cases', json={
            'origin': 'user_case', 'school_id': tu_binh['id'], 'chart_payload': payload,
            'narrative': 'Lá số người quen, chưa rõ giờ sinh.'})
        self.assertEqual(mine.status_code, 201, mine.text)
        case = mine.json()['data']
        self.assertEqual((case['visibility'], case['owner_id']), ('private', self.reader_id))
        other, _ = self.client('reader')
        self.assertEqual(other.get(f"/api/v1/cases/{case['id']}").status_code, 404)
        self.assertEqual(self.c.get(f"/api/v1/cases/{case['id']}").status_code, 404)
        self.assertEqual(self.reader.post('/api/v1/cases', json={
            'origin': 'book_case', 'school_id': tu_binh['id'], 'chart_payload': payload,
            'evidence_ids': []}).status_code, 403)
        wrong = dict(payload, pillars={**payload['pillars'], 'day': {'stem': 'wu', 'branch': 'mao'}})
        self.assertEqual(self.reader.post('/api/v1/cases', json={
            'origin': 'user_case', 'school_id': tu_binh['id'],
            'chart_payload': wrong}).status_code, 422)
        url = f"/api/v1/cases/{case['id']}/revisions"
        revised = self.reader.post(url, json={'base_revision': 1, 'reason': 'thêm giờ sinh',
                                              'chart_payload': dict(payload, pillars={
                                                  **payload['pillars'],
                                                  'hour': {'stem': 'jia', 'branch': 'yin'}})})
        self.assertEqual((revised.status_code, revised.json()['data']['revision']), (201, 2))
        self.assertEqual(self.reader.post(url, json={'base_revision': 1, 'reason': 'lặp lại'})
                         .status_code, 412)
        self.assertEqual(other.delete(f"/api/v1/cases/{case['id']}").status_code, 404)
        self.assertEqual(self.reader.delete(f"/api/v1/cases/{case['id']}").status_code, 204)
        self.assertEqual(self.reader.get(f"/api/v1/cases/{case['id']}").status_code, 404)


if __name__ == '__main__':
    unittest.main()
