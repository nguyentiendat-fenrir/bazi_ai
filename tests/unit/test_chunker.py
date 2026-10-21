"""Structure-first parent/child chunking (chunker-3) on synthetic block sequences."""
import unittest

from backend.app.ingestion.chunker import (DEFAULTS, SEPARATOR, breadcrumb, _tree, plan_children,
                                           plan_parents, plan_units)
from backend.app.ingestion.tokens import count_tokens


def block(i, text, section='0001', speaker='unknown', kind='paragraph', chart=False):
    return {'id': f'b{i}', 'text': text, 'kind': kind, 'revision_id': f'r{i // 10}',
            'start': 0, 'end': len(text), 'bbox': None, 'speaker': speaker, 'chart_row': chart,
            'review': False, 'section_path': section, 'page': 1 + i // 10}


def words(n, seed='chữ'):
    return ' '.join(f'{seed}{i}.' if i % 12 == 11 else f'{seed}{i}' for i in range(n))


def sections(*specs):
    """(path, title, level) → SectionSpec dicts with parent paths from the dotted path."""
    out = []
    for path, title, level in specs:
        parent = path.rsplit('.', 1)[0] if '.' in path else None
        out.append({'path': path, 'parent_path': parent, 'title': title, 'ordinal': 1,
                    'level': level, 'heading_block_id': None})
    return out


class UnitTests(unittest.TestCase):
    def units(self, blocks, **config):
        return plan_units(blocks, {**DEFAULTS, **config})

    def test_sentence_split_over_two_blocks_is_one_paragraph(self):
        units = self.units([block(0, 'Nguyệt lệnh là gốc của cách cục, nên khi'),
                            block(1, 'xét dụng thần phải xem nguyệt lệnh trước.'),
                            block(2, 'Đoạn khác.')])
        self.assertEqual([[p.block['id'] for p in u.pieces] for u in units], [['b0', 'b1'], ['b2']])

    def test_list_with_intro_line_is_one_unit(self):
        units = self.units([block(0, 'Có ba phép chọn dụng thần:'), block(1, '1. Phù ức'),
                            block(2, '2. Điều hậu'), block(3, '3. Thông quan'),
                            block(4, 'Sau đây bàn từng phép.')])
        self.assertEqual([(u.kind, len(u.pieces)) for u in units], [('list', 4), ('paragraph', 1)])

    def test_example_keeps_its_chart_and_discussion(self):
        units = self.units([block(0, 'Ví dụ 3: Càn tạo'), block(1, 'Mậu Ất Nhâm Canh', chart=True),
                            block(2, 'Ngọ Mão Tý Tý', chart=True),
                            block(3, 'Nhâm thủy sinh tháng Mão, thương quan.'),
                            block(4, 'Chương mới', kind='heading'), block(5, 'Lý luận chung.')])
        self.assertEqual([u.kind for u in units], ['example', 'paragraph'])
        self.assertEqual([p.block['id'] for p in units[0].pieces], ['b0', 'b1', 'b2', 'b3'])

    def test_example_heading_section_is_one_unit(self):
        units = self.units([block(0, 'Thí dụ 7)', kind='heading'),
                            block(1, 'Thực Thương nhật chủ t.Tài', chart=True),
                            block(2, 'Mậu Kỷ Bính Canh', chart=True),
                            block(3, 'Bính hỏa sanh tháng 6, lửa còn chút sáng.')])
        self.assertEqual([(u.kind, len(u.pieces)) for u in units], [('example', 3)])

    def test_table_rows_stay_together(self):
        units = self.units([block(0, 'Đoạn trước bảng.'), block(1, 'Giáp Ất Bính Đinh', chart=True),
                            block(2, 'Tý Sửu Dần Mão', chart=True), block(3, 'Đoạn sau bảng.')])
        self.assertIn(('table', ['b1', 'b2']), [(u.kind, [p.block['id'] for p in u.pieces])
                                                for u in units])

    def test_only_an_oversized_unit_is_cut_and_flagged(self):
        long_text = words(1500)
        units = self.units([block(0, long_text), block(1, 'Ngắn.')], hard_max=300)
        cut = [u for u in units if u.oversized]
        self.assertGreater(len(cut), 3)
        self.assertFalse(units[-1].oversized)
        for unit in cut:
            self.assertLessEqual(unit.tokens, 300)
            for piece in unit.pieces:
                self.assertEqual(long_text[piece.start:piece.end], piece.text)

    def test_speakers_and_sections_never_mix(self):
        units = self.units([block(0, 'Nguyên văn: a', speaker='original_author'),
                            block(1, 'Từ chú: b', speaker='commentator'),
                            block(2, 'mục mới', section='0002', speaker='commentator')])
        self.assertEqual([(u.section_path, u.speaker) for u in units],
                         [('0001', 'original_author'), ('0001', 'commentator'),
                          ('0002', 'commentator')])


class ChildAndParentTests(unittest.TestCase):
    def test_short_paragraphs_merge_up_to_target_but_not_across_kinds(self):
        blocks = [block(i, f'Câu ngắn thứ {i}.') for i in range(5)] + \
            [block(5, 'Giáp Ất Bính Đinh', chart=True), block(6, 'Câu sau bảng.')]
        children = plan_children(plan_units(blocks, DEFAULTS), {**DEFAULTS, 'child_target': 40})
        kinds = [c.kind for c in children]
        self.assertEqual([k for i, k in enumerate(kinds) if i == 0 or kinds[i - 1] != k],
                         ['paragraph', 'table', 'paragraph'])
        self.assertGreater(len(children[0].pieces), 1)                 # short ones merged
        self.assertTrue(all(c.tokens <= 40 for c in children if c.kind == 'paragraph'))

    def test_spans_are_exact_slices_of_the_child_text(self):
        blocks = [block(0, 'Một đoạn.'), block(1, 'Hai đoạn.')]
        child = plan_children(plan_units(blocks, DEFAULTS), DEFAULTS)[0]
        position = 0
        for piece in child.pieces:
            self.assertEqual(child.text[position:position + len(piece.text)], piece.text)
            position += len(piece.text) + len(SEPARATOR)

    def test_small_section_with_subsections_is_one_parent(self):
        tree = sections(('0001', 'Chương 1', 1), ('0001.0001', 'Mục A', 2), ('0001.0002', 'Mục B', 2))
        blocks = [block(0, 'Mở đầu chương.', '0001'), block(1, 'Nội dung A.', '0001.0001'),
                  block(2, 'Nội dung B.', '0001.0002')]
        children = plan_children(plan_units(blocks, DEFAULTS), DEFAULTS)
        parents = plan_parents(children, tree, DEFAULTS)
        self.assertEqual(len(parents), 1)
        self.assertEqual(parents[0].root_path, '0001')
        self.assertIn('Mục A', parents[0].text)
        self.assertIn('Nội dung B.', parents[0].text)

    def test_large_section_splits_by_subsection_and_every_child_has_one_parent(self):
        tree = sections(('0001', 'Chương 1', 1), ('0001.0001', 'Mục A', 2), ('0001.0002', 'Mục B', 2))
        blocks = [block(0, words(60) + '.', '0001')] + \
            [block(i, words(80, f'S{i}') + '.', '0001.0001') for i in range(1, 4)] + \
            [block(i, words(80, f'S{i}') + '.', '0001.0002') for i in range(4, 7)]
        config = {**DEFAULTS, 'parent_max': 400, 'child_target': 50}
        children = plan_children(plan_units(blocks, config), config)
        parents = plan_parents(children, tree, config)
        members = sorted(i for p in parents for i in p.children)
        self.assertEqual(members, list(range(len(children))))          # exactly once each
        self.assertEqual({p.root_path for p in parents}, {'0001', '0001.0001', '0001.0002'})
        for parent in parents:
            if len(parent.children) > 1:      # one child larger than the budget is its own parent
                self.assertLessEqual(sum(children[i].tokens for i in parent.children), 400)
            paths = {children[i].section_path for i in parent.children}
            self.assertTrue(all(p == parent.root_path or p.startswith(parent.root_path + '.')
                                for p in paths))
        for index, child in enumerate(children):
            self.assertIn(index, parents[child.parent].children)

    def test_parent_text_carries_headings_and_speaker_tags(self):
        tree = sections(('0001', 'Luận dụng thần', 1))
        blocks = [block(0, 'Bát tự dụng thần chuyên cầu nguyệt lệnh.', speaker='original_author'),
                  block(1, 'Từ chú: nguyệt lệnh là đề cương.', speaker='commentator')]
        children = plan_children(plan_units(blocks, DEFAULTS), DEFAULTS)
        text = plan_parents(children, tree, DEFAULTS)[0].text
        self.assertTrue(text.startswith('## Luận dụng thần'))
        self.assertIn('[Nguyên văn] Bát tự', text)
        self.assertIn('[Bình chú] Từ chú', text)

    def test_breadcrumb(self):
        nodes = _tree(sections(('0001', 'Chương 1', 1), ('0001.0002', 'Mục B', 2)))
        self.assertEqual(breadcrumb(nodes, '0001.0002'), ['Chương 1', 'Mục B'])

    def test_token_counter_is_positive(self):
        self.assertGreater(count_tokens('Khách–Chủ, Thể dụng.'), 3)


if __name__ == '__main__':
    unittest.main()
