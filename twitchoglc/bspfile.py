"""The `IBSP` container both map families share: header, directory, lumps.

``SPEC-BSP38 §1`` and ``SPEC-BSP46 §1`` describe the same container shape —
a four-byte identifier, a version, and a directory of (offset, length) pairs —
and differ only in the directory's length and in what each entry means.  This
module reads that far and no further; a family reader supplies the record
layouts.

A map is memory-mapped and lumps are taken as zero-copy ``numpy`` views of it,
so reading a four-megabyte map costs no parsing pass over its records: the
record layout is a ``dtype`` and a lump is that dtype's view of a byte range.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)

# SPEC-BSP38 §1.1 / SPEC-BSP46 §1.1 -- the identifier, as its four ASCII bytes.
BSP_MAGIC = b'IBSP'
# SPEC-BSP38 §1.4 -- a directory entry is two little-endian int32s.
DIRECTORY_ENTRY_SIZE = 8
HEADER_PREFIX_SIZE = 8          # identifier + version, before the directory


class MalformedBSP(ValueError):
    """A file that cannot be read as an `IBSP` map of the expected version."""


def read_file(path: str) -> np.ndarray:
    """Memory-map ``path`` as a copy-on-write byte array.

    Copy-on-write so a lump view can be written through (an in-place fix-up)
    without touching the user's file on disk.
    """
    if not os.path.isfile(path):
        raise MalformedBSP('%s is not a file' % (path,))
    return np.memmap(path, dtype=np.uint8, mode='c')


def read_version(data: np.ndarray) -> int:
    """The file's version number, after checking the identifier.

    ``SPEC-BSP38 §1.1``, ``§1.2``: the identifier is the first four bytes and
    the version the next four, little-endian (``§1.3``).
    """
    if len(data) < HEADER_PREFIX_SIZE:
        raise MalformedBSP('file is too short to hold a BSP header')
    magic = bytes(data[:4])
    if magic != BSP_MAGIC:
        if magic[:2] == b'PK':
            raise MalformedBSP(
                'this looks like a .pk3/.zip archive, not a .bsp map')
        raise MalformedBSP('not a BSP file: identifier is %r, expected %r'
                           % (magic, BSP_MAGIC))
    return int(data[4:8].view('<i4')[0])


def read_directory(data: np.ndarray, count: int) -> np.ndarray:
    """The lump directory as a ``(count, 2)`` array of (offset, length).

    ``SPEC-BSP38 §1.4``, ``§1.5`` / ``SPEC-BSP46 §1.4``, ``§1.5``.
    """
    end = HEADER_PREFIX_SIZE + count * DIRECTORY_ENTRY_SIZE
    if len(data) < end:
        raise MalformedBSP('file is too short to hold a %d-lump directory' % (count,))
    return data[HEADER_PREFIX_SIZE:end].view('<i4').reshape((count, 2)).copy()


def lump_bytes(data: np.ndarray, directory: np.ndarray, index: int,
               name: str) -> np.ndarray:
    """The raw bytes of one lump, after bounds-checking it.

    ``SPEC-BSP38 §12.1``: validate that a lump's offset and length lie inside
    the file before dereferencing anything through it.  ``SPEC-BSP38 §1.8`` /
    ``§12.2``: a lump's extent comes only from its own directory entry, never
    from the next lump's offset, because lumps need not be in directory order.
    """
    offset, length = (int(v) for v in directory[index])
    if offset < 0 or length < 0:
        raise MalformedBSP('lump %s has a negative offset/length (%d, %d)'
                           % (name, offset, length))
    if offset + length > len(data):
        raise MalformedBSP(
            'lump %s runs past the end of the file (%d + %d > %d)'
            % (name, offset, length, len(data)))
    return data[offset:offset + length]


def lump_records(data: np.ndarray, directory: np.ndarray, index: int,
                 dtype: Any, name: str) -> np.ndarray:
    """One lump viewed as an array of fixed-size records.

    ``SPEC-BSP38 §1.6`` / ``SPEC-BSP46 §1.6``: the record count is the lump
    length divided by the record size.  A length that is not an exact multiple
    signals a malformed file; the trailing partial record is dropped with a
    warning rather than raising, so one damaged lump does not cost the map.
    """
    raw = lump_bytes(data, directory, index, name)
    record = np.dtype(dtype)
    extra = len(raw) % record.itemsize
    if extra:
        log.warning('lump %s has %d trailing bytes that are not a whole '
                    '%d-byte record; dropping them', name, extra, record.itemsize)
        raw = raw[:len(raw) - extra]
    return raw.view(record)


def fixed_string(raw: np.ndarray) -> str:
    """Decode a NUL-terminated, NUL-padded fixed-width name field.

    ``SPEC-BSP38 §6.4`` (32 bytes) and ``SPEC-BSP46 §6.1`` (64 bytes) use the
    same convention: NUL-terminated, NUL-padded, and a field with no NUL at all
    is the full width.
    """
    return bytes(raw).split(b'\x00', 1)[0].decode('latin-1')


def sniff_version(path: str) -> Optional[Tuple[bytes, int]]:
    """``(identifier, version)`` of a map file, or None if it is not one.

    Used by the dispatching loader to pick a family reader without reading the
    whole file (``SPEC-BSP38 §1.2``, ``SPEC-BSP46 §1.2``).
    """
    try:
        with open(path, 'rb') as handle:
            head = handle.read(HEADER_PREFIX_SIZE)
    except OSError:
        return None
    if len(head) < HEADER_PREFIX_SIZE or head[:4] != BSP_MAGIC:
        return None
    return head[:4], int(np.frombuffer(head[4:8], dtype='<i4')[0])
