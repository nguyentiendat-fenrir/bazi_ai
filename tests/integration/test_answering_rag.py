"""The answering harness on the real RAG retrieval: books ingested and published by the pipeline,
BM25 over the release (no embedding model), the school filter, child → parent."""
import os
from unittest.mock import patch
import uuid

from backend.app.answering.adapters import RagRetriever
from backend.app.answering.harness import Config, Harness
from backend.app.auth.service import Principal
from backend.app.core.config import load_settings
from backend.app.rag.service import RagService, SparseCache
from tests.integration.env import FIELD_KEY, PipelineTestCase
from tests.unit.test_answering import FakeModel, cite_all, honest_judge


class AnsweringOnRagTests(PipelineTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with patch.dict(os.environ, {'FIELD_ENCRYPTION_KEY': FIELD_KEY}, clear=True):
            cls.settings = load_settings(_env_file=None)

    def retriever(self):
        role = self.sql('SELECT email, role FROM users WHERE id = %s', self.user)[0]
        principal = Principal(uuid.UUID(self.user), role[0], role[1], uuid.UUID(int=0), '')
        service = RagService(self.engine, self.settings, None, SparseCache())
        return RagRetriever(service, principal)

    def test_retrieval_school_filter_and_a_full_answer(self):
        self.publish_book([('CHƯƠNG 8: LUẬN DỤNG THẦN',
                            'Dụng thần của bát tự, chuyên tìm ở nguyệt lệnh.'),
                           ('CHƯƠNG 9: THÀNH BẠI',
                            'Dụng thần chuyên tìm ở nguyệt lệnh, phối với tứ trụ, tất có thành bại.')],
                          'tu_binh')
        self.publish_book([('CHƯƠNG 5: MỘ KHỐ', 'Mộ bị xung gọi là khố, mộ không xung là tử.'),
                           ('CHƯƠNG 6: KHÁCH CHỦ', 'Bát tự là chủ, đại vận và lưu niên là khách.')],
                          'manh_phai')
        retriever = self.retriever()

        found = retriever.search('dụng thần nguyệt lệnh', 'tu_binh', 4)
        self.assertTrue(found)
        self.assertTrue(all(p.school == 'tu_binh' for p in found))
        self.assertTrue(any('nguyệt lệnh' in p.text for p in found))
        self.assertEqual(len({p.pid for p in found}), len(found))
        self.assertFalse(any('Mộ bị xung' in p.text for p in retriever.search('mộ xung khố', 'tu_binh', 4)))
        mp = retriever.search('mộ xung khố', 'manh_phai', 4)
        self.assertTrue(any('Mộ bị xung' in p.text for p in mp))
        self.assertTrue(all(p.pages.startswith('tr.') for p in mp))

        model = FakeModel(judge=honest_judge, synthesize=cite_all, rewrite={'queries': ['nguyệt lệnh']})
        result = Harness(model, retriever, config=Config(decompose_min_chars=10_000)).answer(
            'Theo Tử Bình Chân Thuyên, dụng thần tìm ở đâu?')
        self.assertEqual(result.status, 'ok', result.trace)
        cited = [s for s in result.sources if s['cited']]
        self.assertTrue(cited)
        self.assertTrue(all(s['school'] == 'tu_binh' for s in cited))
        self.assertIn('nguyệt lệnh', result.answer)
