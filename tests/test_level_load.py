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
import struct

import pytest
from OpenGLContext.loaders.formats import adapter_for
from OpenGLContext.loaders.sceneloader import SceneLoader

from twig_bb import q3bsp, viewer, weapons


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


class TestTheLevelReader:
    """A map is read by the engine's scene loader, as the game reads it."""

    def test_bsp_and_pk3_are_registered_to_it(self):
        assert isinstance(adapter_for('maps/ztn3dm1.bsp'), viewer.LevelReader)
        assert isinstance(adapter_for('pak0.pk3'), viewer.LevelReader)

    def test_the_loader_reads_a_level_with_the_settings_it_is_given(self, monkeypatch):
        read = []
        monkeypatch.setattr(viewer, 'load_level',
                            lambda options, weapons_table, target:
                            read.append((options, weapons_table, target)) or 'BUNDLE')
        options, table = config(), weapons.default_table()
        loader = SceneLoader()
        request = loader.load('pack:ztn3dm1', format='twig-level',
                              options=viewer.LevelSettings(options, table))
        assert request.wait(5.0) and loader.poll() == 1
        assert request.result == 'BUNDLE'
        assert read == [(options, table, 'pack:ztn3dm1')]

    def test_a_reader_with_no_settings_says_what_it_needs(self):
        with pytest.raises(ValueError, match='LevelSettings'):
            viewer.LevelReader().read('maps/x.bsp')
