"""Holding a weapon where a first-person view wants it.

Two transforms, nested, and no matrix arithmetic anywhere: the outer one is put
exactly where the camera is and turned to face the same way
(:func:`aim_at_camera`), and the inner one carries where the weapon sits
*inside* that -- right, down and forward of the eye
(:func:`weapon_transform`).  "In the player's hands" is then a fact about the
scenegraph rather than something recomputed in the frame loop, and both halves
can be checked without a window.

The offsets and scales are fields of the weapon (:mod:`twig_bb.weapons`), so
where a weapon is held is part of the table a designer edits rather than
something in here.

Used by both the map viewer and ``twig-bb-hud``; the weapon is drawn the
same way in each, because it is the same weapon.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

from OpenGLContext.scenegraph.basenodes import Transform

from . import art

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
    grows -- a muzzle flash and §5's arms hang here too -- while the
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
        #: The weapon in hand, kept because the recoil is *its* numbers.
        self._weapon: Any = None
        #: When it last fired, on the caller's clock; None before any shot.
        self._fired_at: Optional[float] = None

    def model_for(self, weapon: Any) -> Optional[Any]:
        """The scenegraph subtree for a weapon's model, loaded on first use."""
        name = str(weapon.model)
        if name not in self._loaded:
            self._loaded[name] = art.load(name)
        return self._loaded[name]

    @staticmethod
    def _tip(holder: Transform) -> Transform:
        """The innermost node of a holder's turning chain."""
        node = holder
        while getattr(node, 'children', None):
            node = node.children[0]
        return node

    def fired(self, now: float) -> None:
        """Say a shot has just been taken, so the weapon kicks.

        Recorded rather than applied, because where the weapon *is* is a
        function of the clock: nothing has to tick, and the answer is the same
        whether it is asked once a frame or ten times -- the same rule the cone
        of fire follows.
        """
        self._fired_at = float(now)

    def settle(self, now: float) -> None:
        """Put the hand where the recoil has got to by ``now``.

        Back towards the eye and tipped up, decaying linearly to nothing over
        the weapon's own ``recoilRecovery``.  Written onto the group rather
        than the holder inside it, so the kick composes with wherever the table
        says this weapon sits in the hand rather than replacing it.
        """
        share = self._recoil(now)
        weapon = self._weapon
        if share <= 0.0 or weapon is None:
            self.group.translation = (0.0, 0.0, 0.0)
            self.group.rotation = (1.0, 0.0, 0.0, 0.0)
            return
        self.group.translation = (0.0, 0.0, float(weapon.recoilKick) * share)
        self.group.rotation = (
            1.0, 0.0, 0.0, math.radians(float(weapon.recoilRise)) * share)

    def _recoil(self, now: float) -> float:
        """How much of the kick is left, from 1 at the shot down to 0."""
        weapon = self._weapon
        if self._fired_at is None or weapon is None:
            return 0.0
        recovery = float(weapon.recoilRecovery)
        if recovery <= 0.0:
            return 0.0
        left = 1.0 - (float(now) - self._fired_at) / recovery
        return left if left > 0.0 else 0.0

    def select(self, weapon: Any) -> bool:
        """Put a weapon in the hand.  False if it was already the one held.

        **The hand's children are replaced in place**, which is what tells the
        renderer anything happened.  The render pass walks the scenegraph once
        and thereafter keeps its set of renderable paths up to date from the
        signals a node's ``children`` list sends as it is added to and removed
        from (``OpenGLContext.passes._flat.SGObserver``).  Rebinding the whole
        list -- ``self.group.children = [holder]`` -- puts a *new* list on the
        field instead of mutating the observed one, so nothing is sent and the
        pass goes on drawing the weapon that was there when it last looked:
        the scenegraph is right, the HUD reads the player's state directly and
        says ``ROCKET``, and the hand on screen still holds the pistol.
        """
        key = str(weapon.key) if weapon is not None else ''
        if key == self._current:
            return False
        self._current = key
        # A weapon taken out is not still recoiling when the next one comes up.
        self._weapon = weapon
        self._fired_at = None
        self.group.translation = (0.0, 0.0, 0.0)
        self.group.rotation = (1.0, 0.0, 0.0, 0.0)
        if weapon is None:
            self.group.children[:] = []
            return True
        model = self.model_for(weapon)
        # Built complete before it is hung on the hand: the holder is not in
        # the scene yet, so assembling it sends nothing and costs nothing.
        holder = weapon_transform(weapon)
        if model is not None:
            self._tip(holder).children = [model]
        self.group.children[:] = [holder]
        return True
