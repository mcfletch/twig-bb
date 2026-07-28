"""What the player is carrying: a declared table of weapons, and their reticules.

**The table is the design document.** Every number a weapon has -- how fast it
fires, how wide its cone of fire opens, what ammunition it eats, which reticule
it draws -- is a field on a declared node rather than a constant in code, so a
variant retunes the game by setting fields and a settings screen can present
them.  See [PROJECT-PLAN §7](../PROJECT-PLAN.md), which owns the behaviour these
numbers will eventually drive; what is here is the half the HUD needs: what is
held, what is selected, what it costs to fire and what the player is aiming
with.

**The reticule is a weapon's property, not the game's.**  Each weapon carries a
:class:`~OpenGLContext.ui.hudwidgets.Crosshair`, so switching weapon is
switching that node rather than branching in the drawing code, and a weapon
whose accuracy falls off while firing shows that by widening its own reticule.

**The model is data too.**  ``model`` names a file under
:mod:`twitchoglc.assets`, so replacing the blocked-out stand-in with §7's
commissioned asset is an edit to this table and not a code change.  The
stand-ins that ship with us are CC0; their provenance is in
[assets/weapons/CREDITS.md](assets/weapons/CREDITS.md).
"""

from __future__ import annotations

import math
import os
from typing import List, Optional

from vrml import field, node

from OpenGLContext.ui.hudwidgets import CIRCLE, CROSS, CROSS_DOT, Crosshair

__all__ = [
    'Weapon', 'WeaponTable', 'default_table', 'model_path', 'spread_pixels',
    'reticule_spread', 'ASSETS',
]

#: Where the art that ships with this package lives.
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')


class Weapon(node.Node):
    """One weapon, as data.

    Angles are **degrees of cone half-angle**, times are **seconds**, and
    distances are map units; the units are named here because the table is
    meant to be edited by someone tuning the game rather than reading the code
    that consumes it.
    """

    PROTO = 'Weapon'
    #: How the rest of the game names this weapon, and how the HUD does.
    key = field.newField('key', 'SFString', 1, '')
    title = field.newField('title', 'SFString', 1, '')
    #: The number key it is selected with, 1-9.
    slot = field.newField('slot', 'SFInt32', 1, 0)

    #: What it fires and what that costs.  The type is a name rather than an
    #: index so several weapons can share a pool.
    ammoType = field.newField('ammoType', 'SFString', 1, 'bullets')
    ammoPerShot = field.newField('ammoPerShot', 'SFInt32', 1, 1)
    #: Seconds between shots.
    fireInterval = field.newField('fireInterval', 'SFFloat', 1, 0.4)
    #: Damage one shot does at the point it lands, before any falloff.
    damage = field.newField('damage', 'SFFloat', 1, 20.0)
    #: How many projectiles or traces one shot sends: a shotgun's pellets.
    pellets = field.newField('pellets', 'SFInt32', 1, 1)

    #: The cone the shot can land in, at rest and when firing continuously.
    #: Equal values are a weapon whose accuracy does not fall off.
    restSpread = field.newField('restSpread', 'SFFloat', 1, 0.0)
    maxSpread = field.newField('maxSpread', 'SFFloat', 1, 0.0)

    #: The reticule drawn while this weapon is selected.
    crosshair = field.newField('crosshair', 'SFNode', 1, node.NULL)

    #: The first-person model, relative to :data:`ASSETS`, and where it sits.
    #: The offset is in metres in view space -- right, up and forward -- and
    #: ``modelScale`` converts the source's units to metres (0.01 for art
    #: modelled in centimetres, which most of it is).
    model = field.newField('model', 'SFString', 1, '')
    modelScale = field.newField('modelScale', 'SFFloat', 1, 1.0)
    modelOffset = field.newField('modelOffset', 'SFVec3f', 1, (0.0, 0.0, 0.0))
    #: How to turn the source model to face the way the view does, in
    #: **degrees**, applied yaw then pitch then roll.  Three angles rather than
    #: one because art does not arrive pointing anywhere in particular: a model
    #: lying along +Y needs a pitch before a yaw is even meaningful.  Degrees
    #: because this table is read and edited by whoever is placing the weapon.
    modelYaw = field.newField('modelYaw', 'SFFloat', 1, 0.0)
    modelPitch = field.newField('modelPitch', 'SFFloat', 1, 0.0)
    modelRoll = field.newField('modelRoll', 'SFFloat', 1, 0.0)

    def spread_at(self, fraction: float) -> float:
        """The cone half-angle in degrees at ``fraction`` of the way to hot.

        Clamped at both ends, so a caller that has not bothered to keep its
        firing fraction in range gets the widest cone rather than an
        extrapolated one.
        """
        fraction = max(0.0, min(1.0, float(fraction)))
        rest = float(self.restSpread)
        return rest + (float(self.maxSpread) - rest) * fraction


class WeaponTable(node.Node):
    """Every weapon this game knows about, in the order they are shown."""

    PROTO = 'WeaponTable'
    weapons = field.newField('weapons', 'MFNode', 1, list)

    def by_key(self, key: str) -> Optional[Weapon]:
        """The weapon with that key, or None -- an unknown key is not fatal."""
        for weapon in self.weapons:
            if str(weapon.key) == key:
                return weapon
        return None

    def by_slot(self, slot: int) -> Optional[Weapon]:
        """The weapon on that number key, or None if nothing is on it."""
        for weapon in self.weapons:
            if int(weapon.slot) == int(slot):
                return weapon
        return None

    def keys(self) -> List[str]:
        """Every weapon's key, in table order."""
        return [str(weapon.key) for weapon in self.weapons]


def model_path(weapon: Weapon) -> str:
    """Where a weapon's model actually is on disk."""
    return os.path.join(ASSETS, str(weapon.model))


def spread_pixels(degrees: float, viewport_height: int,
                  field_of_view: float) -> float:
    """A cone half-angle, in degrees, as a radius in pixels on the screen.

    The renderer's own projection, so this is exact rather than a fudge factor:
    a point at angle ``a`` from the view axis lands ``tan(a)/tan(fov/2)`` of the
    way from the middle of the screen to its top edge.  A reticule drawn at this
    radius is telling the player the truth about where a shot may land, which is
    the only reason to draw it growing at all.

    ``field_of_view`` is the vertical field of view in **radians**, as the view
    platform reports it.
    """
    if degrees <= 0 or viewport_height <= 0 or field_of_view <= 0:
        return 0.0
    half = math.tan(float(field_of_view) / 2.0)
    if half <= 0:
        return 0.0
    return (viewport_height / 2.0) * math.tan(math.radians(degrees)) / half


def reticule_spread(weapon: Weapon, fraction: float, viewport_height: int,
                    field_of_view: float) -> float:
    """The gap a weapon's reticule should be opened by, in pixels."""
    return spread_pixels(weapon.spread_at(fraction), viewport_height,
                         field_of_view)


def default_table() -> WeaponTable:
    """A fresh copy of the stand-in loadout.

    Three weapons chosen to differ in the ways the HUD has to show: a tight
    cross that barely opens, a ring that opens a long way, and a fast weapon
    eating two cells a shot.  The art is CC0 firearms lying along +Y in their
    own space, which is what the pitch here is undoing; their exporter already
    scaled centimetres to metres, so the scale is 1.  Between them the reticule, the ammunition
    readout and the weapon bar can all be seen working before §7's weapons
    exist.  **They look different from each other too** -- switching weapon
    that changed nothing on screen was worse than no model at all.  The
    numbers are ours; the models are CC0 stand-ins.

    A function rather than a constant, because a table is authored data with
    every field writable: a game (or a test) adjusting one weapon's spread
    should not adjust it for every other table in the process.
    """
    return WeaponTable(weapons=[
        Weapon(
            key='pistol', title='PISTOL', slot=1,
            ammoType='bullets', ammoPerShot=1, fireInterval=0.35,
            damage=15.0, restSpread=0.6, maxSpread=2.5,
            crosshair=Crosshair(shape=CROSS, gap=5, length=7, thickness=2),
            model='weapons/luger-pistol.glb', modelScale=1.0,
            modelOffset=(0.15, -0.19, -0.30),
        ),
        Weapon(
            key='shotgun', title='SHOTGUN', slot=2,
            ammoType='shells', ammoPerShot=1, fireInterval=0.9,
            damage=12.0, pellets=8, restSpread=3.5, maxSpread=6.0,
            crosshair=Crosshair(shape=CIRCLE, gap=9, thickness=2),
            model='weapons/pump-shotgun.glb', modelScale=1.0,
            modelOffset=(0.21, -0.27, -0.12),
        ),
        Weapon(
            key='rifle', title='RIFLE', slot=3,
            ammoType='cells', ammoPerShot=2, fireInterval=0.12,
            damage=8.0, restSpread=1.2, maxSpread=4.5,
            crosshair=Crosshair(shape=CROSS_DOT, gap=4, length=5, thickness=2),
            model='weapons/assault-rifle.glb', modelScale=1.0,
            modelOffset=(0.19, -0.25, -0.14),
        ),
    ])
