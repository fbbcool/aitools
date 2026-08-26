"""Tests for ait.tools.videos.ref_frame (board task 84) — anchor-frame
extraction. Anchor-carrying and anchor-less fixtures are generated locally
with PyAV, mimicking FbbcoolSaveVideo's layout (lossy bulk stream + one
single-frame FFV1/bgr0 stream per anchor, titled `fbbcool_anchor_<slot>`); a
real master written by the suite is exercised when present."""

from pathlib import Path

import av
import numpy as np
import pytest

from ait.tools.videos import ANCHOR_TITLE_PREFIX, ref_frame

SAMPLE_MASTER = Path('/home/misw/Downloads/000_comfy/fbbcool_temp_zeyew_00001_.mkv')

needs_master = pytest.mark.skipif(
    not SAMPLE_MASTER.is_file(), reason=f'FbbcoolSaveVideo master not present: {SAMPLE_MASTER}'
)


def _solid(color: tuple[int, int, int], h: int = 48, w: int = 64) -> np.ndarray:
    return np.full((h, w, 3), color, dtype=np.uint8)


FIRST_RGB = _solid((255, 0, 0))
LAST_RGB = _solid((0, 0, 255))
BULK_RGB = [_solid((10, 10, 10)), _solid((128, 128, 128)), _solid((250, 250, 250))]


def _mux_frames(container, stream, arrays, pix_fmt):
    for arr in arrays:
        frame = av.VideoFrame.from_ndarray(arr, format='rgb24')
        container.mux(stream.encode(frame.reformat(format=pix_fmt)))
    container.mux(stream.encode(None))


@pytest.fixture(scope='module')
def anchored_mkv(tmp_path_factory):
    """FbbcoolSaveVideo-shaped master: lossy bulk + two FFV1/bgr0 anchors."""
    path = tmp_path_factory.mktemp('videos') / 'anchored.mkv'
    with av.open(str(path), 'w') as container:
        bulk = container.add_stream('ffv1', rate=10)
        bulk.width, bulk.height = 64, 48
        bulk.pix_fmt = 'yuv420p'
        anchors = []
        for slot in ('first', 'last'):
            s = container.add_stream('ffv1', rate=10)
            s.width, s.height = 64, 48
            s.pix_fmt = 'bgr0'
            s.metadata['title'] = ANCHOR_TITLE_PREFIX + slot
            anchors.append(s)
        _mux_frames(container, bulk, BULK_RGB, 'yuv420p')
        for stream, arr in zip(anchors, (FIRST_RGB, LAST_RGB), strict=True):
            _mux_frames(container, stream, [arr], 'bgr0')
    return path


@pytest.fixture(scope='module')
def plain_mkv(tmp_path_factory):
    """Anchor-less clip, losslessly encoded so frame contents are assertable."""
    path = tmp_path_factory.mktemp('videos') / 'plain.mkv'
    with av.open(str(path), 'w') as container:
        stream = container.add_stream('ffv1', rate=10)
        stream.width, stream.height = 64, 48
        stream.pix_fmt = 'bgr0'
        _mux_frames(container, stream, BULK_RGB, 'bgr0')
    return path


def test_anchor_streams_bit_exact(anchored_mkv):
    """Named anchor streams win over the bulk and decode bit-exact."""
    for slot, expected in (('first', FIRST_RGB), ('last', LAST_RGB)):
        img = ref_frame(anchored_mkv, slot)
        assert img is not None and img.size == (64, 48)
        assert np.array_equal(np.asarray(img.convert('RGB')), expected)


def test_bulk_fallback_first_last(plain_mkv):
    """Without anchor streams the bulk stream's first/last frames are served."""
    first = ref_frame(plain_mkv, 'first')
    last = ref_frame(plain_mkv, 'last')
    assert np.array_equal(np.asarray(first.convert('RGB')), BULK_RGB[0])
    assert np.array_equal(np.asarray(last.convert('RGB')), BULK_RGB[-1])


def test_missing_file_returns_none(tmp_path):
    assert ref_frame(tmp_path / 'absent.mkv', 'first') is None


def test_non_media_file_returns_none(tmp_path):
    bogus = tmp_path / 'not_a_video.mkv'
    bogus.write_text('definitely not matroska')
    assert ref_frame(bogus, 'first') is None


def test_unknown_slot_raises(tmp_path):
    with pytest.raises(ValueError):
        ref_frame(tmp_path / 'whatever.mkv', 'middle')


@needs_master
def test_real_master_anchors_bit_exact():
    """On a real FbbcoolSaveVideo master, ref_frame equals a direct decode of
    the titled anchor streams."""
    direct = {}
    with av.open(str(SAMPLE_MASTER)) as container:
        anchors = [
            s
            for s in container.streams.video
            if str((s.metadata or {}).get('title', '')).startswith(ANCHOR_TITLE_PREFIX)
        ]
        assert anchors, 'sample master carries no anchor streams'
        for packet in container.demux(anchors):
            for frame in packet.decode():
                title = str(packet.stream.metadata['title'])
                direct.setdefault(title, np.asarray(frame.to_image()))
    for slot in ('first', 'last'):
        img = ref_frame(SAMPLE_MASTER, slot)
        assert np.array_equal(np.asarray(img), direct[ANCHOR_TITLE_PREFIX + slot])
