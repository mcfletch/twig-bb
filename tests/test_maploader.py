"""Loading a map: sniffing the version, reading it, and what a load produces."""

from __future__ import annotations

import time

import numpy as np
import pytest

import bspbuilder
from twig_bb import maploader
from twig_bb.bspfile import MalformedBSP


def _q3(tmp_path, lumps=None, name='q3test.bsp'):
    maps = tmp_path / 'maps'
    maps.mkdir(parents=True, exist_ok=True)
    path = maps / name
    path.write_bytes(bspbuilder.build(46, lumps or bspbuilder.v46_quad()))
    return str(path)


def test_a_version_46_map_dispatches_to_the_quake3_reader(tmp_path):
    loaded = maploader.load(_q3(tmp_path))
    assert loaded.family == 'quake3'
    assert loaded.version == 46


def test_an_unknown_version_is_refused_with_a_useful_message(tmp_path):
    path = tmp_path / 'maps'
    path.mkdir()
    target = path / 'weird.bsp'
    target.write_bytes(b'IBSP' + (29).to_bytes(4, 'little') + b'\x00' * 200)
    with pytest.raises(MalformedBSP) as error:
        maploader.load(str(target))
    assert '29' in str(error.value)


def test_a_file_that_is_not_a_map_is_refused(tmp_path):
    target = tmp_path / 'not.bsp'
    target.write_bytes(b'nope' + b'\x00' * 200)
    with pytest.raises(MalformedBSP):
        maploader.load(str(target))


def test_a_pk3_passed_by_mistake_says_so(tmp_path):
    """A common mistake worth naming rather than reporting as a bad magic."""
    target = tmp_path / 'map.bsp'
    target.write_bytes(b'PK\x03\x04' + b'\x00' * 200)
    with pytest.raises(MalformedBSP) as error:
        maploader.load(str(target))
    assert 'pk3' in str(error.value).lower()


def test_the_map_name_is_the_file_stem(tmp_path):
    """The name the material scripts are looked up under (SPEC-Q3SHADER §1.3)."""
    assert maploader.load(_q3(tmp_path, name='q3dm1.bsp')).name == 'q3dm1'


def test_the_content_root_is_the_directory_above_maps(tmp_path):
    """A map lives at `maps/<name>.bsp` inside its content tree."""
    loaded = maploader.load(_q3(tmp_path))
    assert str(tmp_path) in loaded.roots


def test_a_load_produces_geometry_an_atlas_and_a_scene(tmp_path):
    loaded = maploader.load(_q3(tmp_path))
    assert loaded.world.triangle_count == 2
    assert loaded.atlas is not None
    assert len(loaded.scene().children) == 1


def test_a_load_produces_a_collision_mesh(tmp_path):
    points, triangles = maploader.load(_q3(tmp_path)).collision_mesh()
    assert len(points) == 4
    assert triangles.shape == (2, 3)


def test_brush_model_bounds_are_available_for_push_volumes(tmp_path):
    """SPEC-BSP46 §4.6, §5.1: an entity's `*N` names a models-lump entry."""
    lumps = bspbuilder.v46_quad()
    lumps['models'] = (bspbuilder.v46_model((0, 0, 0), (64, 64, 0), 0, 1)
                       + bspbuilder.v46_model((1, 2, 3), (5, 6, 7), 0, 1))
    loaded = maploader.load(_q3(tmp_path, lumps))
    low, high = loaded.model_bounds(1)
    assert tuple(low) == pytest.approx((1.0, 2.0, 3.0))
    assert tuple(high) == pytest.approx((5.0, 6.0, 7.0))
    assert loaded.model_bounds(9) is None
    assert loaded.model_bounds(None) is None


def test_spawn_points_are_found_by_their_classnames(tmp_path):
    """Mapping vocabulary, not a format fact: the classnames level editors use."""
    lumps = bspbuilder.v46_quad()
    lumps['entities'] = bspbuilder.entity_text([
        {'classname': 'worldspawn'},
        {'classname': 'info_player_deathmatch', 'origin': '-1072 154 -40',
         'angle': '90'},
        {'classname': 'light', 'origin': '0 0 0'},
    ])
    spawns = maploader.load(_q3(tmp_path, lumps)).spawn_points()
    assert len(spawns) == 1
    # +Z up in map units becomes +Y up in metres
    assert spawns[0].position[1] == pytest.approx(-40 * 0.0254)


def test_a_map_with_no_spawn_points_offers_none(tmp_path):
    assert maploader.load(_q3(tmp_path)).spawn_points() == []


def test_the_map_reports_its_own_gravity(tmp_path):
    """SPEC-TRIGGER-PUSH §8.2."""
    lumps = bspbuilder.v46_quad()
    lumps['entities'] = bspbuilder.entity_text([
        {'classname': 'worldspawn', 'gravity': '600'}])
    assert maploader.load(_q3(tmp_path, lumps)).gravity == pytest.approx(600.0)


def test_push_volumes_come_from_the_loaded_map(tmp_path):
    """SPEC-TRIGGER-PUSH §5.1: the volume is the brush model's bounds."""
    lumps = bspbuilder.v46_quad()
    lumps['entities'] = bspbuilder.entity_text([
        {'classname': 'worldspawn'},
        {'classname': 'trigger_push', 'model': '*1', 'angle': '-1', 'speed': '100'}])
    lumps['models'] = (bspbuilder.v46_model((0, 0, 0), (64, 64, 0), 0, 1)
                       + bspbuilder.v46_model((0, 0, 0), (128, 128, 32), 0, 0))
    volumes = maploader.load(_q3(tmp_path, lumps)).push_volumes()
    assert len(volumes) == 1
    assert volumes[0].velocity[2] > 0


def test_the_lightmap_strength_is_carried_through_to_the_materials(tmp_path):
    """SPEC-BSP46 §4.13: the baked lightmap is scaled at render time."""
    lumps = bspbuilder.v46_quad(lm_index=0, lightmaps=bspbuilder.v46_lightmap())
    loaded = maploader.load(_q3(tmp_path, lumps), lightmap_strength=4.0)
    material = loaded.scene().children[0].appearance.material
    assert material.lightmapStrength == pytest.approx(4.0)


def test_a_quake3_maps_shaders_decide_its_surface_styles(tmp_path):
    """SPEC-BSP46 §6.2: v46 surface behaviour comes from the material scripts."""
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (scripts / 'test.shader').write_text(
        'textures/base/wall\n{\n surfaceparm nodraw\n}\n')
    loaded = maploader.load(_q3(tmp_path))
    assert loaded.scene().children == []        # the one surface is nodraw


def test_loading_by_name_reports_which_file_was_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        maploader.load(str(tmp_path / 'maps' / 'absent.bsp'))


def test_a_map_reports_the_textures_it_could_not_find(tmp_path):
    """A grey map is otherwise indistinguishable from a broken one."""
    loaded = maploader.load(_q3(tmp_path))
    assert loaded.missing_textures() == ['textures/base/wall']
    assert loaded.texture_names() == ['textures/base/wall']


def test_a_texture_that_is_present_is_not_reported_missing(tmp_path):
    from PIL import Image
    directory = tmp_path / 'textures' / 'base'
    directory.mkdir(parents=True)
    Image.new('RGB', (8, 8)).save(str(directory / 'wall.tga'))
    assert maploader.load(_q3(tmp_path)).missing_textures() == []


def test_undrawn_surfaces_are_not_reported_as_missing_textures(tmp_path):
    """A nodraw surface has no texture to find, so naming it would be noise."""
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (scripts / 'test.shader').write_text(
        'textures/base/wall\n{\n surfaceparm nodraw\n}\n')
    assert maploader.load(_q3(tmp_path)).missing_textures() == []


# -- against the real sample map ---------------------------------------------

@pytest.mark.slow
def test_the_quake3_sample_loads_within_the_budget(quake3_map):
    start = time.perf_counter()
    loaded = maploader.load(quake3_map)
    loaded.scene()
    elapsed = time.perf_counter() - start
    assert loaded.family == 'quake3'
    assert loaded.world.triangle_count > 5000
    assert elapsed < 6.0, 'load took %.2fs' % elapsed


def test_the_quake3_sample_finds_its_spawn_points(quake3_map):
    spawns = maploader.load(quake3_map).spawn_points()
    assert spawns
    assert all(np.isfinite(spawn.position).all() for spawn in spawns)


class TestTheCostOfAskingTwice:
    """What a loaded map reports about itself does not change while it is loaded.

    The developer overlay asks every frame — it is a live display, and that is
    what live means — so a question answered by walking every surface and
    resolving every texture name is a millisecond of every frame spent
    recomputing a number that cannot have moved.  A map is immutable once
    loaded, so the answer is worked out once.
    """

    def test_the_missing_textures_are_worked_out_once(self, monkeypatch,
                                                      quake3_map):
        loaded = maploader.load(quake3_map)
        calls = []
        original = loaded.library.resolve
        monkeypatch.setattr(loaded.library, 'resolve',
                            lambda name: (calls.append(name), original(name))[1])
        loaded.missing_textures()
        first = len(calls)
        loaded.missing_textures()
        assert first > 0
        assert len(calls) == first

    def test_it_still_answers_the_same_thing(self, quake3_map):
        loaded = maploader.load(quake3_map)
        assert loaded.missing_textures() == loaded.missing_textures()
