"""The map's light grid, and the scene node built from it.

A Quake 3 map bakes its lighting and places no lamps, so anything that was not
there when the map was compiled -- a combatant, a pickup, a rocket -- has
nothing lighting it at all.  What the map does carry for them is the lightvol
lump: a coarse grid of samples over the level saying how much light reaches
each point and from where (``SPEC-BSP46 §4.14``).

The lump says only what the samples *are*, so where they are has to be worked
out from the map's own bounds, and the reading has to be defended: a grid
placed wrongly lights a level from the wrong places, which is worse than not
lighting it at all.
"""

from __future__ import annotations

import numpy as np
import pytest

import bspbuilder
from twig_bb import lighting, q3bsp
from twig_bb.worldgeometry import SCENE_SCALE


def _bsp(tmp_path, lumps, name='light-test.bsp'):
    maps = tmp_path / 'maps'
    maps.mkdir(parents=True, exist_ok=True)
    path = maps / name
    path.write_bytes(bspbuilder.build(46, lumps))
    return q3bsp.load(str(path))


def _lumps(mins, maxs, samples, gridsize=None):
    """A map whose world model spans ``mins``..``maxs`` and holds ``samples``."""
    lumps = bspbuilder.v46_quad()
    world = {'classname': 'worldspawn'}
    if gridsize is not None:
        world['gridsize'] = ' '.join('%g' % value for value in gridsize)
    lumps['entities'] = bspbuilder.entity_text([world])
    lumps['models'] = bspbuilder.v46_model(mins, maxs, 0, 1)
    lumps['lightvols'] = samples.tobytes()
    return lumps


def _samples(count, ambient=0, directional=0, direction=(0, 0)):
    array = np.zeros(count, dtype=q3bsp.LIGHTVOL)
    array['ambient'] = ambient
    array['directional'] = directional
    array['direction'] = direction
    return array


class TestWhereTheSamplesAre:
    """``SPEC-BSP46 §4.14.2``: the lattice inside the world's own bounds."""

    def test_the_default_spacing_is_the_one_the_compiler_uses(self):
        assert lighting.DEFAULT_GRID_SIZE == (64.0, 64.0, 128.0)

    def test_the_samples_sit_on_multiples_of_the_spacing(self):
        origin, counts = lighting.grid_placement(
            (-100.0, -100.0, -100.0), (100.0, 100.0, 100.0),
            (64.0, 64.0, 128.0))
        assert tuple(origin) == (-64.0, -64.0, 0.0)
        assert tuple(counts) == (3, 3, 1)

    def test_bounds_already_on_the_lattice_keep_their_ends(self):
        origin, counts = lighting.grid_placement(
            (-128.0, 0.0, 0.0), (128.0, 64.0, 128.0), (64.0, 64.0, 128.0))
        assert tuple(origin) == (-128.0, 0.0, 0.0)
        assert tuple(counts) == (5, 2, 2)

    def test_a_worldspawn_gridsize_replaces_the_default(self, tmp_path):
        bsp = _bsp(tmp_path, _lumps((0, 0, 0), (128, 128, 128),
                                    _samples(27), gridsize=(64, 64, 64)))
        assert lighting.grid_spacing(bsp) == (64.0, 64.0, 64.0)

    def test_a_map_that_says_nothing_gets_the_default(self, tmp_path):
        bsp = _bsp(tmp_path, _lumps((0, 0, 0), (128, 128, 128), _samples(27)))
        assert lighting.grid_spacing(bsp) == lighting.DEFAULT_GRID_SIZE


class TestRefusingAGridThatDoesNotAddUp:
    """A grid placed wrongly lights the level from the wrong places."""

    def test_a_map_with_no_lightvols_has_no_grid(self, tmp_path):
        bsp = _bsp(tmp_path, _lumps((0, 0, 0), (128, 128, 128), _samples(0)))
        assert lighting.light_grid(bsp) is None

    def test_a_sample_count_that_disagrees_is_refused(self, tmp_path, caplog):
        """Better an unlit figure than one lit from somewhere else entirely."""
        bsp = _bsp(tmp_path, _lumps((0, 0, 0), (128, 128, 128), _samples(5)))
        with caplog.at_level('WARNING'):
            assert lighting.light_grid(bsp) is None
        assert any('light grid' in record.message for record in caplog.records)

    def test_the_expected_count_is_the_lattice_size(self, tmp_path):
        """3 x 3 x 2 over 0..128 at the default spacing."""
        bsp = _bsp(tmp_path, _lumps((0, 0, 0), (128, 128, 128), _samples(18)))
        assert lighting.light_grid(bsp) is not None


class TestTheNodeAScenegraphGets:

    def _grid(self, tmp_path, **named):
        samples = _samples(18, ambient=64, directional=255, direction=(0, 0))
        bsp = _bsp(tmp_path, _lumps((0, 0, 0), (128, 128, 128), samples))
        return lighting.light_grid(bsp, **named)

    def test_it_is_the_engine_s_own_node(self, tmp_path):
        from OpenGLContext.scenegraph.lightgrid import LightGrid
        assert isinstance(self._grid(tmp_path), LightGrid)

    def test_it_holds_a_sample_for_every_point(self, tmp_path):
        grid = self._grid(tmp_path)
        assert len(grid.ambient) == 18
        assert grid.filled

    def test_the_counts_are_in_scene_axes(self, tmp_path):
        """Map z is scene y, so the vertical count moves with it."""
        grid = self._grid(tmp_path)
        assert tuple(int(v) for v in grid.counts) == (3, 2, 3)

    def test_it_is_measured_in_metres(self, tmp_path):
        grid = self._grid(tmp_path)
        assert tuple(round(float(v), 6) for v in grid.spacing) == (
            round(64 * SCENE_SCALE, 6), round(128 * SCENE_SCALE, 6),
            round(64 * SCENE_SCALE, 6))

    def test_the_bytes_are_read_as_light_rather_than_colour(self, tmp_path):
        """A baked solution is linear, so 64/255 arrives as 64/255."""
        grid = self._grid(tmp_path, strength=1.0)
        assert float(np.asarray(grid.ambient)[0][0]) == pytest.approx(
            64 / 255.0, abs=1e-3)

    def test_the_lightmap_exposure_scales_it(self, tmp_path):
        """The grid and the lightmaps are one solve and must read alike."""
        assert float(self._grid(tmp_path, strength=2.5).intensity) == \
            pytest.approx(2.5)


class TestWhatALoadedMapOffers:
    """The grid reaches the scenegraph through the map that carries it."""

    def _loaded(self, tmp_path, samples):
        from twig_bb import maploader
        maps = tmp_path / 'maps'
        maps.mkdir(parents=True, exist_ok=True)
        path = maps / 'loaded.bsp'
        path.write_bytes(bspbuilder.build(
            46, _lumps((0, 0, 0), (128, 128, 128), samples)))
        return maploader.load(str(path))

    def test_a_map_with_a_grid_offers_it(self, tmp_path):
        grid = self._loaded(tmp_path, _samples(18, ambient=32)).lightGrid()
        assert grid is not None and grid.filled

    def test_a_map_without_one_offers_nothing(self, tmp_path):
        assert self._loaded(tmp_path, _samples(0)).lightGrid() is None

    def test_it_is_read_at_the_exposure_the_map_is_drawn_at(self, tmp_path):
        """Whatever ``--lightmap`` set, since it is one solve either way."""
        loaded = self._loaded(tmp_path, _samples(18, ambient=32))
        loaded.library.lightmap_strength = 3.0
        assert float(loaded.lightGrid().intensity) == pytest.approx(3.0)

    def test_it_is_built_once_and_kept(self, tmp_path):
        """A level asks nothing of it again; rebuilding it would be waste."""
        loaded = self._loaded(tmp_path, _samples(18, ambient=32))
        assert loaded.lightGrid() is loaded.lightGrid()


class TestWhichWayTheLightComesFrom:
    """``SPEC-BSP46 §4.14.5``, converted into the scene's own axes."""

    def _direction(self, tmp_path, phi, theta):
        samples = _samples(18, ambient=8, directional=255,
                           direction=(phi, theta))
        bsp = _bsp(tmp_path, _lumps((0, 0, 0), (128, 128, 128), samples))
        return np.asarray(lighting.light_grid(bsp).direction)[0]

    def test_a_zero_polar_angle_is_straight_up(self, tmp_path):
        """Map +Z is scene +Y: light from directly overhead."""
        assert self._direction(tmp_path, 0, 0) == pytest.approx(
            [0.0, 1.0, 0.0], abs=1e-3)

    def test_a_quarter_turn_of_polar_lies_in_the_floor_plane(self, tmp_path):
        """phi = 64 bytes is a quarter of 2*pi: along map +X, which is scene +X."""
        assert self._direction(tmp_path, 64, 0) == pytest.approx(
            [1.0, 0.0, 0.0], abs=1e-2)

    def test_the_second_byte_turns_it_about_the_upright_axis(self, tmp_path):
        """phi = 64, theta = 64 is map +Y, which is scene -Z."""
        assert self._direction(tmp_path, 64, 64) == pytest.approx(
            [0.0, 0.0, -1.0], abs=1e-2)

    def test_every_direction_is_unit_length(self, tmp_path):
        lengths = np.linalg.norm(self._direction(tmp_path, 37, 91))
        assert lengths == pytest.approx(1.0, abs=1e-3)
