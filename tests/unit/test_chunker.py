"""Chunk planning rules (T015) on synthetic block sequences."""
import unittest

from backend.app.ingestion.chunker import DEFAULTS, SEPARATOR, count_tokens, plan_chunks


def block(i, text, section='0001', speaker='unknown', kind='paragraph', chart=False):
    return {'id': f'b{i}', 'text': text, 'kind': kind, 'revision_id': f'r{i // 10}',
            'start': 0, 'end': len(text), 'bbox': None, 'speaker': speaker, 'chart_row': chart,
            'review': False, 'section_path': section}


def words(n, seed='chữ'):
    return ' '.join(f'{seed}{i}.' if i % 12 == 11 else f'{seed}{i}' for i in range(n))


class PlanTests(unittest.TestCase):
    def plan(self, blocks, **config):
        return plan_chunks(blocks, {**DEFAULTS, **config})

    def test_speakers_and_sections_never_mix(self):
        blocks = [block(0, 'Nguyên văn: a', speaker='original_author'),
                  block(1, 'Từ chú: b', speaker='commentator'),
                  block(2, 'tiếp c', speaker='commentator'),
                  block(3, 'mục mới', section='0002', speaker='commentator')]
        chunks = self.plan(blocks)
        self.assertEqual([(c.section_path, c.speaker, [p.block['id'] for p in c.pieces])
                          for c in chunks],
                         [('0001', 'original_author', ['b0']), ('0001', 'commentator', ['b1', 'b2']),
                          ('0002', 'commentator', ['b3'])])

    def test_pillar_table_is_one_chunk_and_case_window_bounded(self):
        blocks = [block(0, 'Thí dụ 7)', kind='heading'),
                  block(1, 'Thực Thương nhật chủ t.Tài', chart=True),
                  block(2, 'Mậu Kỷ Bính Canh', chart=True), block(3, 'Tuất Mùi Tý Dần', chart=True),
                  block(4, 'Bính hỏa sanh tháng 6, lửa còn chút sáng.'),
                  block(5, '(Nhị) bệnh dược', kind='heading'),
                  block(6, 'Đoạn lý luận thường.')]
        chunks = self.plan(blocks)
        self.assertEqual([c.kind for c in chunks], ['case', 'text'])
        self.assertEqual([p.block['id'] for p in chunks[0].pieces], ['b1', 'b2', 'b3', 'b4'])
        self.assertNotIn('Thí dụ 7)', chunks[0].text)          # titles stay in sections

    def test_table_outside_case_stays_whole(self):
        blocks = [block(0, 'Đoạn trước bảng.'), block(1, 'Giáp Ất Bính Đinh', chart=True),
                  block(2, 'Tý Sửu Dần Mão', chart=True), block(3, 'Đoạn sau bảng.')]
        kinds = [(c.kind, [p.block['id'] for p in c.pieces]) for c in self.plan(blocks)]
        self.assertIn(('table', ['b1', 'b2']), kinds)

    def test_long_block_split_at_sentences_within_max(self):
        long_text = words(1500)
        chunks = self.plan([block(0, long_text)], target=200, max=300, overlap=0)
        self.assertGreater(len(chunks), 3)
        for chunk in chunks:
            self.assertLessEqual(chunk.tokens, 300)
            for piece in chunk.pieces:
                self.assertEqual(long_text[piece.start:piece.end], piece.text)
                self.assertTrue(piece.text.endswith('.') or piece.end == len(long_text))

    def test_overlap_carries_trailing_pieces(self):
        blocks = [block(i, words(60, f'p{i}x')) for i in range(6)]
        chunks = self.plan(blocks, target=150, max=300, overlap=80)
        self.assertGreater(len(chunks), 1)
        for prev, nxt in zip(chunks, chunks[1:]):
            self.assertEqual(prev.pieces[-1].block['id'], nxt.pieces[0].block['id'])

    def test_a_sentence_split_over_two_blocks_is_never_cut(self):
        # The PDF ended the block mid-sentence (page turn, symbol); the next block goes on.
        first = words(55, 'a') + ' và câu này còn tiếp'
        blocks = [block(0, words(70, 'z')), block(1, first), block(2, 'sang trang sau mới hết câu.'),
                  block(3, words(70, 'y'))]
        chunks = self.plan(blocks, target=100, max=300, overlap=0)
        holders = [[p.block['id'] for p in c.pieces] for c in chunks]
        together = [ids for ids in holders if 'b1' in ids]
        self.assertTrue(together and all('b2' in ids for ids in together), holders)

    def test_overlap_never_starts_with_the_end_of_a_sentence(self):
        blocks = [block(0, words(70, 'm')), block(1, words(20, 'n') + ' còn tiếp'),
                  block(2, 'phần cuối của câu.'), block(3, words(90, 'o'))]
        chunks = self.plan(blocks, target=110, max=300, overlap=60)
        for chunk in chunks[1:]:
            self.assertNotEqual(chunk.pieces[0].block['id'], 'b2')

    def test_an_oversized_sentence_run_is_cut_after_a_sentence_end(self):
        blocks = [block(0, words(100, 'q') + ' mở'), block(1, 'tiếp theo ' + words(100, 'r')),
                  block(2, 'nữa ' + words(100, 's') + ' kết thúc.'), block(3, 'cuối ' + words(30, 't'))]
        chunks = self.plan(blocks, target=150, max=250, overlap=0)
        for chunk in chunks[:-1]:
            self.assertLessEqual(chunk.tokens, 250)

    def test_chunk_text_is_pieces_joined(self):
        blocks = [block(i, f'Đoạn {i} có nội dung.') for i in range(3)]
        chunk = self.plan(blocks)[0]
        self.assertEqual(chunk.text, SEPARATOR.join(p.text for p in chunk.pieces))
        self.assertEqual(count_tokens('Khách–Chủ, Thể dụng.'), 7)


if __name__ == '__main__':
    unittest.main()
