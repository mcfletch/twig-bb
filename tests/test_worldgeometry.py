"""The shared world-geometry container and the map-to-scene axis convention."""

from __future__ import annotations

import numpy as np
import pytest

from twig_bb.surfaces import SurfaceStyle
from twig_bb.worldgeometry import (
    GeometryBuilder, SCENE_SCALE, to_scene_directions, to_scene_points,
)


def _quad(z: float = 0.0):
    """Four corners of an axis-aligned square in map coordinates."""
    positions = np.array([(0, 0, z), (64, 0, z), (64, 64, z), (0, 64, z)], 'f')
    normals = np.tile(np.array([0, 0, 1], 'f'), (4, 1))
    uv = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], 'f')
    indices = np.array([0, 1, 2, 0, 2, 3], np.uint32)
    return positions, normals, uv, indices


def test_a_map_point_becomes_a_y_up_point_in_metres():
    """SPEC-BSP38 §3.1 (+Z up) and §3.2 (about an inch per unit)."""
    scene = to_scene_points(np.array([[10.0, 20.0, 30.0]]))
    assert scene[0] == pytest.approx(
        (10 * SCENE_SCALE, 30 * SCENE_SCALE, -20 * SCENE_SCALE))


def test_the_scale_is_the_specs_inch():
    """SPEC-BSP38 §3.2."""
    assert SCENE_SCALE == pytest.approx(0.0254)


def test_the_conversion_is_a_rotation_so_it_preserves_handedness():
    """A mirror would flip every face's winding; a rotation must not."""
    basis = to_scene_points(np.eye(3) / SCENE_SCALE)
    assert float(np.linalg.det(basis)) == pytest.approx(1.0)


def test_directions_rotate_but_do_not_scale():
    """Normals must stay unit length through the conversion."""
    directions = to_scene_directions(np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0]]))
    assert directions[0] == pytest.approx((0.0, 1.0, 0.0))
    assert directions[1] == pytest.approx((1.0, 0.0, 0.0))
    assert np.linalg.norm(directions, axis=1) == pytest.approx([1.0, 1.0])


def test_a_surface_becomes_a_batch_with_its_style():
    builder = GeometryBuilder()
    style = SurfaceStyle(name='wall')
    positions, normals, uv, indices = _quad()
    builder.add_surface(style, -1, positions, normals, uv, uv, indices)
    world = builder.build()
    assert len(world.batches) == 1
    assert world.batches[0].style == style
    assert len(world.batches[0].positions) == 4
    assert list(world.batches[0].indices) == [0, 1, 2, 0, 2, 3]


def test_surfaces_sharing_a_style_and_lightmap_page_merge_into_one_batch():
    """One draw call per material per lightmap page, not one per face."""
    builder = GeometryBuilder()
    style = SurfaceStyle(name='wall')
    for z in (0.0, 32.0):
        positions, normals, uv, indices = _quad(z)
        builder.add_surface(style, 0, positions, normals, uv, uv, indices)
    world = builder.build()
    assert len(world.batches) == 1
    assert len(world.batches[0].positions) == 8
    # the second surface's indices are rebased onto the merged vertex pool
    assert list(world.batches[0].indices[6:]) == [4, 5, 6, 4, 6, 7]


def test_surfaces_on_different_lightmap_pages_do_not_merge():
    """A batch samples one atlas page, so the page is part of its identity."""
    builder = GeometryBuilder()
    style = SurfaceStyle(name='wall')
    positions, normals, uv, indices = _quad()
    builder.add_surface(style, 0, positions, normals, uv, uv, indices)
    builder.add_surface(style, 1, positions, normals, uv, uv, indices)
    assert len(builder.build().batches) == 2


def test_surfaces_with_different_styles_do_not_merge():
    builder = GeometryBuilder()
    positions, normals, uv, indices = _quad()
    builder.add_surface(SurfaceStyle(name='a'), -1, positions, normals, uv, uv, indices)
    builder.add_surface(SurfaceStyle(name='b'), -1, positions, normals, uv, uv, indices)
    assert len(builder.build().batches) == 2


def test_batch_positions_are_in_scene_space():
    builder = GeometryBuilder()
    positions, normals, uv, indices = _quad()
    builder.add_surface(SurfaceStyle(name='wall'), -1, positions, normals, uv, uv, indices)
    built = builder.build().batches[0]
    assert built.positions[1] == pytest.approx((64 * SCENE_SCALE, 0.0, 0.0))
    assert built.normals[0] == pytest.approx((0.0, 1.0, 0.0))


def test_tangents_are_estimated_when_none_are_supplied():
    """Normal mapping needs a vec4 tangent per vertex."""
    builder = GeometryBuilder()
    positions, normals, uv, indices = _quad()
    builder.add_surface(SurfaceStyle(name='wall'), -1, positions, normals, uv, uv, indices)
    tangents = builder.build().batches[0].tangents
    assert tangents.shape == (4, 4)
    assert np.linalg.norm(tangents[0, :3]) == pytest.approx(1.0, abs=1e-5)


def test_supplied_tangents_are_used_and_rotated_into_scene_space():
    """A planar surface knows its own tangent exactly; estimating would blur it."""
    builder = GeometryBuilder()
    positions, normals, uv, indices = _quad()
    tangents = np.tile(np.array([1, 0, 0, 1], 'f'), (4, 1))
    builder.add_surface(SurfaceStyle(name='wall'), -1, positions, normals, uv, uv,
                        indices, tangents=tangents)
    built = builder.build().batches[0]
    assert built.tangents[0] == pytest.approx((1.0, 0.0, 0.0, 1.0))


def test_the_world_reports_its_bounds_in_scene_space():
    builder = GeometryBuilder()
    positions, normals, uv, indices = _quad()
    builder.add_surface(SurfaceStyle(name='wall'), -1, positions, normals, uv, uv, indices)
    low, high = builder.build().bounds
    assert low == pytest.approx((0.0, 0.0, -64 * SCENE_SCALE))
    assert high == pytest.approx((64 * SCENE_SCALE, 0.0, 0.0))


def test_an_empty_world_has_no_batches_and_zero_bounds():
    world = GeometryBuilder().build()
    assert world.batches == []
    assert world.bounds[0] == pytest.approx((0.0, 0.0, 0.0))
    assert world.triangle_count == 0


def test_a_surface_with_no_triangles_is_dropped():
    builder = GeometryBuilder()
    positions, normals, uv, _ = _quad()
    builder.add_surface(SurfaceStyle(name='wall'), -1, positions, normals, uv, uv,
                        np.zeros((0,), np.uint32))
    assert builder.build().batches == []


def test_the_collision_mesh_merges_the_solid_batches():
    """The character controller walks on one static trimesh."""
    builder = GeometryBuilder()
    positions, normals, uv, indices = _quad()
    builder.add_surface(SurfaceStyle(name='floor'), -1, positions, normals, uv, uv, indices)
    builder.add_surface(SurfaceStyle(name='fx', solid=False), -1,
                        positions + 100, normals, uv, uv, indices)
    points, tris = builder.build().collision_mesh()
    assert len(points) == 4                 # only the solid surface
    assert tris.shape == (2, 3)


def test_a_world_with_nothing_solid_has_no_collision_mesh():
    builder = GeometryBuilder()
    positions, normals, uv, indices = _quad()
    builder.add_surface(SurfaceStyle(name='fx', solid=False), -1,
                        positions, normals, uv, uv, indices)
    assert builder.build().collision_mesh() is None


class TestWhichSurfaceATriangleCameFrom:
    """A hit reports a triangle number; this is what turns it back into a surface."""

    def _two_surfaces(self):
        builder = GeometryBuilder()
        positions, normals, uv, indices = _quad()
        builder.add_surface(SurfaceStyle(name='stone'), -1,
                            positions, normals, uv, uv, indices)
        builder.add_surface(SurfaceStyle(name='metal'), -1,
                            positions + 100, normals, uv, uv, indices)
        return builder.build()

    def test_each_triangle_names_the_surface_it_came_from(self):
        index = self._two_surfaces().collision_surfaces()
        assert [index.style_at(n).name for n in range(4)] == [
            'stone', 'stone', 'metal', 'metal']

    def test_the_index_covers_exactly_the_collision_mesh(self):
        """Two walks of the batch list that can disagree eventually will."""
        world = self._two_surfaces()
        _points, triangles = world.collision_mesh()
        assert len(world.collision_surfaces()) == len(triangles)

    def test_a_triangle_that_is_not_in_the_mesh_has_no_surface(self):
        """None rather than the last one: a wrong material reads as a bug in the effect."""
        index = self._two_surfaces().collision_surfaces()
        assert index.style_at(4) is None
        assert index.style_at(-1) is None

    def test_surfaces_left_out_of_the_collision_mesh_are_left_out_of_the_index(self):
        builder = GeometryBuilder()
        positions, normals, uv, indices = _quad()
        builder.add_surface(SurfaceStyle(name='fx', solid=False), -1,
                            positions, normals, uv, uv, indices)
        builder.add_surface(SurfaceStyle(name='floor'), -1,
                            positions + 100, normals, uv, uv, indices)
        index = builder.build().collision_surfaces()
        assert [index.style_at(n).name for n in range(2)] == ['floor', 'floor']

    def test_a_world_with_nothing_solid_has_an_empty_index(self):
        builder = GeometryBuilder()
        positions, normals, uv, indices = _quad()
        builder.add_surface(SurfaceStyle(name='fx', solid=False), -1,
                            positions, normals, uv, uv, indices)
        index = builder.build().collision_surfaces()
        assert len(index) == 0
        assert index.style_at(0) is None


def test_the_triangle_count_totals_every_batch():
    builder = GeometryBuilder()
    positions, normals, uv, indices = _quad()
    builder.add_surface(SurfaceStyle(name='a'), -1, positions, normals, uv, uv, indices)
    builder.add_surface(SurfaceStyle(name='b'), -1, positions, normals, uv, uv, indices)
    assert builder.build().triangle_count == 4


def test_a_second_uv_set_survives_into_the_batch():
    """The lightmap channel samples the second UV set."""
    builder = GeometryBuilder()
    positions, normals, uv, indices = _quad()
    lightmap_uv = uv * 0.25
    builder.add_surface(SurfaceStyle(name='wall'), 0, positions, normals, uv,
                        lightmap_uv, indices)
    built = builder.build().batches[0]
    assert built.texcoords1[2] == pytest.approx((0.25, 0.25))
    assert built.lightmap_page == 0


def _agrees(indices, positions, normals):
    """Whether every triangle's geometric normal points the same way as its
    surface normal -- the property that decides whether it survives culling."""
    tris = np.asarray(indices).reshape((-1, 3))
    p0 = positions[tris[:, 0]]
    geometric = np.cross(positions[tris[:, 1]] - p0, positions[tris[:, 2]] - p0)
    return bool((np.einsum('ij,ij->i', geometric, normals[tris].sum(axis=1)) > 0).all())


def test_triangles_are_wound_to_agree_with_their_surface_normal():
    """SPEC-BSP38 §5.3: the file's winding is consistent but need not match the
    renderer's, and a reader may reverse it uniformly.  Deriving the sense from
    each face's own outward normal decides it from the data rather than from an
    assumption about either engine."""
    from twig_bb.worldgeometry import orient_triangles
    positions = np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0)], 'f')
    up = np.tile(np.array([0, 0, 1], 'f'), (3, 1))
    for winding in ([0, 1, 2], [0, 2, 1]):
        indices = orient_triangles(np.array(winding, np.uint32), positions, up)
        assert _agrees(indices, positions, up)
        assert sorted(indices.tolist()) == [0, 1, 2]        # same triangle


def test_orientation_is_decided_per_triangle():
    """One reversed triangle among correct ones is fixed on its own."""
    from twig_bb.worldgeometry import orient_triangles
    positions = np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)], 'f')
    up = np.tile(np.array([0, 0, 1], 'f'), (4, 1))
    indices = np.array([0, 1, 2, 1, 2, 3], np.uint32)        # second is reversed
    assert not _agrees(indices, positions, up)
    assert _agrees(orient_triangles(indices, positions, up), positions, up)


def test_a_degenerate_triangle_is_left_alone():
    """A zero-area triangle has no normal to agree or disagree with."""
    from twig_bb.worldgeometry import orient_triangles
    positions = np.array([(0, 0, 0), (1, 0, 0), (2, 0, 0)], 'f')
    up = np.tile(np.array([0, 0, 1], 'f'), (3, 1))
    assert orient_triangles(np.array([0, 1, 2], np.uint32), positions, up).tolist() \
        == [0, 1, 2]


def test_a_liquid_surface_is_left_out_of_the_collision_mesh():
    """Walking across water is what happens when it is collided with as solid;
    the point of marking it is to fall in."""
    positions, normals, uv, indices = _quad()
    builder = GeometryBuilder()
    builder.add_surface(SurfaceStyle(name='floor'), 0,
                        positions, normals, uv, uv, indices)
    builder.add_surface(SurfaceStyle(name='water', liquid=True, solid=False), 0,
                        positions + 128.0, normals, uv, uv, indices)
    mesh = builder.build().collision_mesh()
    assert mesh is not None
    assert len(mesh[0]) == 4                    # the solid quad's corners only
