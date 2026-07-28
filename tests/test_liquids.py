"""Liquid volumes: where the avatar is under water rather than in air.

Which leaves hold a liquid is a format fact and differs by family, so the two
readings are tested against built maps; what a viewer asks — "am I in one?" —
is the same question either way.
"""

from __future__ import annotations

import numpy as np
import pytest

import bspbuilder
from twitchoglc import liquids, maploader, q2bsp
from twitchoglc.worldgeometry import SCENE_SCALE


def _volumes(*boxes):
    return liquids.LiquidVolumes([
        liquids.LiquidVolume(mins=np.array(lo, 'd'), maxs=np.array(hi, 'd'))
        for lo, hi in boxes])


def test_a_point_inside_a_volume_is_submerged():
    volumes = _volumes(((0, 0, 0), (10, 5, 10)))
    assert volumes.contains((5, 2, 5))


def test_a_point_outside_every_volume_is_not():
    volumes = _volumes(((0, 0, 0), (10, 5, 10)))
    assert not volumes.contains((5, 8, 5))
    assert not volumes.contains((-1, 2, 5))


def test_the_faces_of_a_volume_count_as_inside():
    """A camera exactly on the surface should read as in the water rather than
    flickering between modes as it bobs."""
    volumes = _volumes(((0, 0, 0), (10, 5, 10)))
    assert volumes.contains((0, 0, 0))
    assert volumes.contains((10, 5, 10))


def test_any_of_several_volumes_counts():
    volumes = _volumes(((0, 0, 0), (1, 1, 1)), ((20, 0, 20), (30, 5, 30)))
    assert volumes.contains((25, 1, 25))


def test_a_map_with_no_liquid_is_never_submerged():
    assert not liquids.LiquidVolumes([]).contains((0, 0, 0))
    assert not liquids.LiquidVolumes([])


def test_volumes_report_how_many_there_are():
    assert len(_volumes(((0, 0, 0), (1, 1, 1)))) == 1


# -- reading them out of a map ------------------------------------------------

def _v38_map(tmp_path, contents, name='liquid.bsp'):
    """A version 38 map with one leaf carrying ``contents``."""
    lumps = bspbuilder.v38_quad(size=512.0)
    leaves = np.zeros(2, dtype=q2bsp.LEAF)
    leaves[0]['contents'] = q2bsp.CONTENTS_SOLID
    leaves[1]['contents'] = contents
    leaves[1]['mins'] = (0, 0, 0)
    leaves[1]['maxs'] = (128, 256, 64)
    lumps['leafs'] = leaves.tobytes()
    path = tmp_path / name
    path.write_bytes(bspbuilder.build(38, lumps))
    return str(path)


@pytest.mark.parametrize('contents', [q2bsp.CONTENTS_WATER, q2bsp.CONTENTS_SLIME,
                                      q2bsp.CONTENTS_LAVA])
def test_a_version_38_leaf_of_liquid_becomes_a_volume(tmp_path, contents):
    """`SPEC-BSP38 §9.4`: water, slime and lava are the liquids."""
    loaded = maploader.load(_v38_map(tmp_path, contents))
    volumes = liquids.from_map(loaded)
    assert len(volumes) == 1


def test_a_version_38_solid_leaf_is_not_a_volume(tmp_path):
    loaded = maploader.load(_v38_map(tmp_path, q2bsp.CONTENTS_SOLID))
    assert not liquids.from_map(loaded)


def test_a_leaf_that_is_both_liquid_and_something_else_still_counts(tmp_path):
    """`SPEC-BSP38 §9.1`: contents bits combine freely."""
    loaded = maploader.load(
        _v38_map(tmp_path, q2bsp.CONTENTS_WATER | q2bsp.CONTENTS_TRANSLUCENT))
    assert len(liquids.from_map(loaded)) == 1


def test_the_volume_is_in_scene_space(tmp_path):
    """Map units are inches on a Z-up axis; the scene is metres and Y-up
    (`SPEC-BSP38 §3.2`), so a volume read in map units puts the swimmer in the
    wrong place by a factor of forty."""
    loaded = maploader.load(_v38_map(tmp_path, q2bsp.CONTENTS_WATER))
    volume = liquids.from_map(loaded)._volumes[0]
    extent = volume.maxs - volume.mins
    assert sorted(np.round(extent, 6)) == pytest.approx(
        sorted(np.round(np.array([128.0, 256.0, 64.0]) * SCENE_SCALE, 6)))


def test_the_volume_bounds_are_ordered_after_the_axis_swap(tmp_path):
    """The axis convention negates a coordinate, so a min can come out above a
    max and the box would contain nothing at all."""
    loaded = maploader.load(_v38_map(tmp_path, q2bsp.CONTENTS_WATER))
    volume = liquids.from_map(loaded)._volumes[0]
    assert (volume.maxs >= volume.mins).all()


def _v46_map(tmp_path, lumps, shader=''):
    """A version 46 map in a content tree, with an optional shader script."""
    maps = tmp_path / 'maps'
    maps.mkdir(parents=True, exist_ok=True)
    path = maps / 'liquid.bsp'
    path.write_bytes(bspbuilder.build(46, lumps))
    if shader:
        scripts = tmp_path / 'scripts'
        scripts.mkdir(exist_ok=True)
        (scripts / 'liquids.shader').write_text(shader)
    return maploader.load(str(path))


WATER_SHADER = """
textures/liquids/water
{
    surfaceparm water
    {
        map textures/liquids/water.tga
    }
}
"""


def test_a_map_whose_family_has_no_leaf_contents_reads_its_brushes(tmp_path):
    """`SPEC-BSP46 §4.4.1`: a version 46 leaf carries no contents word, so the
    liquid is found through the brushes the leaf holds and the material script
    that says what their texture is (`SPEC-Q3SHADER §2.2`)."""
    loaded = _v46_map(tmp_path, bspbuilder.v46_water(), WATER_SHADER)
    assert len(liquids.from_map(loaded)) == 1


def test_a_version_46_brush_whose_texture_is_not_a_liquid_is_no_volume(tmp_path):
    loaded = _v46_map(tmp_path, bspbuilder.v46_water())    # no script: not water
    assert not liquids.from_map(loaded)


def test_a_version_46_map_with_no_brushes_has_no_volumes(tmp_path):
    loaded = _v46_map(tmp_path, bspbuilder.v46_quad(), WATER_SHADER)
    assert not liquids.from_map(loaded)


def test_a_version_46_map_read_with_no_material_scripts_has_no_liquids(tmp_path):
    """A brush names a texture and only a script says whether that texture is
    water, so nothing is liquid without one."""
    loaded = _v46_map(tmp_path, bspbuilder.v46_water(), WATER_SHADER)
    loaded.style_for = None
    assert not liquids.from_map(loaded)


def test_a_leaf_holding_no_brushes_is_skipped(tmp_path):
    """Most leaves hold none, and indexing a zero-length run would read the
    brush belonging to the next leaf."""
    lumps = bspbuilder.v46_water()
    lumps['leafs'] = (bspbuilder.v46_leaf(cluster=0)          # no brushes
                      + bspbuilder.v46_leaf(cluster=1, mins=(0, 0, -32),
                                            maxs=(64, 64, 0),
                                            leafbrush=0, n_leafbrushes=1))
    loaded = _v46_map(tmp_path, lumps, WATER_SHADER)
    assert len(liquids.from_map(loaded)) == 1


def test_a_version_38_map_with_no_leaves_has_no_liquids(tmp_path):
    lumps = bspbuilder.v38_quad(size=512.0)
    lumps['leafs'] = b''
    path = tmp_path / 'noleaves.bsp'
    path.write_bytes(bspbuilder.build(38, lumps))
    assert not liquids.from_map(maploader.load(str(path)))
