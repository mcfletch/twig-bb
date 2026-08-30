"""Decode Crunch (`.crn`) textures to images.

Crunch is a block-compressed texture container: the payload decompresses to
BC1 or BC3 blocks, which then decode to pixels.  ``SPEC-CRN`` describes the
header this reads and the checks that established it.

The entropy coding is not implemented here and does not need to be
(``SPEC-CRN §5``): ``texture2ddecoder`` performs that step under an MIT licence,
over a zlib-licensed reference implementation, so neither places any obligation
on this package.  It is an **optional** dependency — absent, `.crn` files
simply do not resolve, exactly as an unsupported format always has.

Nothing dispatches on the header's format code.  ``SPEC-CRN §3.4``: the block
size follows from the decompressed payload's own length, which is a measurement
rather than a table lookup and stays right for format codes this content does
not happen to carry.
"""

from __future__ import annotations

import logging
import struct
from typing import Any, Optional

log = logging.getLogger(__name__)

#: ``SPEC-CRN §1.1`` -- the two bytes every Crunch file opens with.
MAGIC = b'Hx'

#: ``SPEC-CRN §2.1`` -- width, height, level count, face count and format code,
#: all big-endian (``§1.2``), at this offset.
_HEADER = struct.Struct('>HHBBB')
_HEADER_OFFSET = 12

#: ``SPEC-CRN §3.1`` -- bytes per 4x4 block for the two schemes this content
#: uses, in the order they are tried against the payload's length (``§4.1``).
BLOCK_BYTES = (8, 16)

#: The file extension this module claims.
EXTENSION = '.crn'


class MalformedCRN(ValueError):
    """A file that cannot be read as a Crunch texture."""


def available() -> bool:
    """Whether the optional decoder this module needs is installed."""
    return _decoder() is not None


def _decoder() -> Any:
    """The decoding library, or None if it is not installed."""
    try:
        import texture2ddecoder
    except ImportError:
        return None
    return texture2ddecoder


def dimensions(data: bytes) -> Any:
    """``(width, height)`` from a Crunch file's header (``SPEC-CRN §2.1``).

    Reads the header only, so a caller wanting a texture's size need not pay
    for the pixels.
    """
    width, height, _levels, _faces, _format = _header(data)
    return (width, height)


def _header(data: bytes) -> Any:
    """The header fields, after checking the signature (``SPEC-CRN §1.1``)."""
    if len(data) < _HEADER_OFFSET + _HEADER.size:
        raise MalformedCRN('file is too short to hold a Crunch header')
    if data[:2] != MAGIC:
        raise MalformedCRN('not a Crunch texture: signature is %r, expected %r'
                           % (bytes(data[:2]), MAGIC))
    return _HEADER.unpack_from(data, _HEADER_OFFSET)


def load(path: str) -> Optional[Any]:
    """The image in the Crunch file at ``path``, or None.

    None rather than an exception for a file this build cannot read, which is
    what an absent optional decoder means and is the same answer the caller
    already handles for every other undecodable texture.
    """
    try:
        with open(path, 'rb') as handle:
            data = handle.read()
    except OSError as error:
        log.warning('cannot read %s: %s', path, error)
        return None
    return loads(data, path)


def loads(data: bytes, path: str = '<bytes>') -> Optional[Any]:
    """The image in a Crunch file's bytes, or None."""
    library = _decoder()
    if library is None:
        log.warning('%s needs the optional "texture2ddecoder" package, which '
                    'is not installed; install the "crn" extra to read Crunch '
                    'textures', path)
        return None
    try:
        width, height, _levels, _faces, _format = _header(data)
        blocks = _blocks(data, width, height, library, path)
        if blocks is None:
            return None
        pixels, block_bytes = blocks
        decode = library.decode_bc1 if block_bytes == 8 else library.decode_bc3
        from PIL import Image
        return Image.frombytes('RGBA', (width, height),
                               decode(pixels, width, height), 'raw', 'BGRA')
    except Exception as error:              # noqa: BLE001 - never fail a load
        log.warning('cannot decode Crunch texture %s: %s', path, error)
        return None


def _blocks(data: bytes, width: int, height: int, library: Any,
            path: str) -> Optional[Any]:
    """The decompressed blocks for mip level 0, and their size in bytes.

    ``SPEC-CRN §5.2``: of the two bitstream variants the library exposes, this
    content uses the one it names for Unity.  The other returns a payload of
    the *right length* with the block order wrong, so it fails as a scrambled
    image rather than as an error and no length check would catch it.

    ``SPEC-CRN §4.1``: the payload's length identifies the block size outright,
    since it is an exact multiple of the block count for one of the two
    candidates and for neither otherwise.
    """
    pixels = library.unpack_unity_crunch(data)
    count = ((width + 3) // 4) * ((height + 3) // 4)
    for block_bytes in BLOCK_BYTES:
        if len(pixels) == count * block_bytes:
            return (pixels, block_bytes)
    log.warning('%s decompressed to %d bytes, which is not %d blocks at any '
                'supported block size', path, len(pixels), count)
    return None
