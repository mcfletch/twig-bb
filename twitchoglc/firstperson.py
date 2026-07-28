"""Holding a weapon where a first-person view wants it.

Two transforms, nested, and no matrix arithmetic anywhere: the outer one is put
exactly where the camera is and turned to face the same way
(:func:`aim_at_camera`), and the inner one carries where the weapon sits
*inside* that -- right, down and forward of the eye
(:func:`weapon_transform`).  "In the player's hands" is then a fact about the
scenegraph rather than something recomputed in the frame loop, and both halves
can be checked without a window.

The offsets and scales are fields of the weapon (:mod:`twitchoglc.weapons`), so
where a weapon is held is part of the table a designer edits rather than
something in here.

Used by both the map viewer and ``twitch-hud-demo``; the weapon is drawn the
same way in each, because it is the same weapon.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, Optional

from OpenGLContext.scenegraph.basenodes import Transform

from . import weapons as weapontable

log = logging.getLogger(__name__)

__all__ = ['WeaponHand', 'weapon_transform', 'aim_at_camera', 'view_rig']

#: The axis each of the weapon's three angles turns about, in the order they
#: are applied: yaw about up, then pitch about the side, then roll about the
#: direction of view.
_TURNS = (('modelYaw', (0.0, 1.0, 0.0)),
          ('modelPitch', (1.0, 0.0, 0.0)),
          ('modelRoll', (0.0, 0.0, 1.0)))


def weapon_transform(weapon: Any) -> Transform:
    """The transform that holds one weapon where a first-person view wants it.

    Its parent carries the camera's pose (:func:`aim_at_camera`); this carries
    only where the weapon sits *inside* that -- right, down and forward of the
    eye -- so nothing here has to know where the player is.

    The three angles become **nested transforms** rather than one composed
    rotation, because that is what makes them adjustable: a `Transform` holds a
    single axis and angle, so composing them by hand would turn "pitch it down
    another five degrees" into quaternion arithmetic instead of an edit to one
    number in the table.  A weapon that needs no turning gets no extra nodes.
    """
    scale = float(weapon.modelScale)
    holder = Transform(
        translation=tuple(float(value) for value in weapon.modelOffset),
        scale=(scale, scale, scale),
    )
    tail = holder
    for name, axis in _TURNS:
        angle = math.radians(float(getattr(weapon, name)))
        if not angle:
            continue
        turn = Transform(rotation=axis + (angle,))
        tail.children = [turn]
        tail = turn
    return holder


def aim_at_camera(hand: Transform, platform: Any) -> None:
    """Put a transform exactly where the camera is, facing the same way.

    The view matrix rotates the *world* by the camera's inverse, so the
    camera's own orientation is that rotation the other way round -- which is
    the one line of this that is worth a comment, because getting its sign
    wrong leaves the weapon pointing at the player's face.
    """
    position = getattr(platform, 'position', None)
    if position is None:
        return
    hand.translation = tuple(float(value) for value in position[:3])
    quaternion = getattr(platform, 'quaternion', None)
    if quaternion is None:
        return
    x, y, z, r = quaternion.XYZR()
    hand.rotation = (float(x), float(y), float(z), -float(r))


def view_rig(hand: 'WeaponHand') -> Transform:
    """Everything that travels with the camera.  Today that is the weapon.

    A separate function because *what* rides the view is a game's decision and
    grows -- §7's muzzle flash and §5's arms hang here too -- while the
    machinery that puts it where the camera is does not.

    **There is deliberately no light in here.**  A map places no dynamic lights
    at all: both families bake their lighting into lightmaps, which is what
    makes them look like themselves, so a weapon held in front of the camera is
    lit by almost nothing.  The obvious fix -- a fill light riding the camera --
    was tried and measured, and it brightened the *map* more than the weapon
    (+61 against +26 on a test capture): a flashlight washing out the baked
    lighting to show a stand-in is the wrong trade.  The weapon carries a small
    emissive floor in its own material instead, which touches that model and
    nothing else in the world.  See ``tools/prepare_weapon.py``.
    """
    return Transform(children=[hand.group])


class WeaponHand(object):
    """The weapon models, and which one is in the player's hands right now.

    Models are loaded once each and kept, because switching weapon happens
    several times a second when someone is trying the keys out and re-reading a
    glTF for each one would be visible.  A model that will not load leaves the
    hand empty rather than raising: the HUD and the reticule are the point of
    this demo and neither needs a model to work.
    """

    def __init__(self, table: Any) -> None:
        self.table = table
        self.group = Transform(children=[])
        self._loaded: Dict[str, Any] = {}
        #: The key of the weapon held; empty for none, which is what a hand
        #: starts out holding.
        self._current: str = ''

    def model_for(self, weapon: Any) -> Optional[Any]:
        """The scenegraph subtree for a weapon's model, loaded on first use."""
        path = weapontable.model_path(weapon)
        if path in self._loaded:
            return self._loaded[path]
        loaded = None
        try:
            from OpenGLContext.loaders.gltf import load_gltf
            loaded = load_gltf(path).group
        except Exception:                       # noqa: BLE001 - a demo, not a game
            log.warning('could not load the weapon model %s', path,
                        exc_info=True)
        self._loaded[path] = loaded
        return loaded

    @staticmethod
    def _tip(holder: Transform) -> Transform:
        """The innermost node of a holder's turning chain."""
        node = holder
        while getattr(node, 'children', None):
            node = node.children[0]
        return node

    def select(self, weapon: Any) -> bool:
        """Put a weapon in the hand.  False if it was already the one held."""
        key = str(weapon.key) if weapon is not None else ''
        if key == self._current:
            return False
        self._current = key
        if weapon is None:
            self.group.children = []
            return True
        model = self.model_for(weapon)
        holder = weapon_transform(weapon)
        if model is not None:
            self._tip(holder).children = [model]
        self.group.children = [holder]
        return True
