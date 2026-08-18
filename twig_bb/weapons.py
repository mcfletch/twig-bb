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
:data:`twig_bb.art.ASSETS`, so re-modelling a weapon is an edit to this table
and not a code change.  Every model that ships with us is this project's own and
BSD; how each is built is in
[assets/weapons/CREDITS.md](assets/weapons/CREDITS.md).
"""

from __future__ import annotations

import math
from typing import List, Optional

from vrml import field, node

from OpenGLContext.ui.hudwidgets import CIRCLE, CROSS, CROSS_DOT, Crosshair

from .art import ASSETS, path_for

__all__ = [
    'Weapon', 'WeaponTable', 'default_table', 'model_path', 'spread_pixels',
    'reticule_spread', 'ASSETS',
]


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
    #: How much of it a player starts with.  A field because *how many rockets
    #: is worth* is a design decision and not an implementation one: a stand-in
    #: loadout that handed out sixty of everything made a rocket launcher an
    #: assault rifle with a bigger bang.  Where two weapons share an
    #: ``ammoType`` they share one pile, and the largest of their numbers is
    #: what a player starts with.
    startingAmmo = field.newField('startingAmmo', 'SFInt32', 1, 40)
    #: Seconds between shots.
    fireInterval = field.newField('fireInterval', 'SFFloat', 1, 0.4)
    #: Damage one trace does where it lands, out to :attr:`fullRange`.
    damage = field.newField('damage', 'SFFloat', 1, 20.0)
    #: How many projectiles or traces one shot sends: a shotgun's pellets.
    pellets = field.newField('pellets', 'SFInt32', 1, 1)

    #: How far ``damage`` carries undiminished, how far it takes to fade, and
    #: what is left at that distance and beyond — metres, metres, and health.
    #: **Range is most of what tells one hitscan weapon from another**: without
    #: it a pistol is a shotgun with a different rate of fire, and every fight
    #: in the level is fought at whatever distance the player happens to be
    #: standing.  A ``fadeRange`` at or inside ``fullRange`` — which is the
    #: default, both zero — is a weapon that hits equally hard anywhere, which
    #: is what a rifle wants and what a half-edited table falls back to.
    fullRange = field.newField('fullRange', 'SFFloat', 1, 0.0)
    fadeRange = field.newField('fadeRange', 'SFFloat', 1, 0.0)
    fadedDamage = field.newField('fadedDamage', 'SFFloat', 1, 0.0)

    #: Which entry of :mod:`twig_bb.projectiles`' table this weapon throws,
    #: or empty for a **hitscan** weapon whose shot arrives instantly.  This
    #: single field is the whole difference between a rifle and a rocket
    #: launcher as far as the rest of the game is concerned: what a projectile
    #: then does -- how fast, how far it falls, whether it bounces, what its
    #: burst costs -- is declared over there, because those are its numbers
    #: and not the weapon's.
    projectile = field.newField('projectile', 'SFString', 1, '')

    #: The cone the shot can land in, at rest and when firing continuously.
    #: Equal values are a weapon whose accuracy does not fall off.
    restSpread = field.newField('restSpread', 'SFFloat', 1, 0.0)
    maxSpread = field.newField('maxSpread', 'SFFloat', 1, 0.0)

    #: The reticule drawn while this weapon is selected.
    crosshair = field.newField('crosshair', 'SFNode', 1, node.NULL)

    #: The vertical field of view this weapon can be sighted through, in
    #: **degrees**, or 0 for one that cannot.  A weapon that kills at any
    #: range it can see has to be hard to *aim*, or it is the only weapon
    #: anybody carries: at three hundred metres a body covers a pixel or two,
    #: and a rifle with nothing to look through is not accurate, it is a
    #: lottery.  Held rather than toggled — see :data:`twig_bb.controls.ZOOM`.
    zoomFieldOfView = field.newField('zoomFieldOfView', 'SFFloat', 1, 0.0)

    #: Which entry of :mod:`twig_bb.combatsound`'s table this weapon is
    #: heard as.  Empty is the table's generic report, which is what makes a
    #: new weapon audible before anyone has designed a sound for it; a key
    #: that names nothing falls back to the same, because a silent weapon
    #: reads as a broken trigger.
    fireSound = field.newField('fireSound', 'SFString', 1, '')

    #: What one of its rounds sounds like **arriving**, on the level and on a
    #: person.  Empty is the table's generic pair, which is what an unnamed
    #: weapon and every future one get.
    #:
    #: A round landing is as much this weapon's sound as its report is: a
    #: rifle arrives with a chunk and a pistol with a ping, and a table with
    #: one impact sound in it makes every weapon land the same way however
    #: differently they fire.  **Whatever a weapon names, hitting a person has
    #: to stay louder and higher-priority than hitting a wall** — that is the
    #: sound a player acts on and the one that must survive a firefight
    #: running the voice pool dry — and there is a test over the whole table
    #: that says so.
    impactSound = field.newField('impactSound', 'SFString', 1, '')
    fleshSound = field.newField('fleshSound', 'SFString', 1, '')

    #: How the weapon moves when it is fired: back towards the eye in
    #: **metres**, up in **degrees**, and the **seconds** it takes to settle.
    #: This is the one piece of feedback that comes from the thing in the
    #: player's hands rather than from the world, so it arrives even when the
    #: shot goes into the sky and meets nothing at all -- and a weapon that did
    #: not move when it fired read as a weapon that had not fired.
    recoilKick = field.newField('recoilKick', 'SFFloat', 1, 0.035)
    recoilRise = field.newField('recoilRise', 'SFFloat', 1, 3.5)
    recoilRecovery = field.newField('recoilRecovery', 'SFFloat', 1, 0.16)

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

    def damage_at(self, distance: float) -> float:
        """What one trace costs after travelling ``distance`` metres.

        Linear between :attr:`fullRange` and :attr:`fadeRange`, and flat
        outside them.  Straight rather than curved because this is a number a
        player has to be able to predict from having been shot by it twice:
        anything an exponent adds is felt as the weapon being inconsistent.

        A weapon whose fade ends at or before its full range is one that does
        not fade at all, which is the default and is also what a table caught
        half-edited does — the safe answer being the weapon's own damage
        rather than nothing.
        """
        near, far = float(self.fullRange), float(self.fadeRange)
        full = float(self.damage)
        if far <= near:
            return full
        travelled = max(0.0, float(distance))
        if travelled <= near:
            return full
        faded = float(self.fadedDamage)
        if travelled >= far:
            return faded
        return full + (faded - full) * (travelled - near) / (far - near)


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
    return path_for(str(weapon.model))


def field_of_view(weapon: Optional[Weapon], zooming: bool,
                  default: float) -> float:
    """The vertical field of view the player is looking through, in radians.

    ``default`` is the view's own, and is the answer for everything except a
    weapon that declares a :attr:`~Weapon.zoomFieldOfView` while its owner is
    holding the zoom down.  Asked *per frame* from what is currently in hand,
    so switching weapon while sighted gives the wide view back with nothing
    having to remember to cancel anything — and so does dying, and so does
    running out of that weapon.
    """
    if weapon is None or not zooming:
        return float(default)
    narrow = float(weapon.zoomFieldOfView)
    return math.radians(narrow) if narrow > 0.0 else float(default)


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
    """A fresh copy of the loadout, which is where this game's design is written.

    **Five weapons that differ by range before they differ by anything else.**
    A pistol worth three times as much in somebody's face as down a corridor;
    a shotgun that kills outright inside five metres and cannot touch anybody
    past seventeen; a rifle that kills in one wherever it can see, once every
    second and a half; and two launchers whose burst is worth a third of a life
    two metres away, so they are aimed at the floor beside somebody rather than
    at them.  Without the ranges they are one weapon at five rates of fire, and
    every fight in the level is fought at whatever distance the two players
    happen to be standing.

    Every number is ours -- there is nothing to match and nothing to look up --
    which is why they are written as sentences about play and the fields are
    whatever makes those true.  The same is done to the tests in
    ``tests/test_weapons.py``, so retuning breaks a claim about the game rather
    than an assertion that a number is still itself.

    A function rather than a constant, because a table is authored data with
    every field writable: a game (or a test) adjusting one weapon's spread
    should not adjust it for every other table in the process.
    """
    return WeaponTable(weapons=[
        # The three that trace a line, and they are told apart by **range**
        # before anything else.  Without that they are one weapon at three
        # rates of fire, and every fight in the level is fought at whatever
        # distance the players happen to be standing.
        Weapon(
            key='pistol', title='PISTOL', slot=1,
            ammoType='bullets', ammoPerShot=1, startingAmmo=60,
            fireInterval=0.35,
            # Two shots in somebody's face, three across a room, half a dozen
            # down a corridor.  It is the weapon a player always has, so it
            # has to stay worth firing at any range and be worth *replacing*
            # at every one of them.
            damage=52.0, fullRange=4.0, fadeRange=40.0, fadedDamage=18.0,
            restSpread=0.6, maxSpread=2.5,
            recoilKick=0.030, recoilRise=3.5, recoilRecovery=0.14,
            crosshair=Crosshair(shape=CROSS, gap=5, length=7, thickness=2),
            fireSound='fire-pistol',
            model='weapons/handgun.glb', modelScale=1.0,
            modelOffset=(0.15, -0.17, -0.34),
        ),
        Weapon(
            key='shotgun', title='SHOTGUN', slot=2,
            ammoType='shells', ammoPerShot=1, startingAmmo=25,
            fireInterval=0.9,
            # A room-length weapon and nothing else: eight pellets at fourteen
            # each will kill outright inside five metres, and past seventeen
            # they arrive and cost nothing at all.  The falloff is *per
            # pellet*, so the cone thinning the pattern out and the range
            # taking the sting out of it compound -- which is why the middle
            # distance costs four or five shots rather than the two the
            # arithmetic alone would suggest.
            damage=14.0, pellets=8,
            fullRange=5.0, fadeRange=17.0, fadedDamage=0.0,
            restSpread=3.5, maxSpread=6.0,
            recoilKick=0.075, recoilRise=7.0, recoilRecovery=0.30,
            crosshair=Crosshair(shape=CIRCLE, gap=9, thickness=2),
            fireSound='fire-shotgun',
            model='weapons/sawn-off-shotgun.glb', modelScale=1.0,
            modelOffset=(0.19, -0.19, -0.40),
        ),
        # The opposite weapon in every respect: one shot, one kill, at any
        # range it can see, and a second and a half between shots to pay for
        # it.  What holds it in check is the *cost of missing* -- a shot that
        # misses is a second and a half of standing still while somebody who
        # heard it closes -- and that only works while the interval is long
        # enough to be a decision.  Ten rounds, because at one kill each that
        # is ten kills.  Armour still saves a target from it, which is what
        # armour is for and the reason the number is a little over a life
        # rather than far over it.
        Weapon(
            key='rifle', title='RIFLE', slot=3,
            ammoType='cartridges', ammoPerShot=1, startingAmmo=10,
            fireInterval=1.5,
            damage=120.0,
            # No cone at all at rest: at three hundred metres a tenth of a
            # degree is a body's width, so a rifle with a resting spread is a
            # rifle that cannot do the one thing it is for.  It opens if it is
            # fired faster than it can be, which it cannot be.
            restSpread=0.0, maxSpread=2.0,
            zoomFieldOfView=24.0,
            recoilKick=0.080, recoilRise=6.5, recoilRecovery=0.45,
            crosshair=Crosshair(shape=CROSS_DOT, gap=4, length=5, thickness=2),
            # The only weapon that names its own impact: a round this heavy
            # arriving is a chunk, and the generic ping made a shot that ends
            # a fight sound like a stone hitting a window.
            fireSound='fire-rifle', impactSound='impact-rifle',
            fleshSound='flesh-rifle',
            model='weapons/sniper-rifle.glb', modelScale=1.0,
            modelOffset=(0.17, -0.20, -0.52),
        ),
        # The two that throw something instead of tracing a line.  Nothing
        # here says what a rocket *does* -- how fast it goes, whether it
        # falls, what its burst costs -- because those are the projectile's
        # numbers and live in twig_bb.projectiles' own table.  The reticule
        # is deliberately open: a splash weapon is aimed at a place rather
        # than at a person, and a tight cross would say otherwise.
        Weapon(
            key='rocket', title='ROCKET', slot=4,
            ammoType='rockets', ammoPerShot=1, startingAmmo=8,
            fireInterval=0.85,
            projectile='rocket',
            recoilKick=0.090, recoilRise=8.0, recoilRecovery=0.34,
            crosshair=Crosshair(shape=CIRCLE, gap=11, thickness=2),
            fireSound='fire-rocket',
            # Modelled for this game at life size, in metres, already pointing
            # the way glTF calls forward -- so it needs no scaling and none of
            # the three correction angles the imported art needs.
            model='weapons/javelin-launcher.glb', modelScale=1.0,
            modelOffset=(0.30, -0.32, -0.86),
        ),
        Weapon(
            key='grenade', title='GRENADES', slot=5,
            ammoType='grenades', ammoPerShot=1, startingAmmo=10,
            fireInterval=0.75,
            projectile='grenade',
            recoilKick=0.045, recoilRise=5.0, recoilRecovery=0.22,
            crosshair=Crosshair(shape=CROSS_DOT, gap=10, length=4, thickness=2),
            fireSound='fire-grenade',
            model='weapons/grenade-launcher.glb', modelScale=1.0,
            modelOffset=(0.19, -0.20, -0.46),
        ),
    ])
