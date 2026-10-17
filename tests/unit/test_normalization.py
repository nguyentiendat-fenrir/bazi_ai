"""Text normalisation, offset maps and layout heuristics (T014)."""
import unicodedata
import unittest

from backend.app.ingestion import layout
from backend.app.ingestion.normalize import from_utf16, normalize, to_utf16, unmapped_glyph_rate
from backend.app.ingestion.quality import calibrate, pillar_mismatch


class NormalizeTests(unittest.TestCase):
    def test_noise_removed_meaning_kept(self):
        raw = 'Khách Chủ​ luận­điểm 甲乙﻿'
        text, index = normalize(raw)
        self.assertEqual(text, 'Khách Chủ luậnđiểm 甲乙')
        self.assertEqual(len(index), len(text))
        for i, ch in enumerate(text):   # every output char points at its raw origin
            origin = raw[index[i]]
            self.assertTrue(origin == ch or origin == ' ' and ch == ' ')

    def test_decomposed_vietnamese_composes_with_map(self):
        decomposed = unicodedata.normalize('NFD', 'Thể Dụng')
        text, index = normalize(decomposed)
        self.assertEqual(text, 'Thể Dụng')
        self.assertEqual(text, unicodedata.normalize('NFC', text))
        self.assertEqual(decomposed[index[2]], 'e')        # ể maps to its base letter
        self.assertEqual(index, sorted(index))             # monotonic

    def test_utf16_roundtrip_with_astral_characters(self):
        text = 'Can 𠀀 Chi 𩸽 Giáp'
        for offset in range(len(text) + 1):
            units = to_utf16(text, offset)
            self.assertEqual(units, len(text[:offset].encode('utf-16-le')) // 2)
            self.assertEqual(from_utf16(text, units), offset)

    def test_unmapped_glyph_rate(self):
        self.assertEqual(unmapped_glyph_rate('Giáp Ất'), 0.0)
        self.assertAlmostEqual(unmapped_glyph_rate('Gip'), 0.4)  # 2 of 5 letters


class LayoutTests(unittest.TestCase):
    def test_headings(self):
        cases = {'CHƯƠNG 1: ỨNG KỲ': (1, 'chapter'), 'II. Các khái niệm đặc thù': (1, 'roman'),
                 '1. Khái niệm khách - chủ': (2, 'decimal1'), '1.2 Tượng Ất mộc': (3, 'decimal2'),
                 'BA PHƯƠNG THỨC ỨNG KỲ': (1, 'uppercase'),
                 # Chapter titles named with chart words are still titles (Tử Bình p.84).
                 'Chương 31: Luận Chính Quan': (1, 'chapter'),
                 'Chương 21 - Quan Sát': (1, 'chapter'), 'CHƯƠNG 3: ĐẠI VẬN': (1, 'chapter')}
        for text_, expected in cases.items():
            with self.subTest(text=text_):
                self.assertEqual(layout.heading(text_, 12, 400, 12, 1), expected)
        self.assertIsNone(layout.heading('Mậu Kỷ Bính Canh', 9, 400, 7.6, 1))      # chart row
        self.assertIsNone(layout.heading('Thực Thương nhật chủ t.Tài', 9, 700, 7.6, 1))
        self.assertFalse(layout.is_chart_row('Chương 39: Luận Thiên Quan'))
        self.assertIsNone(layout.heading('1. Thất chính Tứ dư là hệ thống chiêm tinh dùng'
                                         ' bảy chính tinh và bốn dư tinh để luận đoán vận'
                                         ' mệnh con người theo phép xưa.', 7.6, 400, 7.6, 3))
        self.assertEqual(layout.heading('Lời tự của Phương Trọng Thẩm', 7.6, 700, 7.6, 1),
                         (2, 'bold'))
        self.assertIsNone(layout.heading('Mục lục .......... 12', 12, 700, 12, 1))

    def test_speaker_markers(self):
        self.assertEqual(layout.speaker_marker('Nguyên văn: Bát tự dụng thần'),
                         ('original_author', 'nguyên văn'))
        self.assertEqual(layout.speaker_marker('Từ chú: lấy Tài làm dụng'),
                         ('commentator', 'từ chú'))
        self.assertEqual(layout.speaker_marker('Bình chú của tác giả: Không phải lúc nào'),
                         ('commentator', 'bình chú của tác giả'))
        self.assertEqual(layout.speaker_marker('Khách và Chủ'), (None, None))

    def test_running_headers_and_toc(self):
        pages = [[f'Lưu Bá Ôn – Nhậm Thiết Tiều Tuvilyso.org Page {n}', 'thân bài', '...',
                  'nội dung', 'kết', 'Trích Thiên Tủy'] for n in range(1, 11)]
        patterns = layout.repeated_patterns(pages)
        self.assertIn('lưu bá ôn – nhậm thiết tiều tuvilyso.org page #', patterns)
        self.assertIn('trích thiên tủy', patterns)
        self.assertTrue(layout.is_toc_page(['I. Cách xem........6', '1. Khách chủ.....7',
                                            '2. Công thần......8']))
        self.assertTrue(layout.FOLIO.match('28') and layout.FOLIO.match('xii'))


class QualitySignalTests(unittest.TestCase):
    def test_pillar_mismatch(self):
        self.assertTrue(pillar_mismatch('Mậu Kỷ Bính Canh\nNgọ Mùi Dần'))
        self.assertFalse(pillar_mismatch('Mậu Kỷ Bính Canh\nNgọ Mùi Dần Thân'))
        self.assertFalse(pillar_mismatch('Mậu là dương thổ\nNgọ là hỏa'))

    def test_calibration_report(self):
        predicted = {'p1': {'READING_ORDER'}, 'p2': {'READING_ORDER'}, 'p3': set()}
        labelled = {'p1': {'READING_ORDER'}, 'p2': set(), 'p3': {'READING_ORDER'}}
        report = calibrate(predicted, labelled)['READING_ORDER']
        self.assertEqual((report['tp'], report['fp'], report['fn']), (1, 1, 1))
        self.assertEqual((report['precision'], report['recall']), (0.5, 0.5))


if __name__ == '__main__':
    unittest.main()
