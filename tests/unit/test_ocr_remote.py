"""Remote OCR: wire format, the server's guards, and the worker's client against a fake engine."""
import os
import unittest
from unittest.mock import patch
import warnings
import zlib

try:
    import numpy as np
except ImportError:            # the ML stack lives in the app image
    np = None

from backend.app.core.config import ConfigError, load_settings
from backend.app.ingestion.ocr import OcrOutOfMemory, OcrUnavailable

TOKEN = 'ocr-test-token-0123456789-abcdefghijklmn'


class FakeEngine:
    version = 'senocr-vi@test+paddleocr-vl-1.6'

    def __init__(self, oom=False):
        self.oom, self.images = oom, []

    def recognize(self, image):
        if self.oom:
            raise OcrOutOfMemory('CUDA out of memory')
        self.images.append(image)
        h, w = image.shape[:2]
        return [{'block_label': 'text', 'block_content': 'Thiên can địa chi', 'block_bbox': [0, 0, w, h]}]


@unittest.skipIf(np is None, 'numpy is not installed here')
class RemoteOcrTests(unittest.TestCase):
    def setUp(self):
        from backend.app.ingestion import ocr_remote
        self.mod = ocr_remote
        self.image = np.full((60, 40, 3), 255, dtype=np.uint8)
        self.image[10:20, 5:30] = (12, 34, 56)

    def remote(self, engine, token=TOKEN):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            from fastapi.testclient import TestClient
        client = TestClient(self.mod.create_server(engine, TOKEN), base_url='http://ocr.test')
        return self.mod.RemoteOcrEngine('http://ocr.test', token, client=client)

    def test_round_trip_keeps_pixels_and_engine_version(self):
        engine = FakeEngine()
        remote = self.remote(engine)
        self.assertEqual(remote.version, engine.version)        # same idempotency keys as local
        items = remote.recognize(self.image)
        self.assertEqual(items[0]['block_content'], 'Thiên can địa chi')
        self.assertEqual(items[0]['block_bbox'], [0, 0, 40, 60])
        self.assertTrue(np.array_equal(engine.images[0], self.image))

    def test_wrong_token_and_gpu_out_of_memory(self):
        with self.assertRaises(OcrUnavailable):
            self.remote(FakeEngine(), token='x' * 40)
        with self.assertRaises(OcrOutOfMemory):               # the worker steps DPI down as before
            self.remote(FakeEngine(oom=True)).recognize(self.image)

    def test_unreachable_server_is_retryable(self):
        import httpx
        from backend.app.ingestion.worker import RetryableError

        def down(request):
            raise httpx.ConnectError('refused', request=request)
        client = httpx.Client(base_url='http://ocr.test', transport=httpx.MockTransport(down))
        with self.assertRaises(RetryableError) as caught:
            self.mod.RemoteOcrEngine('http://ocr.test', TOKEN, client=client)
        self.assertEqual(caught.exception.code, 'OCR_REMOTE_UNREACHABLE')

    def test_decode_refuses_bad_shapes_and_bombs(self):
        body, shape = self.mod.encode(self.image)
        self.assertTrue(np.array_equal(self.mod.decode(body, shape), self.image))
        for bad_shape in ('60,40', '60,40,4', '0,40,3', 'a,b,c', '100000,100000,3'):
            with self.assertRaises(self.mod.BadImage):
                self.mod.decode(body, bad_shape)
        with self.assertRaises(self.mod.BadImage):             # more bytes than the shape says
            self.mod.decode(zlib.compress(b'\0' * (60 * 40 * 3 + 10)), '60,40,3')
        with self.assertRaises(self.mod.BadImage):
            self.mod.decode(b'not zlib', shape)

    def test_server_needs_a_long_token(self):
        with self.assertRaises(RuntimeError):
            self.mod.create_server(FakeEngine(), 'short')

    def test_worker_uses_remote_only_when_configured(self):
        with patch.dict(os.environ, {'OCR_REMOTE_URL': ''}):
            self.assertIsNone(self.mod.engine_from_env())
        with patch.dict(os.environ, {'OCR_REMOTE_URL': 'http://ocr.test', 'OCR_REMOTE_TOKEN': 'short'}):
            with self.assertRaises(OcrUnavailable):
                self.mod.engine_from_env()


class SettingsTests(unittest.TestCase):
    def test_remote_url_needs_a_token_and_the_token_is_redacted(self):
        with self.assertRaises(ConfigError):
            load_settings(_env_file=None, ocr_remote_url='http://ocr.test:8010')
        with self.assertRaises(ConfigError):
            load_settings(_env_file=None, ocr_remote_url='ocr.test', ocr_remote_token=TOKEN)
        settings = load_settings(_env_file=None, ocr_remote_url='http://ocr.test:8010',
                                 ocr_remote_token=TOKEN)
        self.assertIn(TOKEN, settings.secret_values())
        self.assertIsNone(load_settings(_env_file=None, ocr_remote_url='').ocr_remote_url)


if __name__ == '__main__':
    unittest.main()
