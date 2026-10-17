"""Candidate extraction: draft assertions with exact evidence, scoped by reviewed school (T021)."""
import unittest
import uuid

from backend.app.knowledge.candidates import propose, sentences
from tests.fixtures.pdf_factory import PdfBuilder
from tests.integration.env import BLACK, PipelineTestCase

RULE = 'Nếu thân vượng gặp Tài thì giàu, Quan tinh hữu dụng thì quý.'
DEFINITION = 'Thìn là dư khí của mộc, Mùi là dư khí của hỏa.'
PILLARS = 'Giáp Tý gặp Canh Ngọ thì xung khắc, chủ về hung tai nặng.'
PLAIN = 'Ngày hôm nay trời đẹp, mọi người đi chơi vui vẻ cả ngày.'


class ProposeTests(unittest.TestCase):
    def test_rules_and_definitions(self):
        self.assertEqual([c.kind for c in propose(RULE)], ['rule'])
        self.assertEqual([c.kind for c in propose(DEFINITION)], ['definition'])
        self.assertEqual([c.kind for c in propose('Ất mộc là hoa cỏ mềm mại trong vườn.')],
                         ['definition'])

    def test_chart_specific_and_plain_text_are_left_out(self):
        for sentence in (PILLARS, PLAIN, 'Năm 2003 gặp Quý Mùi thì ứng kỳ, tất phát tài lớn.',
                         'Đây là mệnh phú quý, Thìn là dụng thần chính.',
                         'Khi trời mưa thì ắt đất ướt, ai cũng thấy vậy.'):
            with self.subTest(sentence=sentence):
                self.assertEqual(propose(sentence), [])

    def test_sentence_spans_are_exact(self):
        block = f'  {RULE}\n{DEFINITION}  '
        spans = sentences(block)
        self.assertEqual([block[s:e] for s, e in spans], [RULE, DEFINITION])


class CandidateStageTests(PipelineTestCase):
    def book(self) -> bytes:
        builder = PdfBuilder()
        for n, (title, lines) in enumerate((('CHƯƠNG 1: THÂN VƯỢNG', [RULE, PLAIN]),
                                            ('CHƯƠNG 2: TƯỢNG', [DEFINITION, PILLARS]))):
            builder.page(lines=[(title, 72, 720, 18, BLACK)] +
                         [(line, 72, 680 - 40 * i, 11, BLACK) for i, line in enumerate(lines)])
        return builder.save(self.tmp / f'{uuid.uuid4().hex}.pdf').read_bytes()

    def candidates(self, version):
        return self.sql('SELECT a.id::text, a.statement, a.state, s.key, a.origin FROM assertions a'
                        ' JOIN schools s ON s.id = a.school_id WHERE EXISTS (SELECT 1 FROM'
                        ' assertion_sources x JOIN evidence_spans e ON e.id = x.evidence_id'
                        ' WHERE x.assertion_id = a.id AND e.book_version_id = %s)'
                        ' ORDER BY a.statement', version)

    def review(self, kind, entity_id, decision='approve'):
        return self.c.post('/api/v1/reviews', headers={'Idempotency-Key': uuid.uuid4().hex},
                           json={'entity_kind': kind, 'entity_id': entity_id,
                                 'decision': decision, 'base_revision': 1,
                                 'reason': 'đã đối chiếu'})

    def test_candidates_need_a_reviewed_school_and_never_duplicate(self):
        version, gen = self.ready(data=self.book())
        self.assertEqual(self.candidates(version), [])          # no school assigned yet
        manh = next(s for s in self.c.get('/api/v1/schools').json()['data']
                    if s['key'] == 'manh_phai')
        scope = self.c.post(f'/api/v1/book-versions/{version}/school-scopes',
                            json={'school_id': manh['id'], 'reason': 'sách Manh phái'})
        rebuild = self.review('school_scope', scope.json()['data']['id']).json()['data']
        self.assertEqual(self.run_pipeline(rebuild['job_id']), 'succeeded')

        found = self.candidates(version)
        self.assertEqual([row[1] for row in found], sorted([DEFINITION, RULE]))
        self.assertEqual({(row[2], row[3], row[4]) for row in found},
                         {('draft', 'manh_phai', 'source_explicit')})   # never approved by a job
        definition = next(row[0] for row in found if row[1] == DEFINITION)
        detail = self.c.get(f'/api/v1/assertions/{definition}').json()['data']
        source = detail['sources'][0]
        self.assertEqual((source['quote'], source['physical_page_number'], source['relation']),
                         (DEFINITION, 2, 'states'))
        items = self.c.get('/api/v1/review-items', params={
            'book_version_id': version, 'reason': 'CANDIDATE_ASSERTION'}).json()['data']
        self.assertEqual(sorted(i['resolution']['kind'] for i in items), ['definition', 'rule'])
        listed = self.c.get('/api/v1/assertions', params={'book_version_id': version}).json()
        self.assertEqual(len(listed['data']), 2)
        reader, _ = self.client('reader')
        self.assertEqual(reader.get('/api/v1/assertions',
                                    params={'book_version_id': version}).json()['data'], [])
        self.assertEqual(reader.get(f'/api/v1/assertions/{definition}').status_code, 404)

        # A full rebuild proposes nothing new; a corrected page adds only its new sentence.
        again = self.c.post(f'/api/v1/book-versions/{version}/process', json={},
                            headers={'Idempotency-Key': uuid.uuid4().hex}).json()['data']
        self.assertEqual(self.run_pipeline(again['id']), 'succeeded')
        self.assertEqual(len(self.candidates(version)), 2)
        page = next(p for p in self.c.get(f'/api/v1/book-versions/{version}/pages')
                    .json()['data'] if p['physical_page_number'] == 1)
        blocks = self.c.get(f"/api/v1/page-revisions/{page['revision_id']}").json()['data']
        plain = next(b for b in blocks['blocks'] if b['text'] == PLAIN)
        added = 'Khí là gốc của thân, gặp Ấn sinh thì mạnh mẽ, có Tài thì giàu có lâu dài.'
        fix = self.c.post(f"/api/v1/pages/{page['page_id']}/corrections",
                          headers={'If-Match': f'"{page["revision_id"]}"',
                                   'Idempotency-Key': uuid.uuid4().hex},
                          json={'base_revision_id': page['revision_id'], 'reason': 'bổ sung câu',
                                'changes': [{'ordinal': plain['ordinal'], 'text': added}]})
        self.assertEqual(fix.status_code, 201, fix.text)
        self.assertEqual(self.run_pipeline(fix.json()['data']['job_id']), 'succeeded')
        statements = [row[1] for row in self.candidates(version)]
        self.assertEqual(len(statements), 3)
        self.assertIn(added, statements)


if __name__ == '__main__':
    unittest.main()
