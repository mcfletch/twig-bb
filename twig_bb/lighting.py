"""The light a map has for the things that move through it.

A Quake 3 map bakes its lighting into lightmaps and places no lamps at all, so
a combatant, a pickup or a rocket -- none of which existed when the map was
compiled, and none of which carries a lightmap coordinate -- has nothing
lighting it.  What the map does carry for them is the lightvol lump: a coarse
grid of samples over the level, each saying how much light arrives at that
point and from which direction (``SPEC-BSP46 §4.14``).

This reads that lump into
:class:`OpenGLContext.scenegraph.lightgrid.LightGrid`, which is what the render
pass looks each object's position up in.  Two conversions happen on the way:
the samples are placed in the world, since the lump records values and not
where they are (``SPEC-BSP46 §4.14.2``), and they are turned from the map's
axes and inches into the scene's metres and +Y up.

A grid whose placement does not account for every sample in the lump is
**refused**: a grid put down in the wrong place lights the level from the wrong
places, which reads as a bug in the lighting rather than as an absence of it.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence, Tuple

import numpy as np

from OpenGLContext.scenegraph.lightgrid import LightGrid

from .materials import DEFAULT_LIGHTMAP_STRENGTH
from .worldgeometry import SCENE_SCALE

log = logging.getLogger(__name__)

__all__ = ['DEFAULT_GRID_SIZE', 'grid_spacing', 'grid_placement', 'light_grid']

#: How far apart the samples are, in map units, when the map does not say
#: (``SPEC-BSP46 §4.14.2``).  Wider vertically than horizontally because a
#: level is mostly floors: the light over a room changes far less between one
#: storey's height and the next than it does across the room.
DEFAULT_GRID_SIZE: Tuple[float, float, float] = (64.0, 64.0, 128.0)

#: What one angle byte is worth in radians (``SPEC-BSP46 §4.14.5``).
ANGLE_STEP = 2.0 * np.pi / 255.0


def grid_spacing(bsp: Any) -> Tuple[float, float, float]:
    """How far apart this map's samples are, in map units.

    The ``worldspawn`` entity's ``gridsize`` where it has one, and
    :data:`DEFAULT_GRID_SIZE` where it does not (``SPEC-BSP46 §4.14.2``).
    """
    for entity in bsp.entities:
        if entity.get('classname') != 'worldspawn':
            continue
        stated = entity.get('gridsize')
        if not stated:
            continue
        values = [float(value) for value in str(stated).split()]
        if len(values) == 3 and min(values) > 0:
            return (values[0], values[1], values[2])
        log.warning('ignoring a worldspawn gridsize of %r', stated)
    return DEFAULT_GRID_SIZE


def grid_placement(mins: Sequence[float], maxs: Sequence[float],
                   spacing: Sequence[float]) -> Tuple[np.ndarray, np.ndarray]:
    """Where the samples are, as (origin, counts) in map units.

    ``SPEC-BSP46 §4.14.2``: they lie on the points whose coordinates are whole
    multiples of ``spacing`` and which fall inside the world model's bounding
    box, so the box is stepped inwards to the lattice rather than outwards.
    """
    step = np.asarray(spacing, dtype='d')
    first = np.ceil(np.asarray(mins, dtype='d') / step)
    last = np.floor(np.asarray(maxs, dtype='d') / step)
    counts = (last - first).astype(int) + 1
    return first * step, counts


def light_grid(bsp: Any, strength: float = DEFAULT_LIGHTMAP_STRENGTH
               ) -> Optional[LightGrid]:
    """This map's baked irradiance grid as a scene node, or None.

    None where the map compiled no grid, and None where the placement does not
    account for exactly the samples the lump holds -- see the module docstring
    for why that is refused rather than approximated.

    ``strength`` is the exposure the map's lightmaps are drawn at.  The grid
    and the lightmaps are two records of one solve, so a figure lit by the grid
    and the floor it stands on have to be scaled alike or the figure reads as
    pasted onto the room.
    """
    samples = getattr(bsp, 'lightvols', None)
    if samples is None or not len(samples):
        return None
    spacing = grid_spacing(bsp)
    model = bsp.models[0]
    origin, counts = grid_placement(model['mins'], model['maxs'], spacing)
    expected = int(np.prod(counts))
    if expected != len(samples) or min(counts) < 1:
        log.warning(
            'ignoring the light grid in this map: its bounds and %s spacing '
            'call for %d samples and the lump holds %d',
            tuple(spacing), expected, len(samples))
        return None

    shape = (int(counts[2]), int(counts[1]), int(counts[0]))    # z, y, x
    ambient = _scene_order(samples['ambient'].astype('f').reshape(shape + (3,))
                           / 255.0)
    directional = _scene_order(
        samples['directional'].astype('f').reshape(shape + (3,)) / 255.0)
    direction = _scene_order(
        _towards_light(samples['direction']).reshape(shape + (3,)))

    return LightGrid(
        origin=_scene_origin(origin, spacing, counts),
        spacing=(spacing[0] * SCENE_SCALE, spacing[2] * SCENE_SCALE,
                 spacing[1] * SCENE_SCALE),
        counts=[int(counts[0]), int(counts[2]), int(counts[1])],
        ambient=ambient, directional=directional, direction=direction,
        intensity=float(strength),
    )


def _towards_light(angles: np.ndarray) -> np.ndarray:
    """The two angle bytes as unit vectors towards the light, in scene axes.

    ``SPEC-BSP46 §4.14.5``: the first byte is measured from map +Z and the
    second about it from map +X.
    """
    from .worldgeometry import to_scene_directions
    phi = angles[:, 0].astype('d') * ANGLE_STEP
    theta = angles[:, 1].astype('d') * ANGLE_STEP
    return to_scene_directions(np.column_stack((
        np.sin(phi) * np.cos(theta),
        np.sin(phi) * np.sin(theta),
        np.cos(phi),
    ))).astype('f')


def _scene_origin(origin: np.ndarray, spacing: Sequence[float],
                  counts: np.ndarray) -> Tuple[float, float, float]:
    """The scene-space corner of the grid: the sample the node indexes first.

    Scene +Z is map -Y, so the corner the node starts from is the map's *last*
    sample along y rather than its first.
    """
    far_y = origin[1] + spacing[1] * (int(counts[1]) - 1)
    return (float(origin[0]) * SCENE_SCALE, float(origin[2]) * SCENE_SCALE,
            float(-far_y) * SCENE_SCALE)


def _scene_order(volume: np.ndarray) -> np.ndarray:
    """Map-ordered samples (z, y, x) as scene-ordered ones, flattened.

    Scene x is map x, scene y is map z and scene z is map -y, so the axes are
    swapped and the one that reversed is counted from the other end.  The node
    wants them flat with x varying fastest, which is the order they are already
    in along each axis.
    """
    return volume.transpose(1, 0, 2, 3)[::-1].reshape(-1, 3)
