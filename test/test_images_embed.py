"""Tests for ait.tools.images.embed (board task 67). Loads DINOv2-small once
(downloaded to the HF cache on first run); CPU inference on tiny synthetic
images keeps the suite fast."""

import numpy as np
import pytest
from PIL import Image

from ait.tools.images import embed


def _img(path, colors, size=(64, 64)):
    """Two-tone vertical split — colors control the motif."""
    img = Image.new('RGB', size, colors[0])
    img.paste(Image.new('RGB', (size[0] // 2, size[1]), colors[1]), (size[0] // 2, 0))
    img.save(path)
    return path


@pytest.fixture(scope='module')
def imgs(tmp_path_factory):
    base = tmp_path_factory.mktemp('embed')
    similar_a = _img(base / 'a.png', [(200, 30, 30), (220, 60, 60)])
    similar_b = _img(base / 'b.png', [(190, 40, 25), (210, 70, 55)])
    rng = np.random.default_rng(42)
    noise = Image.fromarray(rng.integers(0, 255, (64, 64, 3), dtype=np.uint8))
    noise.save(base / 'noise.png')
    return {'a': similar_a, 'b': similar_b, 'noise': base / 'noise.png', 'base': base}


class TestEmbedStored:
    def test_store_roundtrip_serves_from_chunk(self, imgs, tmp_path, monkeypatch):
        import ait.tools.images as im

        path = _img(tmp_path / 'stored.png', [(50, 100, 150), (150, 100, 50)])
        (v,) = embed([path], store=True)

        info = Image.open(path).info
        assert 'embedding-dinov2-small' in info

        # a stored batch must resolve without the model: poison the loader
        monkeypatch.setattr(im, '_embed_models', {})
        monkeypatch.setattr(
            'ait.install.snapshot_from_db',
            lambda *a, **k: (_ for _ in ()).throw(AssertionError('model loaded despite cache')),
        )
        (cached,) = embed([path])
        assert float(v @ cached) > 0.999

    def test_store_preserves_other_chunks_and_pixels(self, tmp_path):
        from PIL.PngImagePlugin import PngInfo

        path = tmp_path / 'prov.png'
        img = Image.new('RGB', (32, 32), (10, 200, 90))
        info = PngInfo()
        info.add_text('parent_metadata', '{"url": "/some/parent.png"}')
        img.save(path, pnginfo=info)
        before = np.asarray(Image.open(path))

        embed([path], store=True)

        after_img = Image.open(path)
        assert after_img.info.get('parent_metadata') == '{"url": "/some/parent.png"}'
        assert 'embedding-dinov2-small' in after_img.info
        assert np.array_equal(before, np.asarray(after_img))

    def test_store_skips_non_png(self, tmp_path):
        path = tmp_path / 'img.webp'
        Image.new('RGB', (32, 32), (120, 60, 30)).save(path)
        raw = path.read_bytes()

        (v,) = embed([path], store=True)

        assert v is not None
        assert path.read_bytes() == raw  # untouched

    def test_embed_stored_reads_without_compute(self, imgs, tmp_path, monkeypatch):
        from ait.tools.images import embed_stored

        stored = _img(tmp_path / 's.png', [(20, 40, 60), (60, 40, 20)])
        unstored = _img(tmp_path / 'u.png', [(5, 5, 5), (250, 250, 250)])
        (v,) = embed([stored], store=True)

        # pure read: poison the model loader — embed_stored must never touch it
        import ait.tools.images as im

        monkeypatch.setattr(im, '_embed_models', {})
        monkeypatch.setattr(
            'ait.install.snapshot_from_db',
            lambda *a, **k: (_ for _ in ()).throw(AssertionError('embed_stored loaded a model')),
        )
        vs = embed_stored([stored, unstored, tmp_path / 'missing.png'])

        assert float(vs[0] @ v) > 0.999
        assert vs[1] is None  # readable, but no stored payload
        assert vs[2] is None  # unreadable
        assert embed_stored(stored, model='dinov2:base') == [None]  # model-scoped

    def test_refresh_recomputes_and_restores(self, tmp_path):
        path = _img(tmp_path / 'fresh.png', [(90, 90, 90), (30, 30, 30)])
        (v1,) = embed([path], store=True)
        (v2,) = embed([path], store=True, refresh=True)
        assert float(v1 @ v2) > 0.999
        assert 'embedding-dinov2-small' in Image.open(path).info


class TestEmbed:
    def test_shape_norm_and_order(self, imgs):
        vs = embed([imgs['a'], imgs['b'], imgs['noise']])
        assert len(vs) == 3
        for v in vs:
            assert v.shape == (384,)
            assert v.dtype == np.float32
            assert np.isclose(np.linalg.norm(v), 1.0, atol=1e-5)
        # order stable: same input order, same vectors
        again = embed([imgs['noise'], imgs['a']])
        assert np.allclose(again[1], vs[0], atol=1e-5)

    def test_similarity_ordering(self, imgs):
        a, b, n = embed([imgs['a'], imgs['b'], imgs['noise']])
        assert float(a @ b) > float(a @ n)
        assert float(a @ b) > float(b @ n)

    def test_unreadable_slot_is_none(self, imgs):
        vs = embed([imgs['a'], imgs['base'] / 'missing.png'])
        assert vs[0] is not None
        assert vs[1] is None

    def test_single_path_input(self, imgs):
        vs = embed(imgs['a'])
        assert len(vs) == 1 and vs[0].shape == (384,)

    def test_gpu_auto_matches_cpu(self, imgs):
        # batches > 3 readable images auto-select the GPU when available
        import torch

        if not torch.cuda.is_available():
            pytest.skip('no GPU on this host')
        paths = [imgs['a'], imgs['b'], imgs['noise'], imgs['a']]
        auto = embed(paths)
        cpu = embed(paths, device='cpu')
        for v_auto, v_cpu in zip(auto, cpu, strict=True):
            assert float(v_auto @ v_cpu) > 0.999

    def test_batch_of_16_single_call(self, imgs, tmp_path):
        paths = []
        for i in range(16):
            paths.append(_img(tmp_path / f'g{i}.png', [(i * 15, 80, 120), (30, i * 15, 200)]))
        vs = embed(paths)
        assert len(vs) == 16
        assert all(v is not None and v.shape == (384,) for v in vs)
