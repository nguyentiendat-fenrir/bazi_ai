"""Soft source links: anchor matching, link shape, and the glossary's sources against books.json."""
import unittest
from urllib.parse import parse_qs, urlsplit

from backend.app.knowledge.glossary import read
from backend.app.knowledge.sources import find, fold_keep, registry, soft_link, unresolved


class AnchorTests(unittest.TestCase):
    def test_fold_keeps_offsets(self):
        for s in ('Thìn Dậu hợp', 'ĐINH HỎA', 'Thủy cục — Thân Tý Thìn'):
            self.assertEqual(len(fold_keep(s)), len(s))
        self.assertEqual(fold_keep('Đinh Hỏa'), 'dinh hoa')

    def test_find_case_spacing_then_diacritics(self):
        page = 'Chương 2.\nThìn  Dậu\nhợp, Tý Sửu hợp.'
        start, end = find(page, 'thìn dậu hợp')
        self.assertEqual(page[start:end], 'Thìn  Dậu\nhợp')
        start, end = find(page, 'ty suu hop')
        self.assertEqual(page[start:end], 'Tý Sửu hợp')
        self.assertIsNone(find(page, 'Ngọ Mùi hợp'))
        self.assertIsNone(find(page, '   '))

    def test_find_offsets_index_decomposed_text(self):
        import unicodedata
        page = unicodedata.normalize('NFD', 'thuộc địa phận, Thìn Dậu hợp -ND')
        for needle in ('thìn dậu hợp', 'Thin Dau hop', '-ND'):
            start, end = find(page, needle)
            self.assertEqual(fold_keep(unicodedata.normalize('NFC', page[start:end])),
                             fold_keep(needle), needle)

    def test_soft_link_names_no_machine_ids(self):
        link = soft_link({'book': 'tu_binh_chan_thuyen', 'page': 12, 'anchor': 'Thương quan'})
        url = urlsplit(link)
        self.assertEqual(url.path, '/api/v1/sources/open')
        self.assertEqual(parse_qs(url.query), {'book': ['tu_binh_chan_thuyen'], 'q': ['Thương quan'],
                                               'page': ['12']})
        out = unresolved({'book': 'tu_binh_chan_thuyen', 'page': 12, 'anchor': 'Thương quan'})
        self.assertEqual((out['short'], out['page_hint'], out['matched']), ('TBCT', 12, 'not_found'))


class GlossarySourceTests(unittest.TestCase):
    def test_every_source_is_a_soft_link_inside_its_book(self):
        books = registry()
        for concept in read()['concepts']:
            self.assertLessEqual(len(concept['sources']), 6, concept['key'])
            for src in concept['sources']:
                book = books[src['book']]
                self.assertTrue(src['anchor'].strip(), concept['key'])
                self.assertIn(src['verified'], ('exact', 'nearby'))
                if book['kind'] == 'pdf':
                    self.assertTrue(1 <= src['page'] <= book['pages'], (concept['key'], src))
                else:
                    self.assertTrue(1 <= src['para'] <= book['paragraphs'], (concept['key'], src))


if __name__ == '__main__':
    unittest.main()
