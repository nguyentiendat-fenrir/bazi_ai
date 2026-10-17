"""Page images for review and the pipeline profiles uploads use (T046.1)."""
import struct
import unittest
from unittest.mock import patch
import uuid
import zlib

from backend.app.documents import render
from backend.app.ingestion.profiles import ProfileError, create_pipeline_profile
from tests.integration.env import PipelineTestCase


def png_info(data: bytes) -> tuple[int, int, bytes]:
    """(width, height, raw scanlines) of the PNGs written by render.png."""
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    width, height = struct.unpack('>II', data[16:24])
    start = data.index(b'IDAT') + 4
    length = struct.unpack('>I', data[start - 8:start - 4])[0]
    return width, height, zlib.decompress(data[start:start + length])


class PngTests(unittest.TestCase):
    def test_encoder_round_trip(self):
        pixels = bytes([0, 0, 0, 255, 255, 255, 10, 20, 30, 40, 50, 60])
        width, height, raw = png_info(render.png(2, 2, pixels))
        self.assertEqual((width, height), (2, 2))
        self.assertEqual(raw, b'\x00' + pixels[:6] + b'\x00' + pixels[6:])


class RenderTests(PipelineTestCase):
    def first_page(self):
        version, _ = self.ready()
        return self.sql('SELECT r.id FROM page_revisions r JOIN pages p ON p.id = r.page_id'
                        ' WHERE p.book_version_id = %s AND p.physical_page_number = 1'
                        ' ORDER BY r.revision_no DESC LIMIT 1', version)[0][0], version

    def get(self, revision, client=None, **params):
        return (client or self.c).get(f'/api/v1/page-revisions/{revision}/render', params=params)

    def test_png_of_the_displayed_page_with_cache_validators(self):
        revision, _ = self.first_page()
        response = self.get(revision, scale=1)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['content-type'], 'image/png')
        self.assertIn('private', response.headers['cache-control'])
        width, height, raw = png_info(response.content)
        self.assertEqual((width, height), (612, 792))
        self.assertLess(min(raw[1:width * 3 * 200]), 100)   # text, not a blank page
        again = self.c.get(f'/api/v1/page-revisions/{revision}/render', params={'scale': 1},
                           headers={'If-None-Match': response.headers['etag']})
        self.assertEqual((again.status_code, again.content), (304, b''))
        self.assertEqual(png_info(self.get(revision, scale=2).content)[:2], (1224, 1584))
        # Scales snap to quarter steps, so 1.1 is the same image (and ETag) as 1.0.
        self.assertEqual(self.get(revision, scale=1.1).headers['etag'], response.headers['etag'])

    def test_scale_and_pixel_bounds(self):
        revision, _ = self.first_page()
        for bad in (0.1, 3.5):
            self.assertEqual(self.get(revision, scale=bad).status_code, 422)
        with patch.object(render, 'MAX_PIXELS', 100_000):
            width, height, _ = png_info(self.get(revision, scale=3).content)
        self.assertLessEqual(width * height, 100_000)

    def test_access_follows_the_book_and_missing_pages_are_reported(self):
        revision, version = self.first_page()
        reader, _ = self.client('reader')
        self.assertEqual(self.get(revision, reader).status_code, 404)
        self.assertEqual(self.get(uuid.uuid4()).status_code, 404)
        key, sha = self.sql('SELECT o.object_key, o.sha256 FROM book_versions v JOIN objects o'
                            ' ON o.id = v.object_id WHERE v.id = %s', version)[0]
        with self.assertRaises(render.RenderUnavailable):
            render.page_png(self.store, render.Source(key, sha.strip(), 99), 1.0)


class PipelineProfileTests(PipelineTestCase):
    def embedding_of(self, pipeline):
        return self.sql('SELECT embedding_profile_id FROM pipeline_profiles WHERE id = %s',
                        pipeline)[0][0]

    def test_created_from_code_versions_listed_for_reviewers(self):
        embedding = self.embedding_of(self.pipeline)
        with self.owner_engine.begin() as conn:
            first, created = create_pipeline_profile(conn, 'Sách in', embedding, 'vie+eng+chi_sim')
            again, created_again = create_pipeline_profile(conn, 'Sách in', embedding,
                                                           'vie+eng+chi_sim')
            for bad in ('vie;rm', 'VIE'):
                with self.assertRaises(ProfileError):
                    create_pipeline_profile(conn, 'x', embedding, bad)
        self.assertEqual((created, created_again, again), (True, False, first))
        unprovisioned = self.embedding_of(self.pipeline_profile('cold', provision=False))
        with self.owner_engine.begin() as conn, self.assertRaises(ProfileError):
            create_pipeline_profile(conn, 'cold', unprovisioned)

        listed = self.c.get('/api/v1/pipeline-profiles')
        self.assertEqual(listed.status_code, 200, listed.text)
        mine = next(p for p in listed.json()['data'] if p['id'] == str(first))
        self.assertEqual((mine['name'], mine['config'], mine['embedding']['ready'],
                          mine['embedding']['locality']),
                         ('Sách in', {'ocr': {'languages': 'vie+eng+chi_sim'}}, True, 'fixture'))
        self.assertTrue(mine['parser_version'].startswith('pdfium-native-'))
        reader, _ = self.client('reader')
        self.assertEqual(reader.get('/api/v1/pipeline-profiles').status_code, 403)


if __name__ == '__main__':
    unittest.main()
