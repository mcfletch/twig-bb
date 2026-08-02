"""The map as something a shot, a footstep and a line of sight all meet.

One static mesh, and — the part these tests are about — a way back from the
triangle a ray reports to the surface that triangle came from.  Without it an
impact on marble and an impact on a grating are the same puff of dust.
"""

from __future__ import annotations

import numpy as np

from omi_physics import model, raycast
from omi_physics.world import PhysicsWorld

from twitchoglc import collision
from twitchoglc.surfaces import SurfaceStyle
from twitchoglc.worldgeometry import GeometryBuilder, SurfaceIndex


def _quad(x: float, style: SurfaceStyle):
    """One square wall standing across the x axis, in map coordinates."""
    e = 400.0
    positions = np.array([(x, -e, -e), (x, -e, e), (x, e, e), (x, e, -e)], 'f')
    normals = np.tile(np.array([1, 0, 0], 'f'), (4, 1))
    uv = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], 'f')
    return (style, positions, normals, uv, np.array([0, 1, 2, 0, 2, 3], np.uint32))


def _two_walls():
    """A world geometry of two differently-surfaced walls."""
    builder = GeometryBuilder()
    for x, name in ((200.0, 'stone'), (400.0, 'metal')):
        style, positions, normals, uv, indices = _quad(x, SurfaceStyle(name=name))
        builder.add_surface(style, -1, positions, normals, uv, uv, indices)
    return builder.build()


class TestBuildingItFromAMap:

    def test_a_map_with_solid_geometry_becomes_a_world(self):
        built = collision.from_geometry(_two_walls())
        assert isinstance(built.world, PhysicsWorld)
        assert built.world.body_count == 1

    def test_a_map_with_nothing_solid_has_no_collision_at_all(self):
        builder = GeometryBuilder()
        style, positions, normals, uv, indices = _quad(
            200.0, SurfaceStyle(name='fx', solid=False))
        builder.add_surface(style, -1, positions, normals, uv, uv, indices)
        assert collision.from_geometry(builder.build()) is None

    def test_the_index_matches_the_mesh_that_was_staged(self):
        built = collision.from_geometry(_two_walls())
        shape = built.world.shapes[int(built.world.collider_shape[built.body])]
        assert len(built.surfaces) == len(np.asarray(shape.indices).reshape((-1, 3)))


class TestWhatASurfaceAHitMet:

    def _cast(self, built, origin, direction):
        return raycast.raycast(built.world, origin, direction)

    def test_a_hit_reports_the_surface_of_the_wall_it_met(self):
        built = collision.from_geometry(_two_walls())
        hit = self._cast(built, (0, 0, 0), (1, 0, 0))
        assert built.style_at(hit).name == 'stone'

    def test_a_hit_on_the_further_wall_reports_the_other_surface(self):
        """The index is not merely returning its first entry."""
        built = collision.from_geometry(_two_walls())
        # Started past the near wall, so the far one is what is met.
        hit = self._cast(built, (300 * 0.0254 + 0.1, 0, 0), (1, 0, 0))
        assert built.style_at(hit).name == 'metal'

    def test_a_hit_on_another_body_has_no_surface(self):
        """A staged combatant capsule is not part of the level."""
        built = collision.from_geometry(_two_walls())
        shape = built.world.add_shape(model.Shape.sphere(radius=0.5))
        other = built.world.add_body(model.Motion(type=model.KINEMATIC),
                                     collider=model.Collider(shape=shape),
                                     position=(1.0, 0.0, 0.0))
        hit = self._cast(built, (0, 0, 0), (1, 0, 0))
        assert hit.body == other
        assert built.style_at(hit) is None

    def test_nothing_hit_has_no_surface(self):
        built = collision.from_geometry(_two_walls())
        assert built.style_at(None) is None


class TestTheRecordItself:

    def test_it_reports_no_surface_for_a_triangle_outside_the_mesh(self):
        world = PhysicsWorld()
        built = collision.MapCollision(
            world=world, body=0,
            surfaces=SurfaceIndex(ends=np.array([2]),
                                  styles=(SurfaceStyle(name='stone'),)))
        assert built.style_at(raycast.RayHit(
            body=0, distance=1.0, point=np.zeros(3), normal=np.zeros(3),
            triangle=9)) is None

    def test_a_shape_with_no_triangles_has_no_surface(self):
        """A sphere is a surface without parts; there is nothing to name."""
        world = PhysicsWorld()
        built = collision.MapCollision(
            world=world, body=0,
            surfaces=SurfaceIndex(ends=np.array([2]),
                                  styles=(SurfaceStyle(name='stone'),)))
        assert built.style_at(raycast.RayHit(
            body=0, distance=1.0, point=np.zeros(3), normal=np.zeros(3),
            triangle=raycast.NO_TRIANGLE)) is None
