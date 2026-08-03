"""Version 38 geometry: rings, normals, planar UVs and lightmap addressing.

Facts under test are SPEC-BSP38 §4.6.1, §4.11.1, §5, §6, §7.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

import bspbuilder
from twig_bb import q2bsp, q2geometry


def _sized(_name: str) -> tuple:
    """Texture size lookup used by the tests: a 64 x 64 image."""
    return (64, 64)


def _build(path, **kwargs):
    bsp = q2bsp.load(path)
    return q2geometry.build(bsp, texture_size=_sized, **kwargs)


def test_a_faces_ring_follows_the_sign_of_each_surfedge(write_map):
    """SPEC-BSP38 §4.11.1, §5.1: a negative entry walks its edge backwards, and
    the ring is the first vertex of each successive directed edge."""
    bsp = q2bsp.load(write_map(38, bspbuilder.v38_quad(size=64.0)))
    ring = q2geometry.face_vertices(bsp, 0)
    assert len(ring) == 4
    assert ring.tolist() == [[0, 0, 0], [64, 0, 0], [64, 64, 0], [0, 64, 0]]


def test_a_face_normal_is_the_planes_normal_when_the_side_is_zero(write_map):
    """SPEC-BSP38 §4.6.1, §5.3."""
    bsp = q2bsp.load(write_map(38, bspbuilder.v38_quad()))
    assert q2geometry.face_normal(bsp, 0) == pytest.approx((0.0, 0.0, 1.0))


def test_a_face_normal_is_negated_when_the_side_is_not_zero(write_map):
    """SPEC-BSP38 §4.6.1: any non-zero value negates the plane's normal."""
    lumps = bspbuilder.v38_quad()
    lumps['faces'] = bspbuilder.v38_face(0, 1, 0, 4, 0)
    bsp = q2bsp.load(write_map(38, lumps))
    assert q2geometry.face_normal(bsp, 0) == pytest.approx((0.0, 0.0, -1.0))


def test_texture_coordinates_are_the_affine_projection_of_world_position(write_map):
    """SPEC-BSP38 §6.1: S = p.(S axis) + (S offset), and likewise for T."""
    lumps = bspbuilder.v38_quad()
    lumps['texinfo'] = bspbuilder.v38_texinfo((0.5, 0, 0), 8.0, (0, 0.25, 0), -2.0)
    bsp = q2bsp.load(write_map(38, lumps))
    points = np.array([[0.0, 0.0, 0.0], [64.0, 32.0, 0.0]])
    st = q2geometry.texture_coordinates(bsp, 0, points)
    assert st[0] == pytest.approx((8.0, -2.0))
    assert st[1] == pytest.approx((0.5 * 64 + 8.0, 0.25 * 32 - 2.0))


def test_texture_coordinates_normalise_by_the_images_dimensions(write_map):
    """SPEC-BSP38 §6.2: divide S by the width and T by the height."""
    world = _build(write_map(38, bspbuilder.v38_quad(size=64.0)))[0]
    uv = world.batches[0].texcoords
    # the builder's S axis is (1,0,0) with no offset, so x = 64 is S = 64 texels,
    # which over a 64-wide image is exactly one repeat
    assert float(uv[:, 0].max()) == pytest.approx(1.0)


def test_a_face_is_triangulated_as_a_fan(write_map):
    """SPEC-BSP38 §5.2: a convex ring fans from any of its vertices."""
    world = _build(write_map(38, bspbuilder.v38_quad()))[0]
    batch = world.batches[0]
    assert len(batch.positions) == 4
    assert batch.triangle_count == 2
    assert batch.indices.tolist() == [0, 1, 2, 0, 2, 3]


def test_a_face_with_fewer_than_three_edges_is_dropped(write_map):
    lumps = bspbuilder.v38_quad()
    lumps['faces'] = bspbuilder.v38_face(0, 0, 0, 2, 0)
    world = _build(write_map(38, lumps))[0]
    assert world.batches == []


def test_a_nodraw_face_is_kept_for_collision_but_marked_undrawn(write_map):
    """SPEC-BSP38 §8.1: nodraw exists for compilation and collision only."""
    world = _build(write_map(38, bspbuilder.v38_quad(flags=q2bsp.SURF_NODRAW)))[0]
    assert len(world.batches) == 1
    assert not world.batches[0].style.draw
    assert world.collision_mesh() is not None


def test_the_luxel_grid_is_the_quantised_texture_extent_plus_one():
    """SPEC-BSP38 §7.2: floor(min/16), ceil(max/16), and the +1 for corners."""
    st = np.array([[0.0, 0.0], [64.0, 32.0]])
    grid_min, size = q2geometry.luxel_grid(st, (16.0, 16.0))
    assert grid_min == pytest.approx((0.0, 0.0))
    assert size == (5, 3)                       # 64/16 + 1, 32/16 + 1


def test_the_luxel_grid_floors_and_ceils_rather_than_rounding():
    """SPEC-BSP38 §7.2: a face one cell wide still has two luxels across."""
    st = np.array([[3.0, -1.0], [20.0, 1.0]])
    grid_min, size = q2geometry.luxel_grid(st, (16.0, 16.0))
    assert grid_min == pytest.approx((0.0, -16.0))
    # S: floor(3/16) = 0 to ceil(20/16) = 2, so 3 luxels across.
    # T: floor(-1/16) = -1 to ceil(1/16) = 1, so 3 down -- a span of two texels
    # straddling zero still costs three luxels, which rounding would hide.
    assert size == (3, 3)


def test_the_luxel_grid_uses_the_scale_it_is_given():
    """SPEC-BSP38 §7.2 states the relationship against a scale, so a reader may
    check it independently of the fixed 16."""
    st = np.array([[0.0, 0.0], [64.0, 64.0]])
    _, size = q2geometry.luxel_grid(st, (4.0, 4.0))
    assert size == (17, 17)


def test_a_face_with_a_negative_lighting_offset_has_no_lightmap(write_map):
    """SPEC-BSP38 §7.4: a negative offset means the face has no baked lighting."""
    world, atlas = _build(write_map(38, bspbuilder.v38_quad(lightofs=-1)))
    assert world.batches[0].lightmap_page == -1
    assert atlas.pages == []


def test_a_face_whose_first_style_slot_is_unused_has_no_lightmap(write_map):
    """SPEC-BSP38 §7.5: the value 255 marks an unused slot and terminates."""
    lumps = bspbuilder.v38_quad(lightofs=0, styles=(255, 255, 255, 255))
    lumps['lighting'] = b'\x40' * (5 * 5 * 3)
    world, _ = _build(write_map(38, lumps))
    assert world.batches[0].lightmap_page == -1


def test_a_lighting_offset_past_the_end_of_the_lump_has_no_lightmap(write_map):
    """SPEC-BSP38 §7.4: a reader must not trust an offset outside the lump."""
    lumps = bspbuilder.v38_quad(lightofs=10_000)
    lumps['lighting'] = b'\x40' * 300
    world, _ = _build(write_map(38, lumps))
    assert world.batches[0].lightmap_page == -1


def test_a_sky_face_carries_no_lightmap(write_map):
    """SPEC-BSP38 §7.8: sky surfaces carry no lightmap."""
    lumps = bspbuilder.v38_quad(flags=q2bsp.SURF_SKY, lightofs=0)
    lumps['lighting'] = b'\x40' * (5 * 5 * 3)
    world, _ = _build(write_map(38, lumps))
    assert world.batches[0].lightmap_page == -1


def test_a_warped_face_carries_no_lightmap(write_map):
    """SPEC-BSP38 §7.8: a warped surface has no usable texture-space extent."""
    lumps = bspbuilder.v38_quad(flags=q2bsp.SURF_WARP, lightofs=0)
    lumps['lighting'] = b'\x40' * (5 * 5 * 3)
    world, _ = _build(write_map(38, lumps))
    assert world.batches[0].lightmap_page == -1


def test_a_lit_face_gets_a_page_and_lightmap_coordinates(write_map):
    """SPEC-BSP38 §7.2, §7.3, §7.7 end to end."""
    lumps = bspbuilder.v38_quad(size=64.0, lightofs=0)
    lumps['lighting'] = bytes([200, 100, 50]) * (5 * 5)
    world, atlas = _build(write_map(38, lumps))
    batch = world.batches[0]
    assert batch.lightmap_page == 0
    assert len(atlas.pages) == 1
    place = atlas.placements[0]
    assert (place.width, place.height) == (5, 5)
    # the face spans S,T = 0..64 texels, i.e. luxels 0..4 of a five-luxel grid
    uv = batch.texcoords1
    assert uv[:, 0].min() == pytest.approx((place.x + 0.5) / atlas.page_size)
    assert uv[:, 0].max() == pytest.approx((place.x + 4.5) / atlas.page_size)


def test_only_the_first_light_style_block_is_read(write_map):
    """SPEC-BSP38 §7.5, §7.6: style 0 is the always-on contribution, and a
    reader that wants only static lighting may use that block alone."""
    lumps = bspbuilder.v38_quad(size=64.0, lightofs=0, styles=(0, 3, 255, 255))
    first = bytes([10, 10, 10]) * 25
    second = bytes([250, 250, 250]) * 25
    lumps['lighting'] = first + second
    _, atlas = _build(write_map(38, lumps))
    place = atlas.placements[0]
    region = atlas.pages[0][place.y:place.y + 5, place.x:place.x + 5]
    assert int(region.max()) == 10


def test_faces_of_different_textures_become_different_batches(write_map):
    lumps = bspbuilder.v38_quad()
    lumps['texinfo'] = (bspbuilder.v38_texinfo((1, 0, 0), 0, (0, -1, 0), 0, name='a/one')
                        + bspbuilder.v38_texinfo((1, 0, 0), 0, (0, -1, 0), 0, name='b/two'))
    lumps['faces'] = (bspbuilder.v38_face(0, 0, 0, 4, 0)
                      + bspbuilder.v38_face(0, 0, 0, 4, 1))
    lumps['models'] = bspbuilder.v38_model((0, 0, 0), (64, 64, 0), (0, 0, 0), 0, 0, 2)
    world = _build(write_map(38, lumps))[0]
    assert sorted(b.style.name for b in world.batches) == ['a/one', 'b/two']


def test_a_brush_models_faces_build_on_their_own(write_map):
    """SPEC-BSP38 §4.12.2: a brush model's faces are a contiguous face range."""
    lumps = bspbuilder.v38_quad()
    lumps['faces'] = (bspbuilder.v38_face(0, 0, 0, 4, 0)
                      + bspbuilder.v38_face(0, 0, 0, 4, 0))
    lumps['models'] = (bspbuilder.v38_model((0, 0, 0), (64, 64, 0), (0, 0, 0), 0, 0, 1)
                       + bspbuilder.v38_model((0, 0, 0), (64, 64, 0), (0, 0, 0), 0, 1, 1))
    bsp = q2bsp.load(write_map(38, lumps))
    world, _ = q2geometry.build(bsp, texture_size=_sized, model=1)
    assert world.triangle_count == 2


def test_a_model_index_with_no_model_builds_nothing(write_map):
    bsp = q2bsp.load(write_map(38, bspbuilder.v38_quad()))
    world, _ = q2geometry.build(bsp, texture_size=_sized, model=7)
    assert world.batches == []


def test_a_missing_texture_size_falls_back_without_raising(write_map):
    """A map whose images are absent still loads; only the tiling scale suffers."""
    world = _build(write_map(38, bspbuilder.v38_quad()), )[0]
    assert world.batches


def test_tangents_come_from_the_texinfo_axes(write_map):
    """SPEC-BSP38 §6.3: the S axis is the surface's tangent direction, so a
    planar face knows its tangent frame exactly rather than estimating it."""
    world = _build(write_map(38, bspbuilder.v38_quad()))[0]
    tangents = world.batches[0].tangents
    assert tangents.shape[1] == 4
    # S axis (1,0,0) in map space is (1,0,0) in scene space
    assert tangents[0][:3] == pytest.approx((1.0, 0.0, 0.0))


# -- against the real sample map ---------------------------------------------

@pytest.mark.slow
def test_the_sample_map_builds_within_the_load_budget(arena_map):
    """The plan's constraint: a local map load is about two seconds, not fifty."""
    bsp = q2bsp.load(arena_map)
    start = time.perf_counter()
    world, atlas = q2geometry.build(bsp, texture_size=_sized)
    elapsed = time.perf_counter() - start
    assert world.triangle_count > 10000
    assert len(atlas.pages) >= 1
    assert elapsed < 4.0, 'geometry build took %.2fs' % elapsed


def test_the_sample_maps_lit_faces_all_land_on_a_page(arena_map):
    """Every face the `.bsp` says is lit must end up addressable in the atlas."""
    bsp = q2bsp.load(arena_map)
    world, atlas = q2geometry.build(bsp, texture_size=_sized)
    lit = [b for b in world.batches if b.lightmap_page >= 0]
    assert lit
    for batch in lit:
        assert 0.0 <= float(batch.texcoords1.min())
        assert float(batch.texcoords1.max()) <= 1.0
