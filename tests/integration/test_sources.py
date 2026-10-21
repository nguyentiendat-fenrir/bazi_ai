"""Soft source links resolved against a published book: by sha256 or title, page hint, anchor."""
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from tests.integration.env import PipelineTestCase

PAGES = [('CHƯƠNG 1: LUẬN THẬP THẦN', 'Thập thần lấy nhật can làm chủ.'),
         ('CHƯƠNG 2: LỤC HỢP', 'Thìn Dậu hợp, Tý Sửu hợp, Dần Hợi hợp.'),
         ('CHƯƠNG 3: CÁCH CỤC', 'Cách cục lấy nguyệt lệnh mà định.'),
         ('CHƯƠNG 4: THƯƠNG QUAN', 'Thương quan kiến quan, vi họa bách đoan.')]


class SourceLinkTests(PipelineTestCase):
    def setUp(self):
        super().setUp()
        if not getattr(type(self), 'version', None):                 # one book for the class
            type(self).version = self.publish_book(PAGES, 'tu_binh')
        self.sha, self.title = self.sql(
            'SELECT o.sha256, b.title FROM book_versions v JOIN objects o ON o.id = v.object_id'
            ' JOIN books b ON b.id = v.book_id WHERE v.id = %s', self.version)[0]
        self.books = {
            'by_sha': {'key': 'by_sha', 'short': 'S', 'title': 'Sách thử', 'kind': 'pdf',
                       'sha256': [self.sha], 'titles': []},
            'by_title': {'key': 'by_title', 'short': 'T', 'title': self.title, 'kind': 'pdf',
                         'sha256': ['0' * 64], 'titles': []},
            'absent': {'key': 'absent', 'short': 'A', 'title': 'Không có ở đây', 'kind': 'pdf',
                       'sha256': ['1' * 64], 'titles': ['Sách vắng']}}
        registry = patch('backend.app.knowledge.sources.registry', return_value=self.books)
        registry.start()
        self.addCleanup(registry.stop)

    def resolve(self, client=None, **query):
        response = (client or self.c).get('/api/v1/sources/resolve', params=query)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['data']

    def test_page_hint_then_neighbours_then_whole_book(self):
        exact = self.resolve(book='by_sha', page=2, q='Thìn Dậu hợp')
        self.assertEqual((exact['matched'], exact['matched_by'], exact['page']), ('exact', 'sha256', 2))
        url = urlsplit(exact['url'])
        span = {k: int(v[0]) for k, v in parse_qs(url.query).items()}
        text = self.sql('SELECT normalized_text FROM page_revisions WHERE id = %s', exact['revision_id'])[0][0]
        self.assertEqual(text[span['from']:span['to']], 'Thìn Dậu hợp')
        self.assertIn('Tý Sửu hợp', exact['excerpt'])

        nearby = self.resolve(book='by_sha', page=1, q='thin dau hop')       # no diacritics
        self.assertEqual((nearby['matched'], nearby['page']), ('nearby', 2))
        far = self.resolve(book='by_sha', page=1, q='Thương quan kiến quan')
        self.assertEqual((far['matched'], far['page']), ('search', 4))
        by_title = self.resolve(book='by_title', page=3, q='nguyệt lệnh')
        self.assertEqual((by_title['matched'], by_title['matched_by']), ('exact', 'title'))

    def test_missing_book_anchor_or_access(self):
        self.assertEqual(self.resolve(book='absent', page=1, q='x')['matched'], 'not_found')
        self.assertEqual(self.resolve(book='nope', page=1, q='x')['reason'], 'unknown book key')
        gone = self.resolve(book='by_sha', page=2, q='Ngọ Mùi hợp')
        self.assertEqual((gone['matched'], gone['reason']), ('not_found', 'anchor not found in this copy'))
        reader, _ = self.client('reader')                                    # no read grant
        self.assertEqual(self.resolve(reader, book='by_sha', page=2, q='Thìn Dậu hợp')['matched'],
                         'not_found')

    def test_open_redirects_to_the_page_viewer(self):
        opened = self.c.get('/api/v1/sources/open', params={'book': 'by_sha', 'page': 2, 'q': 'Thìn Dậu hợp'},
                            follow_redirects=False)
        self.assertEqual(opened.status_code, 302)
        self.assertRegex(opened.headers['location'], r'^/pages/[0-9a-f-]{36}\?from=\d+&to=\d+$')
        missing = self.c.get('/api/v1/sources/open', params={'book': 'absent', 'q': 'x'},
                             follow_redirects=False)
        self.assertEqual(missing.status_code, 404)
