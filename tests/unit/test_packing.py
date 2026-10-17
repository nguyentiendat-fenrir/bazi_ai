"""Context packing: adjacency merge without duplicated overlap, caps, whole chunks (T036)."""
import unittest

from backend.app.retrieval.packing import pack


def span(block, start, end, chunk_start, page=1):
    return {'page_revision_id': 'r1', 'block_id': block, 'start_offset': start, 'end_offset': end,
            'chunk_start': chunk_start, 'chunk_end': chunk_start + (end - start),
            'physical_page_number': page, 'printed_page_label': str(page)}


def hit(chunk, ordinal, text, spans, section='0001', book='v1', score=1.0, kind='text'):
    return {'chunk_id': chunk, 'ordinal': ordinal, 'text': text, 'spans': spans,
            'generation_id': 'g1', 'section_path': section, 'section_title': f'S {section}',
            'speaker_layer': 'unknown', 'book_version_id': book, 'book_id': f'b-{book}',
            'book_title': 'Sách', 'edition_label': 'v1', 'school_key': 'manh_phai',
            'kind': kind, 'score': score}


class PackTests(unittest.TestCase):
    def test_adjacent_chunks_merge_and_overlap_appears_once(self):
        first = hit('c5', 5, 'Đoạn một.\n\nĐoạn hai.', [span('b1', 0, 9, 0), span('b2', 11, 20, 11)])
        second = hit('c6', 6, 'Đoạn hai.\n\nĐoạn ba.', [span('b2', 11, 20, 0),
                                                       span('b3', 22, 30, 11)], score=0.9)
        bundle = pack([first, second])
        self.assertEqual(len(bundle['groups']), 1)
        group = bundle['groups'][0]
        self.assertEqual((group['evidence_id'], group['chunk_ids'], group['merged']),
                         ('E1', ['c5', 'c6'], True))
        self.assertEqual(group['excerpt'], 'Đoạn một.\n\nĐoạn hai.\n\nĐoạn ba.')
        self.assertEqual(len(group['spans']), 3)

    def test_caps_keep_chunks_whole(self):
        hits = [hit(f'c{i}', i * 10, f'Văn bản {i}.', [span(f'b{i}', i * 20, i * 20 + 11, 0)],
                    section=f'{i:04d}') for i in range(5)]
        capped = pack(hits)
        self.assertEqual((len(capped['groups']), capped['omitted'], capped['truncated']),
                         (3, 2, True))                          # three per book by default
        self.assertEqual(len(pack(hits, book_filtered=True)['groups']), 5)
        self.assertEqual(len(pack(hits, max_groups=2, book_filtered=True)['groups']), 2)
        tight = pack(hits, max_tokens=3, book_filtered=True)
        self.assertEqual(tight['groups'], [])                   # never a cut chunk
        self.assertTrue(tight['truncated'])
        table = hit('t', 1, 'Giáp Ất\nTý Sửu', [span('bt', 0, 14, 0)], kind='table')
        self.assertEqual(pack([table])['groups'][0]['excerpt'], 'Giáp Ất\nTý Sửu')


if __name__ == '__main__':
    unittest.main()
