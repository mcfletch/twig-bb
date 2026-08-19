"""Building a level's match as data, off the render thread.

Starting a level decodes the map and stages the match in it, and neither touches
GL -- so it is a plain function that a worker thread can run while the window
keeps drawing, handing back a :class:`~twig_bb.viewer.LevelBundle` the render
thread then mounts. These tests drive that function with no window: a map-less
match for the start screen, a cast for the bots in it, and a real map decoded
without a GL context.
"""
from __future__ import annotations

import glob
import os

import pytest

from twig_bb import viewer, weapons


def config(**over):
    options = viewer.build_parser().parse_args([])
    for key, value in over.items():
        setattr(options, key, value)
    return options


def test_a_mapless_match_is_built_for_the_start_screen():
    bundle = viewer.build_match(config(), weapons.default_table(), None)
    assert bundle.loaded is None
    assert bundle.arena is not None
    assert bundle.player is not None
    assert bundle.rules is not None
    assert bundle.deathCamera is not None


def test_bots_get_a_cast_of_drawn_figures():
    bundle = viewer.build_match(config(bots=2), weapons.default_table(), None)
    assert len(bundle.cast) == 2
    assert bundle.botGroup is not None


def _a_supported_map():
    """A map file this build can actually decode, or None.

    The cache holds whatever has been downloaded into it, which includes maps
    of formats twig-bb does not read; picking the first name off the disk tests
    the loader against a file it was never meant to open.
    """
    import struct

    from twig_bb import q3bsp

    for path in sorted(glob.glob(os.path.expanduser(
            '~/.config/OpenGLContext/twig-bb-maps/*/maps/*.bsp'))):
        with open(path, 'rb') as handle:
            header = handle.read(8)
        if len(header) == 8 and header[:4] == b'IBSP' \
                and struct.unpack('<i', header[4:])[0] == q3bsp.BSP_VERSION:
            return path
    return None


def test_load_level_decodes_a_real_map_without_a_gl_context():
    found = _a_supported_map()
    if found is None:
        pytest.skip('no map content available in this environment')
    bundle = viewer.load_level(config(), weapons.default_table(), found)
    assert bundle.loaded is not None
    assert bundle.arena is not None
