"""Where a map's water, slime and lava are, so a swimmer can be in one.

A liquid is a *volume*, not a surface: its faces are drawn, but what decides
whether the avatar is swimming is whether the camera is inside the space they
bound.  The two families record that space differently and neither records it
as a box, so both are read through the leaves of the BSP tree, whose bounds are
already axis-aligned and stored:

* version 38 puts a contents word on every leaf (``SPEC-BSP38 §4.7``), and
  ``§9.4`` names water, slime and lava as the liquids;
* version 46 puts no contents word on a leaf at all (``SPEC-BSP46 §4.4.1``) --
  contents live on brushes, whose values ``§E.1`` deliberately does not state --
  so a leaf is a liquid when one of the brushes it holds is textured with a
  material carrying a liquid ``surfaceparm`` (``SPEC-Q3SHADER §2.2``).

The result is a set of boxes in scene space.  A leaf's box is the leaf's own
bound rather than the liquid's exact shape, which is conservative at the edges
of a sloped pool and exact for the boxy volumes maps actually use.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, List, Sequence, Tuple

import numpy as np

from . import q2bsp
from .worldgeometry import to_scene_points

log = logging.getLogger(__name__)

#: Every liquid, as the union ``SPEC-BSP38 §9.4`` states rather than a named
#: constant the spec does not define.
LIQUID_CONTENTS = q2bsp.CONTENTS_WATER | q2bsp.CONTENTS_SLIME | q2bsp.CONTENTS_LAVA


@dataclass(frozen=True)
class LiquidVolume:
    """One axis-aligned box of liquid, in scene space."""

    mins: np.ndarray
    maxs: np.ndarray


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
        if not self._volumes:
            return False
        position = np.asarray(point, dtype='d')
        inside = ((position >= self._mins) & (position <= self._maxs)).all(axis=1)
        return bool(inside.any())


def from_map(loaded: Any) -> LiquidVolumes:
    """Every liquid volume of a loaded map, whichever family it came from."""
    reader = _v38_liquid_leaves if loaded.version == 38 else _v46_liquid_leaves
    return LiquidVolumes(_volume(mins, maxs) for mins, maxs in reader(loaded))


def _volume(mins: Sequence[float], maxs: Sequence[float]) -> LiquidVolume:
    """A map-space bound as a scene-space box.

    The axis convention negates a coordinate (``SPEC-BSP38 §3.2``), so the two
    corners can come back the wrong way round and the box would contain nothing
    at all; they are re-ordered after the transform rather than before it.
    """
    corners = to_scene_points(np.array([mins, maxs], dtype='f'))
    return LiquidVolume(mins=corners.min(axis=0).astype('d'),
                        maxs=corners.max(axis=0).astype('d'))


def _v38_liquid_leaves(loaded: Any) -> Iterable[Tuple[Any, Any]]:
    """Bounds of every version 38 leaf whose contents include a liquid."""
    leaves = loaded.bsp.leafs
    if not len(leaves):
        return
    liquid = (leaves['contents'] & LIQUID_CONTENTS) != 0
    for leaf in leaves[liquid]:
        yield (leaf['mins'], leaf['maxs'])


def _v46_liquid_leaves(loaded: Any) -> Iterable[Tuple[Any, Any]]:
    """Bounds of every version 46 leaf holding a brush of liquid.

    Nothing is liquid without the material scripts: a brush names a texture and
    only a script says whether that texture is water (``SPEC-Q3SHADER §2.2``),
    so a map loaded with no content tree has no liquids to find.
    """
    bsp = loaded.bsp
    leaves, brushes, leafbrushes = bsp.leafs, bsp.brushes, bsp.leafbrushes
    if loaded.style_for is None or not len(leaves) or not len(brushes):
        return
    liquid_brush = np.array([_is_liquid(loaded, int(brush['texture']))
                             for brush in brushes])
    for leaf in leaves:
        first = int(leaf['leafbrush'])
        count = int(leaf['num_leafbrushes'])
        if count <= 0:
            continue
        indices = leafbrushes[first:first + count]
        if any(0 <= int(index) < len(liquid_brush) and liquid_brush[int(index)]
               for index in indices):
            yield (leaf['mins'], leaf['maxs'])


def _is_liquid(loaded: Any, texture_index: int) -> bool:
    """Whether a version 46 texture record names a liquid material."""
    name = loaded.bsp.texture_name(texture_index)
    return bool(name and loaded.style_for(name).liquid)
