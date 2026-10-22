"""Where the Jina models run: RAG_DEVICE / RAG_DTYPE, GPU fallback, and settings validation."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.app.core.config import ConfigError, load_settings
from backend.app.rag.models import ModelSpec, placement


def fake_torch(gpu: bool):
    return SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: gpu),
                           float32='torch.float32', bfloat16='torch.bfloat16', float16='torch.float16')


class PlacementTests(unittest.TestCase):
    def spec(self, **env):
        with patch.dict(os.environ, {'RAG_DEVICE': '', 'RAG_DTYPE': '', **env}):
            return ModelSpec('jinaai/x', 'rev')

    def test_cpu_by_default_in_fp32(self):
        self.assertEqual(placement(self.spec(), fake_torch(True)), ('cpu', 'torch.float32'))

    def test_gpu_defaults_to_bf16_and_honours_an_override(self):
        self.assertEqual(placement(self.spec(RAG_DEVICE='cuda'), fake_torch(True)),
                         ('cuda', 'torch.bfloat16'))
        self.assertEqual(placement(self.spec(RAG_DEVICE='cuda:0', RAG_DTYPE='fp32'), fake_torch(True)),
                         ('cuda:0', 'torch.float32'))

    def test_no_gpu_falls_back_to_cpu_fp32(self):
        with self.assertLogs('bazi.rag.models', 'WARNING'):
            got = placement(self.spec(RAG_DEVICE='cuda', RAG_DTYPE='bf16'), fake_torch(False))
        self.assertEqual(got, ('cpu', 'torch.float32'))

    def test_specs_differ_by_device_so_the_cache_never_mixes_them(self):
        self.assertNotEqual(self.spec(RAG_DEVICE='cuda'), self.spec())

    def test_settings_reject_unknown_device_or_dtype(self):
        with self.assertRaises(ConfigError):
            load_settings(_env_file=None, rag_device='gpu')
        with self.assertRaises(ConfigError):
            load_settings(_env_file=None, rag_dtype='int8')
        self.assertEqual(load_settings(_env_file=None, rag_device='cuda:1').rag_device, 'cuda:1')


if __name__ == '__main__':
    unittest.main()
