"""Version 46 geometry: meshverts, Bezier patches and lightmap addressing.

Facts under test are SPEC-BSP46 §4.9, §4.10, §4.12, §4.13 and §6.3–§6.6.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

import bspbuilder
from twitchoglc import q3bsp, q3geometry
from twitchoglc.surfaces import SurfaceStyle


def _style(name: str) -> SurfaceStyle:
    return SurfaceStyle(name=name)


def _build(path, **kwargs):
    return q3geometry.build(q3bsp.load(path), style_for=_style, **kwargs)


# -- Bezier patch evaluation --------------------------------------------------

def test_the_quadratic_basis_weights_sum_to_one():
    """SPEC-BSP46 §6.5: b0 = (1-u)^2, b1 = 2u(1-u), b2 = u^2."""
    basis = q3geometry.bezier_basis(5)
    assert basis.shape == (5, 3)
    assert basis.sum(axis=1) == pytest.approx(np.ones(5))
    assert basis[0] == pytest.approx((1.0, 0.0, 0.0))
    assert basis[-1] == pytest.approx((0.0, 0.0, 1.0))
    assert basis[2] == pytest.approx((0.25, 0.5, 0.25))


def test_a_patch_interpolates_its_corner_control_points_exactly():
    """SPEC-BSP46 §6.5: at (0,0) and (1,1) the surface meets the corner points."""
    control = np.zeros((3, 3, 3), 'f')
    for i in range(3):
        for j in range(3):
            control[i, j] = (j, i, 0)
    grid, _ = q3geometry.tessellate_patch(control, subdivisions=4)
    assert grid[0, 0] == pytest.approx((0.0, 0.0, 0.0))
    assert grid[-1, -1] == pytest.approx((2.0, 2.0, 0.0))


def test_a_patch_pulls_towards_but_does_not_reach_its_middle_control_point():
    """The defining property of a Bezier surface: the interior is approximated."""
    control = np.zeros((3, 3, 3), 'f')
    for i in range(3):
        for j in range(3):
            control[i, j] = (j, i, 0)
    control[1, 1, 2] = 4.0                      # lift the middle control point
    grid, _ = q3geometry.tessellate_patch(control, subdivisions=4)
    centre = grid[grid.shape[0] // 2, grid.shape[1] // 2]
    assert 0.0 < float(centre[2]) < 4.0


def test_a_patch_grid_has_one_sample_per_subdivision_plus_a_shared_edge():
    """SPEC-BSP46 §6.4: sub-patches share their edge control points."""
    control = np.zeros((3, 5, 3), 'f')          # one patch tall, two wide
    for i in range(3):
        for j in range(5):
            control[i, j] = (j, i, 0)
    grid, indices = q3geometry.tessellate_patch(control, subdivisions=4)
    assert grid.shape[:2] == (5, 9)             # 1*4+1 rows, 2*4+1 columns
    assert len(indices) == (5 - 1) * (9 - 1) * 6


def test_every_vertex_attribute_is_interpolated_over_the_same_domain():
    """SPEC-BSP46 §6.5: positions, normals and both UV sets share the weights."""
    control = np.zeros((3, 3, 10), 'f')
    for i in range(3):
        for j in range(3):
            control[i, j, :3] = (j, i, 0)
            control[i, j, 3:6] = (0, 0, 1)
            control[i, j, 6:8] = (j / 2.0, i / 2.0)
            control[i, j, 8:10] = (j / 4.0, i / 4.0)
    grid, _ = q3geometry.tessellate_patch(control, subdivisions=4)
    assert grid[-1, -1, 6:8] == pytest.approx((1.0, 1.0))
    assert grid[-1, -1, 8:10] == pytest.approx((0.5, 0.5))
    assert grid[0, 0, 3:6] == pytest.approx((0.0, 0.0, 1.0))


def test_a_control_grid_smaller_than_one_patch_yields_nothing():
    """SPEC-BSP46 §6.3: both dimensions are odd and at least 3."""
    grid, indices = q3geometry.tessellate_patch(np.zeros((1, 3, 3), 'f'), 4)
    assert len(indices) == 0
    assert grid.size == 0


# -- whole-map building -------------------------------------------------------

def test_a_polygon_face_is_drawn_from_its_meshverts(write_map):
    """SPEC-BSP46 §4.10.1, §4.12.1: meshverts offset from the face's first vertex."""
    world, _ = _build(write_map(46, bspbuilder.v46_quad()))
    assert len(world.batches) == 1
    batch = world.batches[0]
    assert len(batch.positions) == 4
    assert batch.triangle_count == 2


def test_meshverts_are_relative_to_the_faces_own_first_vertex(write_map):
    """SPEC-BSP46 §4.10.1: a shared meshvert run addresses each face's own block."""
    lumps = bspbuilder.v46_quad()
    corners = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    far = [(10, 0, 0), (11, 0, 0), (11, 1, 0), (10, 1, 0)]
    lumps['vertexes'] = b''.join(bspbuilder.v46_vertex(c) for c in corners + far)
    lumps['faces'] = (bspbuilder.v46_face(0, 1, 0, 4, 0, 6)
                      + bspbuilder.v46_face(0, 1, 4, 4, 0, 6))
    lumps['models'] = bspbuilder.v46_model((0, 0, 0), (11, 1, 0), 0, 2)
    world, _ = _build(write_map(46, lumps))
    xs = world.batches[0].positions[:, 0]
    assert float(xs.max()) > 10 * 0.0254 * 0.9      # the second face's block was used


def test_a_mesh_face_is_drawn_like_a_polygon(write_map):
    """SPEC-BSP46 §4.12.1: types 1 and 3 are drawn identically."""
    lumps = bspbuilder.v46_quad()
    lumps['faces'] = bspbuilder.v46_face(0, q3bsp.FACE_MESH, 0, 4, 0, 6)
    world, _ = _build(write_map(46, lumps))
    assert world.batches[0].triangle_count == 2


def test_a_billboard_face_is_skipped(write_map):
    """SPEC-BSP46 §4.12.1: type 4 carries no polygon geometry."""
    lumps = bspbuilder.v46_quad()
    lumps['faces'] = bspbuilder.v46_face(0, q3bsp.FACE_BILLBOARD, 0, 4, 0, 6)
    world, _ = _build(write_map(46, lumps))
    assert world.batches == []


def test_a_face_with_an_unknown_type_is_skipped(write_map):
    lumps = bspbuilder.v46_quad()
    lumps['faces'] = bspbuilder.v46_face(0, 99, 0, 4, 0, 6)
    world, _ = _build(write_map(46, lumps))
    assert world.batches == []


def test_vertex_texture_coordinates_are_used_as_they_are(write_map):
    """SPEC-BSP46 §4.9.1, §4.9.2: v46 stores normalised UVs per vertex."""
    world, _ = _build(write_map(46, bspbuilder.v46_quad()))
    uv = world.batches[0].texcoords
    assert uv.min() == pytest.approx(0.0)
    assert uv.max() == pytest.approx(1.0)


def test_a_face_with_no_lightmap_index_gets_no_page(write_map):
    """SPEC-BSP46 §4.12.2: -1 means the face has no baked lighting."""
    world, atlas = _build(write_map(46, bspbuilder.v46_quad(lm_index=-1)))
    assert world.batches[0].lightmap_page == -1
    assert atlas.pages == []


def test_a_lightmap_index_past_the_end_of_the_lump_gets_no_page(write_map):
    """SPEC-BSP46 §4.12.2: an index outside the lump means no lighting."""
    lumps = bspbuilder.v46_quad(lm_index=5,
                                lightmaps=bspbuilder.v46_lightmap(40))
    world, _ = _build(write_map(46, lumps))
    assert world.batches[0].lightmap_page == -1


def test_a_lit_face_addresses_its_image_through_the_atlas(write_map):
    """SPEC-BSP46 §4.9.3, §4.13.1: the vertex UV spans one 128 x 128 image."""
    lumps = bspbuilder.v46_quad(lm_index=0, lightmaps=bspbuilder.v46_lightmap(90))
    world, atlas = _build(write_map(46, lumps))
    batch = world.batches[0]
    assert batch.lightmap_page == 0
    place = atlas.placements[0]
    assert (place.width, place.height) == (128, 128)
    uv = batch.texcoords1
    # the quad's lightmap UVs run 0..0.5, i.e. half of the image
    assert uv[:, 0].min() == pytest.approx(place.x / atlas.page_size)
    assert uv[:, 0].max() == pytest.approx((place.x + 64) / atlas.page_size)


def test_only_the_lightmaps_a_map_uses_are_packed(write_map):
    """A map may ship images no face references; packing them wastes pages."""
    lumps = bspbuilder.v46_quad(lm_index=1,
                                lightmaps=bspbuilder.v46_lightmap(1)
                                + bspbuilder.v46_lightmap(2))
    _, atlas = _build(write_map(46, lumps))
    used = [p for p in atlas.placements if p is not None]
    assert len(used) == 1
    assert int(atlas.pages[0][used[0].y, used[0].x, 0]) == 2


def test_a_patch_face_is_tessellated_into_triangles(write_map):
    """SPEC-BSP46 §6.3, §6.4: a 3 x 3 control grid is one biquadratic patch."""
    control = []
    for i in range(3):
        for j in range(3):
            control.append(bspbuilder.v46_vertex(
                (j * 32, i * 32, 0 if (i + j) % 2 == 0 else 16),
                (j / 2.0, i / 2.0)))
    lumps = bspbuilder.v46_quad()
    lumps['vertexes'] = b''.join(control)
    lumps['faces'] = bspbuilder.v46_face(0, q3bsp.FACE_PATCH, 0, 9, 0, 0, size=(3, 3))
    world, _ = _build(write_map(46, lumps), subdivisions=4)
    batch = world.batches[0]
    assert len(batch.positions) == 25           # (4+1) x (4+1) samples
    assert batch.triangle_count == 32           # 4 x 4 quads x 2


def test_a_patch_whose_grid_does_not_fit_its_vertices_is_skipped(write_map):
    """SPEC-BSP46 §12-style validation: the grid must lie inside the lump."""
    lumps = bspbuilder.v46_quad()
    lumps['faces'] = bspbuilder.v46_face(0, q3bsp.FACE_PATCH, 0, 9, 0, 0, size=(3, 3))
    world, _ = _build(write_map(46, lumps))     # only 4 vertices exist
    assert world.batches == []


def test_a_model_index_with_no_model_builds_nothing(write_map):
    bsp = q3bsp.load(write_map(46, bspbuilder.v46_quad()))
    world, _ = q3geometry.build(bsp, style_for=_style, model=7)
    assert world.batches == []


def test_the_style_callback_decides_how_a_surface_looks(write_map):
    """SPEC-BSP46 §6.2: v46 surface behaviour comes from the material script,
    not from the flags word, so the caller supplies the style."""
    def style_for(name):
        return SurfaceStyle(name=name, draw=False, solid=False)

    bsp = q3bsp.load(write_map(46, bspbuilder.v46_quad()))
    world, _ = q3geometry.build(bsp, style_for=style_for)
    assert not world.batches[0].style.draw
    assert world.collision_mesh() is None


# -- against a real sample map ------------------------------------------------

@pytest.mark.slow
def test_the_sample_map_builds_within_the_load_budget(quake3_map):
    """The plan's constraint: a local map load is about two seconds."""
    bsp = q3bsp.load(quake3_map)
    start = time.perf_counter()
    world, atlas = q3geometry.build(bsp, style_for=_style)
    elapsed = time.perf_counter() - start
    assert world.triangle_count > 5000
    assert len(atlas.pages) >= 1
    assert elapsed < 4.0, 'geometry build took %.2fs' % elapsed


def test_the_sample_maps_lightmap_coordinates_stay_inside_the_atlas(quake3_map):
    bsp = q3bsp.load(quake3_map)
    world, _ = q3geometry.build(bsp, style_for=_style)
    lit = [b for b in world.batches if b.lightmap_page >= 0]
    assert lit
    for batch in lit:
        assert float(batch.texcoords1.min()) >= 0.0
        assert float(batch.texcoords1.max()) <= 1.0


def test_the_sample_maps_patches_produce_geometry(quake3_map):
    """SPEC-BSP46 §6.3–§6.5 against a real map's curved surfaces."""
    bsp = q3bsp.load(quake3_map)
    patches = int((bsp.faces['type'] == q3bsp.FACE_PATCH).sum())
    assert patches > 0
    with_patches, _ = q3geometry.build(bsp, style_for=_style)
    without, _ = q3geometry.build(bsp, style_for=_style, subdivisions=1)
    assert with_patches.triangle_count > without.triangle_count


# -- malformed maps -----------------------------------------------------------

def test_a_face_naming_a_texture_that_does_not_exist_still_builds(write_map):
    """SPEC-BSP46 §12-style validation: an index out of range is not a crash."""
    lumps = bspbuilder.v46_quad()
    lumps['faces'] = bspbuilder.v46_face(9, 1, 0, 4, 0, 6)
    world, _ = _build(write_map(46, lumps))
    assert world.batches[0].style.name == ''


def test_a_face_whose_vertex_block_runs_past_the_lump_is_skipped(write_map):
    lumps = bspbuilder.v46_quad()
    lumps['faces'] = bspbuilder.v46_face(0, 1, 0, 99, 0, 6)
    assert _build(write_map(46, lumps))[0].batches == []


def test_a_face_with_no_vertices_or_no_meshverts_is_skipped(write_map):
    for face in (bspbuilder.v46_face(0, 1, 0, 0, 0, 6),
                 bspbuilder.v46_face(0, 1, 0, 4, 0, 0)):
        lumps = bspbuilder.v46_quad()
        lumps['faces'] = face
        assert _build(write_map(46, lumps))[0].batches == []


def test_a_face_whose_meshverts_run_past_the_lump_is_skipped(write_map):
    lumps = bspbuilder.v46_quad()
    lumps['faces'] = bspbuilder.v46_face(0, 1, 0, 4, 0, 99)
    assert _build(write_map(46, lumps))[0].batches == []


def test_a_meshvert_outside_the_faces_own_block_is_skipped(write_map):
    """SPEC-BSP46 §4.10.1: a meshvert addresses the face's own vertices."""
    lumps = bspbuilder.v46_quad()
    lumps['meshverts'] = b''.join(bspbuilder.v46_meshvert(i) for i in (0, 1, 9,
                                                                       0, 2, 3))
    assert _build(write_map(46, lumps))[0].batches == []


def test_a_patch_with_an_even_grid_dimension_is_skipped(write_map):
    """SPEC-BSP46 §6.3: both dimensions are odd and at least 3."""
    lumps = bspbuilder.v46_quad()
    lumps['faces'] = bspbuilder.v46_face(0, q3bsp.FACE_PATCH, 0, 4, 0, 0,
                                         size=(4, 3))
    assert _build(write_map(46, lumps))[0].batches == []


def test_a_negative_first_vertex_is_skipped(write_map):
    lumps = bspbuilder.v46_quad()
    lumps['faces'] = bspbuilder.v46_face(0, 1, -4, 4, 0, 6)
    assert _build(write_map(46, lumps))[0].batches == []
