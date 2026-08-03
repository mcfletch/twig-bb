"""The map as one thing a footstep, a shot and a line of sight all meet.

A level's drawn geometry and the geometry it is *solid* in are the same
triangles read two ways, and this is the second reading: one static trimesh in
a :class:`~omi_physics.world.PhysicsWorld`, which is what the character
controller walks on and what :mod:`twig_bb.combat` casts against.

**It carries what each of those triangles is made of.**  A ray cast reports the
triangle it met, and on its own that is a number; paired with the
:class:`~twig_bb.worldgeometry.SurfaceIndex` built from the same batches in
the same order, it is the surface — which is what lets an impact on metal spark
where one on stone puffs, and what an impact sound is chosen by.  The two are
built together and kept together for exactly that reason: a mesh and an index
that can be handed around separately are a mesh and an index that will one day
describe different maps.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from omi_physics import model
from omi_physics.world import PhysicsWorld

from .surfaces import SurfaceStyle
from .worldgeometry import SurfaceIndex

log = logging.getLogger(__name__)

__all__ = ['MapCollision', 'from_geometry', 'from_map']

#: Metres per second squared, downwards.  The world's gravity rather than the
#: map's: a map states its own in :mod:`twig_bb.maploader` and the
#: navigator applies it, while the physics world only has to be built with
#: something sane for anything simulated in it directly.
GRAVITY = 9.81


@dataclass(frozen=True)
class MapCollision:
    """A map's collision world, the body holding it, and its surfaces."""

    #: The physics world.  It holds the map and nothing else at first;
    #: combatant capsules are staged into it for the moment a shot is resolved.
    world: PhysicsWorld
    #: Which body of that world is the map.
    body: int
    #: What each triangle of that body is made of.
    surfaces: SurfaceIndex

    def style_at(self, hit: Any) -> Optional[SurfaceStyle]:
        """The surface a ray hit met, or None if it did not meet the map.

        None covers all three ways there is no answer — no hit at all, a hit on
        something staged into the world rather than on the level, and a hit on
        a shape that has no triangles to name.  Every caller does the same
        thing with each: falls back to a plain effect.
        """
        if hit is None or int(hit.body) != self.body:
            return None
        return self.surfaces.style_at(hit.triangle)


def from_map(loaded: Any) -> Optional[MapCollision]:
    """The collision of a loaded map, or None if it has nothing solid."""
    return from_geometry(loaded.world)


def from_geometry(geometry: Any) -> Optional[MapCollision]:
    """The collision of built world geometry, or None if nothing in it is solid.

    None rather than an empty world, because a map with no floor cannot be
    walked in at all and the caller's answer to that is to stay in free-fly
    rather than to walk on nothing.
    """
    mesh = geometry.collision_mesh()
    if mesh is None:
        return None
    points, triangles = mesh
    world = PhysicsWorld(gravity=model.Gravity(gravity=GRAVITY,
                                               direction=(0, -1, 0)))
    shape = world.add_shape(model.Shape.trimesh(points, triangles))
    body = world.add_body(model.Motion(type=model.STATIC),
                          model.Collider(shape=shape))
    return MapCollision(world=world, body=body,
                        surfaces=geometry.collision_surfaces())
