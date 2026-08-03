"""How big a person is, stated once.

Four things in the game have to agree about how big a body is: the capsule the
player *walks* in, the capsule a shot *meets*, the capsule an opponent is
*drawn* as, and the height a camera looks from. They are one set of numbers,
stated here, because any two of them declared apart will differ — and a shot
capsule shorter than the drawn body sends a shot at somebody's chest over their
shoulder, while a body published from a camera at the wrong eye height stands
through the floor it is standing on.

The numbers are in **map units** because that is what a level is authored in
(``SPEC-BSP38 §3.2``: one unit is about an inch, and a standing player is 56
units tall on a 32 x 32 footprint), and are converted here so that nothing else
has to.

Where a spawn entity's origin sits relative to the feet is **not** a format
fact — the spec says nothing about it — so :data:`SPAWN_LIFT_UNITS` is our
decision, and it is the *one* place it is made: both the eye a camera binds to
and the feet a body stands on come from it, which is what stops the two
drifting apart.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

from .worldgeometry import SCENE_SCALE

__all__ = ['EYE_HEIGHT', 'HEIGHT', 'RADIUS', 'SPAWN_LIFT',
           'PLAYER_EYE_UNITS', 'PLAYER_HEIGHT_UNITS', 'PLAYER_RADIUS_UNITS',
           'SPAWN_LIFT_UNITS', 'feet_of', 'eye_of']

#: The standing player, in map units (``SPEC-BSP38 §3.2``).
PLAYER_HEIGHT_UNITS = 56.0
#: Half the 32-unit footprint the same paragraph gives.
PLAYER_RADIUS_UNITS = 16.0
#: How far up the eyes are.  Ours: the spec gives the body, not the view.
PLAYER_EYE_UNITS = 46.0

#: How far a spawn entity's origin sits **above the feet**, in map units.
#: Ours, because no spec states it.  One constant rather than two, so the eye a
#: camera is bound to and the feet a body is published at cannot disagree: two
#: of them differing by a metre puts a body inside the floor, where nothing is
#: looking for it.
SPAWN_LIFT_UNITS = 24.0

#: The same four in metres, which is what the scene is in.
HEIGHT = PLAYER_HEIGHT_UNITS * SCENE_SCALE
RADIUS = PLAYER_RADIUS_UNITS * SCENE_SCALE
EYE_HEIGHT = PLAYER_EYE_UNITS * SCENE_SCALE
SPAWN_LIFT = SPAWN_LIFT_UNITS * SCENE_SCALE


def feet_of(origin: ArrayLike) -> np.ndarray:
    """Where somebody spawning at entity ``origin`` stands, in scene metres."""
    return np.asarray(origin, dtype='d')[:3] - np.array([0.0, SPAWN_LIFT, 0.0])


def eye_of(origin: ArrayLike) -> np.ndarray:
    """Where somebody spawning at entity ``origin`` looks from, in scene metres."""
    return feet_of(origin) + np.array([0.0, EYE_HEIGHT, 0.0])
