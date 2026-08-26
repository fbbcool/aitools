"""Tests for ait.tools.videos.metadata (board task 82) — the video branch of
the embedded-metadata reader. The primary fixture is the FFV1/FLAC MKV written
by FbbcoolSaveVideo's real encoder (agent-comfy workspace); tagless/non-media
cases are generated locally with PyAV."""

import json
from pathlib import Path

import av
import numpy as np
import pytest

from ait.tools.images import METADATA_SCHEMA
from ait.tools.videos import metadata

FIXTURE_MKV = Path('/home/misw/Repos/fbbcool/agent-comfy/docs/fixtures/parent_metadata_sample.mkv')

needs_fixture = pytest.mark.skipif(
    not FIXTURE_MKV.is_file(), reason=f'agent-comfy fixture not present: {FIXTURE_MKV}'
)


@pytest.fixture(scope='module')
def tagless_mkv(tmp_path_factory):
    """A valid, readable MKV carrying no metadata tags (one gray frame)."""
    path = tmp_path_factory.mktemp('videos') / 'tagless.mkv'
    with av.open(str(path), 'w') as container:
        stream = container.add_stream('ffv1', rate=10)
        stream.width, stream.height = 64, 48
        stream.pix_fmt = 'yuv420p'
        frame = av.VideoFrame.from_ndarray(
            np.full((48, 64, 3), 128, dtype=np.uint8), format='rgb24'
        )
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


@needs_fixture
def test_fixture_parent_json_equal():
    """The `parent` key equals the embedded PARENT_METADATA envelope."""
    with av.open(str(FIXTURE_MKV)) as container:
        embedded = json.loads(container.metadata['PARENT_METADATA'])
    md = metadata(FIXTURE_MKV)
    assert md is not None
    assert md['schema'] == METADATA_SCHEMA
    assert md['parent'] == embedded


@needs_fixture
def test_fixture_v1_shape():
    """Same v1 dict as the image path: every key present, prompt/workflow
    parsed from the (ffmpeg-uppercased) container tags."""
    md = metadata(FIXTURE_MKV)
    assert set(md) == {
        'schema',
        'url',
        'image',
        'comfy',
        'enhancer',
        'generation',
        'loras',
        'seed',
        'parent',
        'inherited',
    }
    assert md['url'] == str(FIXTURE_MKV)
    # case-insensitive tag matching: read-back keys are PROMPT/WORKFLOW
    assert isinstance(md['comfy']['prompt_graph'], dict)
    assert isinstance(md['comfy']['workflow'], dict)
    assert md['image']['width'] == 96 and md['image']['height'] == 64


def test_tagless_video_returns_none(tagless_mkv):
    assert metadata(tagless_mkv) is None


def test_non_media_file_returns_none(tmp_path):
    bogus = tmp_path / 'not_a_video.mkv'
    bogus.write_text('definitely not matroska')
    assert metadata(bogus) is None


def test_missing_file_returns_none(tmp_path):
    assert metadata(tmp_path / 'absent.mkv') is None
