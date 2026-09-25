"""Reading Crunch (`.crn`) textures — ``SPEC-CRN``.

The header facts are checked against bytes this module builds itself, so a
passing test says the reader agrees with the specification rather than with its
own struct format.  Decoding a real payload needs the optional package and a
sample file, and skips without them.
"""

from __future__ import annotations

import logging
import os
import struct

import pytest

from twig_bb import crnfile

#: Where the sample packages are unpacked, if this machine has them.
SAMPLE_ROOT = os.environ.get('TWIG_BB_CRN_SAMPLES', '')


def _header(width: int, height: int, levels: int = 10, faces: int = 1,
            fmt: int = 0, payload: bytes = b'') -> bytes:
    """A Crunch header laid out per ``SPEC-CRN §2.1``, big-endian (``§1.2``).

    Built from the spec rather than from :mod:`twig_bb.crnfile`'s own struct,
    which is the point: the two agreeing is the fact under test.
    """
    size = 20 + len(payload)
    head = struct.pack('>HHH', 0x4878, 20, 0)           # magic, header size, crc
    head += struct.pack('>IH', size, 0)                 # total size, payload crc
    head += struct.pack('>HH', width, height)
    head += struct.pack('>BBB', levels, faces, fmt)
    head += struct.pack('>H', 0)                        # flags
    return head + payload


def test_the_signature_identifies_a_crunch_file():
    """SPEC-CRN §1.1: the two bytes every Crunch file opens with."""
    assert crnfile.MAGIC == b'Hx'
    assert _header(64, 64)[:2] == crnfile.MAGIC


def test_dimensions_are_read_big_endian():
    """SPEC-CRN §1.2, §2.1: width and height at offset 12, big-endian.

    A little-endian read of 512 x 256 would give 2 x 1, so the byte order is
    what this actually pins down.
    """
    assert crnfile.dimensions(_header(512, 256)) == (512, 256)


def test_a_file_that_is_not_crunch_is_refused():
    with pytest.raises(crnfile.MalformedCRN):
        crnfile.dimensions(b'\x89PNG\r\n\x1a\n' + b'\x00' * 32)


def test_a_truncated_header_is_refused():
    with pytest.raises(crnfile.MalformedCRN):
        crnfile.dimensions(_header(64, 64)[:8])


def test_an_unreadable_file_is_none_rather_than_an_error(tmp_path):
    """A texture that will not open is None, as every other format's is."""
    assert crnfile.load(str(tmp_path / 'absent.crn')) is None


def test_a_file_that_is_not_crunch_loads_as_none(tmp_path):
    """`loads` reports rather than raises: a bad texture is not a bad map."""
    path = tmp_path / 'bad.crn'
    path.write_bytes(b'not a crunch file at all')
    assert crnfile.load(str(path)) is None


def test_a_decoder_failure_is_logged_with_its_traceback(monkeypatch, caplog):
    """The decoder is a compiled extension; what it raises is reported whole."""
    class Broken:
        @staticmethod
        def unpack_unity_crunch(data):
            raise RuntimeError('inside the decoder')

    monkeypatch.setattr(crnfile, '_decoder', lambda: Broken)
    with caplog.at_level(logging.WARNING, logger=crnfile.__name__):
        assert crnfile.loads(_header(64, 64) + b'\x00' * 64, 'x.crn') is None
    assert caplog.records[-1].exc_info is not None


def test_a_malformed_file_is_reported_without_a_traceback(monkeypatch, caplog):
    """Bad content is a fact about the file, not a fault in this code."""
    monkeypatch.setattr(crnfile, '_decoder', lambda: object())
    with caplog.at_level(logging.WARNING, logger=crnfile.__name__):
        assert crnfile.loads(b'not a crunch file at all', 'x.crn') is None
    assert 'x.crn' in caplog.text
    assert caplog.records[-1].exc_info is None


def test_the_block_size_comes_from_the_payload_not_the_format_code():
    """SPEC-CRN §3.4, §4.1: the two candidate block sizes, in order."""
    assert crnfile.BLOCK_BYTES == (8, 16)


@pytest.mark.skipif(not crnfile.available(),
                    reason='the optional texture2ddecoder package is absent')
@pytest.mark.skipif(not SAMPLE_ROOT or not os.path.isdir(SAMPLE_ROOT),
                    reason='no Crunch sample tree; set TWIG_BB_CRN_SAMPLES')
def test_a_real_crunch_texture_decodes_to_its_stated_size():
    """SPEC-CRN §4.1, §4.2: the payload decodes at the header's dimensions."""
    samples = []
    for directory, _, files in os.walk(SAMPLE_ROOT):
        samples.extend(os.path.join(directory, name) for name in files
                       if name.lower().endswith('.crn'))
    if not samples:
        pytest.skip('no .crn files under %s' % (SAMPLE_ROOT,))
    for path in sorted(samples)[:8]:
        with open(path, 'rb') as handle:
            data = handle.read()
        image = crnfile.load(path)
        assert image is not None, path
        assert image.size == crnfile.dimensions(data), path
