"""Shared fixtures: synthetic maps on disk, and the real sample map if present."""

from __future__ import annotations

import glob
import os
from typing import Callable, Dict, Optional

import pytest

import bspbuilder

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
QUAKE3_MAP = os.path.join(WORKSPACE, 'tmp', 'q3', 'ztn', 'maps', 'ztn3dm1.bsp')


# Two test modules define an OpenGLContext window class at import time, which
# needs a real GL backend: with none present (a headless box, plain `tox`) the
# class body raises a metaclass conflict before any test is collected, and the
# whole run errors out.  Skip *collecting* those files when the viewer will not
# import, so the suite is green headless and still runs them where GL is up.
try:
    from twig_bb import viewer as _viewer  # noqa: F401
except Exception:
    collect_ignore = ['test_viewer.py', 'test_viewer_match.py',
                      'test_hudsample.py']


@pytest.fixture
def write_map(tmp_path) -> Callable[..., str]:
    """Write a synthetic map and return its path."""
    def write(version: int, lumps: Dict[str, bytes], name: str = 'test.bsp') -> str:
        maps = tmp_path / 'maps'
        maps.mkdir(exist_ok=True)
        path = maps / name
        path.write_bytes(bspbuilder.build(version, lumps))
        return str(path)
    return write


#: A level from a pack the downloader offers, used when no map is sitting in
#: ``tmp/``.  Named rather than "whichever the pack lists first": the claims
#: made against a real map want curved patches, lightmaps and enough geometry
#: to be worth timing, and a pack listing is ordered by none of those.
#: ``delta`` carries all three, and comes from Debian main under the
#: OpenArena project's CC BY-SA 3.0 / GPL terms.
PACK_MAP = ('openarena-maps', 'delta')


def _sample(path: str, what: str) -> Optional[str]:
    if not os.path.exists(path):
        pytest.skip('%s not present at %s' % (what, path))
    return path


def _map_from_pack() -> Optional[str]:
    """:data:`PACK_MAP` if that pack has been fetched, else None.

    Nothing is downloaded from here: a suite that reached for the network would
    decide on the user's behalf to accept a content licence, which is the
    player's decision and the downloader's job to ask about.
    """
    try:
        from twig_bb import download
    except Exception:                       # pragma: no cover - twig_bb absent
        return None
    key, name = PACK_MAP
    pack = download.pack_for_key(key)
    root = download.pack_root(pack) if pack is not None else None
    if not root:
        return None
    for dirpath, _, names in os.walk(root):
        if name + '.bsp' in names:
            return os.path.join(dirpath, name + '.bsp')
    return None


@pytest.fixture
def quake3_map() -> Optional[str]:
    """A real Quake 3 map (``IBSP`` v46), or skip.

    The checkout's own sample under ``tmp/`` first, since that is what somebody
    working on a particular map has put there; otherwise a level from
    :data:`PACK_MAP`, so a machine that has fetched the pack runs these rather
    than skipping them.
    """
    if os.path.exists(QUAKE3_MAP):
        return QUAKE3_MAP
    from_pack = _map_from_pack()
    if from_pack:
        return from_pack
    pytest.skip('no Quake 3 map: none at %s, and the %s pack is not fetched'
                % (QUAKE3_MAP, PACK_MAP[0]))


def _script_roots(tree: Optional[str]) -> list:
    """Every directory under ``tree`` that is a content root holding scripts.

    A content root is what ``q3shader.load_scripts`` is handed: the directory a
    ``scripts/`` folder sits in, which is one unpacked ``pak`` rather than the
    tree the packs were unpacked into.
    """
    if not tree:
        return []
    found = []
    for dirpath, dirnames, _ in os.walk(tree):
        if 'scripts' in dirnames and glob.glob(
                os.path.join(dirpath, 'scripts', '*.shader')):
            found.append(dirpath)
    return sorted(found)


@pytest.fixture
def quake3_scripts_roots(quake3_map) -> list:
    """The content roots holding the ``.shader`` scripts ``quake3_map`` is built against.

    A self-contained ``.pk3`` carries its own, so the map's own tree is looked
    at first.  A split distribution puts the levels in one package and the
    scripts in another -- which is what a pack's ``companions`` are -- so those
    are searched next.
    """
    from twig_bb import download

    roots = _script_roots(os.path.dirname(os.path.dirname(quake3_map)))
    if roots:
        return roots
    pack = download.pack_for_key(PACK_MAP[0])
    for key in (pack.companions if pack is not None else ()):
        companion = download.pack_for_key(key)
        roots = _script_roots(
            download.pack_root(companion) if companion is not None else None)
        if roots:
            return roots
    pytest.skip('no .shader scripts beside %s or in its companion packs'
                % (quake3_map,))
