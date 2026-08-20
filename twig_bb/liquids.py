"""Where a map's water, slime and lava are, so a swimmer can be in one.

A liquid is a *volume*, not a surface: its faces are drawn, but what decides
whether the avatar is swimming is whether the body is inside the space they
bound -- see :func:`twig_bb.viewer.update_submerged` for which part of the body
is asked, going in and coming out.  Version 46 records that space through the
brushes a leaf holds: it puts no contents word on a leaf at all
(``SPEC-BSP46 §4.4.1``) -- contents live on brushes, whose values ``§E.1``
deliberately does not state -- so a leaf is a liquid when one of the brushes it
holds is textured with a material carrying a liquid ``surfaceparm``
(``SPEC-Q3SHADER §2.2``).

The result is a set of boxes in scene space.  A leaf's box is the leaf's own
bound rather than the liquid's exact shape, which is conservative at the edges
of a sloped pool and exact for the boxy volumes maps actually use.

**Two of them hurt.**  :class:`LiquidHarm` is what standing in slime or lava
costs: a periodic bite rather than a trickle, because a health number sliding
down by one is not a warning and being taken a chunk at a time is.  The rates
are ours and are declared in :data:`HARM`; the death carries the liquid's name
as its cause, so the line a player reads is the true one and the arena's
frag-off rule -- dying to the map costs a frag -- applies without anything
having to invent a killer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from . import combat
from .worldgeometry import to_scene_points

log = logging.getLogger(__name__)

#: The three liquids, spelled as ``SPEC-Q3SHADER §2.2``'s ``surfaceparm``
#: spells them.
WATER = 'water'
SLIME = 'slime'
LAVA = 'lava'

#: The liquids **worst first**.  A body may span several, and a swimmer needs to
#: hear about the one that will hurt them, not the one that happens to be found
#: first.
LIQUID_SEVERITY = (LAVA, SLIME, WATER)


#: Health per second each liquid costs somebody standing in it.  **Ours**, and
#: chosen so that lava is a mistake you may just survive crossing and slime is
#: a place you can pass through if you must -- which is the only thing either
#: number has to be right about.  Water is in the table at zero rather than
#: left out of it, because "water does not hurt" is a decision and a table
#: with a hole in it reads as an oversight.
HARM = {WATER: 0.0, SLIME: 12.0, LAVA: 32.0}

#: Seconds between one bite and the next.
HARM_INTERVAL = 0.4

#: How tall the body :meth:`LiquidVolumes.kind_along` is asked about is.  The
#: combatant's own height, so what burns is what can be shot and what can walk.
BODY_HEIGHT = combat.BODY_HEIGHT


@dataclass(frozen=True)
class LiquidVolume:
    """One axis-aligned box of liquid, in scene space.

    ``kind`` is which liquid: what tints the view, and what will decide how
    much being in it hurts.  Empty only for a volume built without one, which
    no map reader produces.
    """

    mins: np.ndarray
    maxs: np.ndarray
    kind: str = WATER


class LiquidVolumes:
    """Every liquid volume of one map, and the one question a viewer asks.

    Held as two arrays rather than a list of objects: the test runs once per
    frame against every volume, and a map may have hundreds.
    """

    def __init__(self, volumes: Iterable[LiquidVolume]) -> None:
        self._volumes: List[LiquidVolume] = list(volumes)
        if self._volumes:
            self._mins = np.array([v.mins for v in self._volumes], dtype='d')
            self._maxs = np.array([v.maxs for v in self._volumes], dtype='d')
        else:
            self._mins = np.zeros((0, 3), dtype='d')
            self._maxs = np.zeros((0, 3), dtype='d')

    def __len__(self) -> int:
        return len(self._volumes)

    def contains(self, point: Sequence[float]) -> bool:
        """Whether ``point`` is inside any volume.

        The faces count as inside, so a camera drifting on the surface reads as
        submerged rather than flickering between modes.
        """
        return bool(self._inside(point).any()) if self._volumes else False

    def kind_at(self, point: Sequence[float]) -> str:
        """Which liquid ``point`` is in, or '' for none.

        Where volumes overlap the **smallest** one wins.  A leaf's box is the
        leaf's own bound rather than the liquid's exact shape, so neighbouring
        pools of different liquids overlap at their edges, and the smaller box
        is the more specific answer -- a pit of lava inside a flooded room
        reads as lava, which is the answer that matters.
        """
        if not self._volumes:
            return ''
        inside = self._inside(point)
        if not inside.any():
            return ''
        sizes = np.where(inside, (self._maxs - self._mins).prod(axis=1), np.inf)
        return self._volumes[int(np.argmin(sizes))].kind

    def medium_at(self, point: Sequence[float]) -> str:
        """Which substance ``point`` is in, or '' for none.

        The protocol
        :func:`OpenGLContext.scenegraph.water.submersion.submerge` asks of any
        set of volumes. This map's answer is :meth:`kind_at`'s -- smallest box
        wins -- because a leaf's bound is the partition's shape rather than the
        liquid's, and a pit of lava inside a flooded room is the answer that
        matters.
        """
        return self.kind_at(point)

    def kind_along(self, feet: Sequence[float], height: float) -> str:
        """Which liquid an upright body standing at ``feet`` is in, or ''.

        **A body rather than a point**, because the point that reads most
        naturally -- where somebody stands -- is the one place that is
        regularly outside the liquid they are up to their waist in.  A liquid
        brush is not solid, so falling into a pool takes you through it and on
        to whatever is underneath, and a map's floor commonly sits a hair
        below where the brush stops.  Asking about the feet alone therefore
        answers "not in any liquid" for somebody standing waist-deep in lava,
        and burns them only on the steps that happen to bob them upward.

        **The worst of them where a body spans several**, which is the other
        way round from :meth:`kind_at`.  Innermost-wins is the more specific
        answer about one point; a body reaching through a sheet of water into
        the lava below it is in the lava, and being told it is swimming is the
        answer that gets it killed.  Which is worse is :data:`LIQUID_SEVERITY`'s
        order.
        """
        if not self._volumes:
            return ''
        low = np.asarray(feet, dtype='d')
        crossed = self._crossed(low, low[1] + max(0.0, float(height)))
        if not crossed.any():
            return ''
        found = {self._volumes[at].kind for at in np.flatnonzero(crossed)}
        for kind in LIQUID_SEVERITY:
            if kind in found:
                return kind
        return self._volumes[int(np.argmax(crossed))].kind

    def _inside(self, point: Sequence[float]) -> np.ndarray:
        """A boolean per volume: is ``point`` in it?"""
        position = np.asarray(point, dtype='d')
        return ((position >= self._mins) & (position <= self._maxs)).all(axis=1)

    def _crossed(self, feet: np.ndarray, head: float) -> np.ndarray:
        """A boolean per volume: does the upright body at ``feet`` meet it?

        The body's own axis, not a cylinder around it: standing on the rim of
        a pool with a toe over the edge is standing on the rim.
        """
        flat = feet[[0, 2]]
        across = ((flat >= self._mins[:, [0, 2]])
                  & (flat <= self._maxs[:, [0, 2]])).all(axis=1)
        return across & (head >= self._mins[:, 1]) & (feet[1] <= self._maxs[:, 1])


def from_map(loaded: Any) -> LiquidVolumes:
    """Every liquid volume of a loaded map."""
    return LiquidVolumes(_volume(mins, maxs, kind)
                         for mins, maxs, kind in _v46_liquid_leaves(loaded))


def _volume(mins: Sequence[float], maxs: Sequence[float],
            kind: str) -> LiquidVolume:
    """A map-space bound as a scene-space box.

    The axis convention negates a coordinate (``SPEC-BSP46 §3.2``), so the two
    corners can come back the wrong way round and the box would contain nothing
    at all; they are re-ordered after the transform rather than before it.
    """
    corners = to_scene_points(np.array([mins, maxs], dtype='f'))
    return LiquidVolume(mins=corners.min(axis=0).astype('d'),
                        maxs=corners.max(axis=0).astype('d'), kind=kind)


def _v46_liquid_leaves(loaded: Any) -> Iterable[Tuple[Any, Any, str]]:
    """Bounds and kind of every version 46 **brush** of liquid.

    Nothing is liquid without the material scripts: a brush names a texture and
    only a script says whether that texture is water (``SPEC-Q3SHADER §2.2``),
    so a map loaded with no content tree has no liquids to find.

    **The brush's own extent, not the leaf's.**  A leaf reaches as far as the
    BSP split that made it — for a pool in a room, up to the ceiling — so a
    camera was inside the leaf long before it was inside the water, and
    standing ankle-deep fogged the whole view.  A brush states where it ends in
    its planes (``SPEC-BSP46 §4.7``, ``§4.8``), and that is the surface a
    swimmer should be tested against.  The leaf's bound is kept only as the
    fallback for a brush whose planes do not describe a box.
    """
    bsp = loaded.bsp
    leaves, brushes, leafbrushes = bsp.leafs, bsp.brushes, bsp.leafbrushes
    if loaded.style_for is None or not len(leaves) or not len(brushes):
        return
    brush_kind = [_liquid_kind(loaded, int(brush['texture']))
                  for brush in brushes]
    seen = set()
    for leaf in leaves:
        first = int(leaf['leafbrush'])
        count = int(leaf['num_leafbrushes'])
        if count <= 0:
            continue
        for index in leafbrushes[first:first + count]:
            index = int(index)
            if not (0 <= index < len(brush_kind)) or not brush_kind[index]:
                continue
            # One volume per *brush*.  A pool split across several leaves would
            # otherwise become several boxes of the same water, and the
            # innermost-wins rule in `kind_at` would then pick between them by
            # size rather than by what they hold.
            if index in seen:
                continue
            seen.add(index)
            bounds = _brush_bounds(bsp, brushes[index])
            if bounds is None:
                bounds = (leaf['mins'], leaf['maxs'])
            yield (bounds[0], bounds[1], brush_kind[index])


def _brush_bounds(bsp: Any, brush: Any) -> Optional[Tuple[Any, Any]]:
    """A brush's own box, from its axis-aligned planes, or None.

    ``SPEC-BSP46 §4.8``: a brush is the intersection of the half-spaces its
    sides name, each plane facing *out*.  For the boxy brushes a liquid volume
    is made of, the six axis-aligned planes give the box outright.  A brush
    with a slope has no single box and falls back to the leaf, which is the
    conservative answer it had before.
    """
    planes, sides = bsp.planes, bsp.brushsides
    if not len(planes) or not len(sides):
        return None
    low: List[Optional[float]] = [None, None, None]
    high: List[Optional[float]] = [None, None, None]
    first = int(brush['brushside'])
    count = int(brush['num_brushsides'])
    for offset in range(count):
        index = first + offset
        if not (0 <= index < len(sides)):
            return None
        plane = planes[int(sides[index]['plane'])]
        normal = np.asarray(plane['normal'], dtype='d')
        distance = float(plane['distance'])
        axis = int(np.argmax(np.abs(normal)))
        if abs(abs(float(normal[axis])) - 1.0) > 1e-4:
            return None                         # not axis aligned: no box
        if float(normal[axis]) > 0.0:
            high[axis] = distance
        else:
            low[axis] = -distance
    if any(value is None for value in low + high):
        return None
    return (np.array(low, dtype='d'), np.array(high, dtype='d'))


def _liquid_kind(loaded: Any, texture_index: int) -> str:
    """Which liquid a version 46 texture record names, or '' for none."""
    name = loaded.bsp.texture_name(texture_index)
    return loaded.style_for(name).liquidKind if name else ''


class LiquidHarm:
    """What standing in slime or lava costs, ticked.

    Held by whatever drives the match and advanced with it.  It reads each
    combatant's whole *body* against the volumes -- see
    :meth:`LiquidVolumes.kind_along` for why the feet alone are the one place
    that is regularly dry -- and applies :data:`HARM`; nothing here draws, and
    nothing here reads a clock -- time arrives through
    :meth:`advance`, so a match replays from its inputs exactly as the rest of
    the rules do.
    """

    def __init__(self, volumes: Any, rates: Optional[dict] = None,
                 interval: float = HARM_INTERVAL) -> None:
        self.volumes = volumes
        #: Health per second by liquid.  A copy, so one match retuning its
        #: lava does not retune every other match in the process.
        self.rates = dict(HARM if rates is None else rates)
        self.interval = float(interval)
        #: Seconds accumulated towards the next bite.
        self._owed = 0.0

    def advance(self, arena: Any, dt: float) -> int:
        """Move the clock on, and bite anybody standing in something.

        Returns how many combatants were hurt, which is what a test reads and
        what a developer overlay would show.
        """
        if not len(self.volumes):
            return 0
        self._owed += max(0.0, float(dt))
        if self._owed < self.interval:
            return 0
        bites = int(self._owed / self.interval)
        self._owed -= bites * self.interval
        return self._bite(arena, bites)

    def _bite(self, arena: Any, bites: int) -> int:
        """One round of damage, for however many intervals have passed.

        Several intervals in one call are applied as one larger bite rather
        than as several: a frame that took a quarter of a second should cost
        what a quarter of a second in lava costs, and a loop would emit four
        events for one moment of it.
        """
        hurt = 0
        for id in arena.ids():
            one = arena.combatant(id)
            if one is None or not one.alive:
                continue
            kind = self.volumes.kind_along(one.position, BODY_HEIGHT)
            rate = float(self.rates.get(kind, 0.0))
            if rate <= 0.0:
                continue
            arena.damage(id, rate * self.interval * bites, cause=kind)
            hurt += 1
        return hurt

    def describe(self) -> dict:
        """What this is watching, as rows for the developer overlay."""
        return {'liquid volumes': len(self.volumes)}
