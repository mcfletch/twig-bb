"""Firing a weapon: where the shot goes, what it meets, and what that costs.

A shot is a **ray cast**, not a projectile: the trace leaves the muzzle and
whatever it meets first is what was hit. That is what a bullet is in this genre
and it is what makes a shot feel instant.

The ray cast itself is [omi_physics](../../omi_physics/)'s, because "what does
this line meet" is a question a rigid-body world should be able to answer and
because a bot asks the same one about line of sight. What is here is only the
*rules*: how many traces a trigger pull sends, how wide the cone is, what a hit
takes off, and that a shooter does not shoot themselves.

**Combatants are put in the world as capsules.** A shot has to be able to meet a
body, and the body a character controller already has is a capsule — so the
same shape a bot walks in is the shape it is shot in, and there is no second
idea of where somebody is to fall out of step with the first.
"""

from __future__ import annotations

import logging
import math
import random
import weakref
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np
from numpy.typing import ArrayLike

from omi_physics import model, raycast

from OpenGLContext import entropy

from . import avatar

log = logging.getLogger(__name__)

__all__ = ['Hit', 'NOBODY', 'SCATTER_STREAM', 'aim_at', 'can_see', 'fire',
           'stage', 'unstage', 'who_is_at']

#: The session stream a shot's scatter is drawn from when the caller pins no
#: seed of its own.  Named, so that a weapon spreading has no effect on where a
#: bot decides to walk and a session recording puts both back: see
#: :mod:`OpenGLContext.entropy`.
SCATTER_STREAM = 'twig-scatter'

#: :attr:`Hit.target` for a trace that met the level rather than a person.
#: The absence of a target rather than an invented name, so nothing has to
#: filter a pretend combatant out of a scoreboard — and the same spelling
#: :mod:`twig_bb.arena` already uses for a death with no killer.
NOBODY = ''

#: How far a hitscan trace reaches, in metres.  Not a weapon field: every
#: weapon here is instant and the limit exists so a shot into the sky stops
#: rather than walking the whole world.  A weapon that should carry less than
#: this wants a `range` field of its own, which is a table edit.
TRACE_RANGE = 400.0

#: The capsule a combatant is shot in.  The character controller's own
#: proportions — literally the same numbers, from
#: :mod:`twig_bb.avatar` — so what you can hit is what can walk.  Declared
#: separately once, and the two disagreed by forty centimetres.
BODY_HEIGHT = avatar.HEIGHT
BODY_RADIUS = avatar.RADIUS

#: How far above the feet a combatant looks from, in metres.  The eyes rather
#: than the middle: a knee-high ledge between two players does not blind them.
EYE_HEIGHT = avatar.EYE_HEIGHT

#: The capsule pool for each physics world; see :class:`_Capsules`.  Weak, so
#: a map that has been unloaded takes its pool with it.
_POOLS: "weakref.WeakKeyDictionary[Any, Any]" = weakref.WeakKeyDictionary()


@dataclass(frozen=True)
class Hit:
    """One trace that met something — a person, or the level.

    **A hit on the level is a hit.**  It is where an impact effect is drawn, an
    impact sound is played and a burst is centred, and a shot that reported
    only its casualties would leave all three with nothing to hang on.  Which
    of the two it is is read from :attr:`target`, and
    :attr:`on_somebody` is the same question asked so that no caller has to
    know that an empty id spells "the world".
    """

    #: Who was hit, or :data:`NOBODY` for the level.
    target: str
    #: Where, in world coordinates.
    point: np.ndarray
    #: The surface normal there, facing back along the trace, which is what an
    #: effect is oriented from.
    normal: np.ndarray
    #: How much health it cost.  Zero for the level, which does not bleed.
    damage: int = 0
    #: What the level is made of where it was met, or None: for a hit on a
    #: person, for a shot resolved without a
    #: :class:`~twig_bb.collision.MapCollision`, and for geometry whose
    #: surface cannot be named.  Callers choose an effect by it and fall back
    #: to a plain one, so None is an answer rather than an error.
    surface: Optional[Any] = None

    @property
    def on_somebody(self) -> bool:
        """Whether this landed on a combatant rather than on the level."""
        return bool(self.target)


def fire(world: Any, arena: Any, shooter: str, weapon: Any,
         origin: Sequence[float], direction: Sequence[float],
         spread: float = 0.0, seed: Optional[int] = None,
         surfaces: Optional[Any] = None) -> List[Hit]:
    """Fire one shot; returns every impact it made and applies the damage.

    ``spread`` is the half-angle of the cone in **degrees**, which is what the
    weapon table states and what the reticule is drawn from — so a weapon
    firing while running scatters exactly as widely as the crosshair says it
    will.

    ``seed`` pins this one shot's scatter, which is what a test does with it.
    Without one the scatter comes from the **session's** own stream
    (:mod:`OpenGLContext.entropy`), so successive shots spread differently --
    a cone whose every shot took one path is a cone in name only -- while a
    session run again from its seed spreads them all exactly as it did.  That
    is what a recorded session replaying and, later, client-side prediction
    both need; it is not a promise of bit-identical results across machines,
    which is a much harder one.

    ``surfaces`` is the :class:`~twig_bb.collision.MapCollision` the level
    was built as, and is what a hit on the world takes its material from.
    Without one a world impact still happens and still has a place and a
    normal; it simply cannot say what it met, and an effect chosen from that
    falls back to the plain one.

    Every trace that met *anything* is returned, in the order the pellets were
    fired.  A trace that met nothing is not: a miss is an absence, and it is
    the shot itself -- which the caller knows it took -- rather than this list
    that says a weapon was used.
    """
    start = np.asarray(origin, dtype='d')
    heading = _unit(np.asarray(direction, dtype='d'))
    if heading is None:
        return []
    arena.fired(shooter, weapon.key, origin=start, direction=heading)
    bodies = stage(world, arena, without=shooter)
    scatter = (random.Random(seed) if seed is not None
               else entropy.randomizer(SCATTER_STREAM))
    landed: List[Hit] = []
    for _pellet in range(max(1, int(weapon.pellets))):
        trace = _scattered(heading, spread, scatter) if spread > 0.0 else heading
        found = raycast.raycast(world, start, trace, max_distance=TRACE_RANGE)
        if found is None:
            continue
        landed.append(_landed(arena, bodies, shooter, weapon, found, surfaces))
    unstage(world, bodies)
    return landed


def _landed(arena: Any, bodies: dict, shooter: str, weapon: Any, found: Any,
            surfaces: Optional[Any]) -> Hit:
    """One trace's meeting: the damage applied and the impact announced.

    A body staged for this shot is a person and everything else is the level,
    which is why the staging table answers the whole question: nothing has to
    ask the physics world what kind of thing it just reported.

    **How far it flew is what decides what it costs**, through the weapon's own
    :meth:`~twig_bb.weapons.Weapon.damage_at`.  Measured here rather than
    from where the two of them are standing, because the trace is the only
    thing that knows: it stops at the near side of a capsule, and a weapon that
    fades sharply would otherwise disagree with itself by the width of a body.
    A hit that costs nothing is still a hit -- it is drawn, it is heard, and it
    says a shotgun has been fired at somebody from too far away, which is worth
    knowing from both ends.
    """
    target = bodies.get(found.body)
    style = None if target is not None or surfaces is None \
        else surfaces.style_at(found)
    taken = 0 if target is None else arena.damage(
        target, weapon.damage_at(float(found.distance)), by=shooter,
        point=found.point)
    arena.impact(point=found.point, normal=found.normal,
                 surface='' if style is None else style.name,
                 target=NOBODY if target is None else target, by=shooter,
                 weapon=str(weapon.key))
    return Hit(target=NOBODY if target is None else target, point=found.point,
               normal=found.normal, damage=taken, surface=style)


def who_is_at(world: Any, arena: Any, looker: str, origin: ArrayLike,
              direction: ArrayLike,
              reach: float = TRACE_RANGE) -> str:
    """Who a shot from here would hit, or :data:`NOBODY`.

    The same trace :func:`fire` sends and against the same staged bodies, so
    the answer is the one a shot would give rather than a second opinion about
    it: a name that appeared over somebody a shot would miss is worse than no
    name at all.  Nothing is damaged and nothing is announced -- this is a
    question, and asking it every frame must not put anything on the event
    stream.

    A wall between the two answers nobody, because the wall is what the trace
    meets first.  That is also what stops this being a way to find people
    through geometry.
    """
    start = np.asarray(origin, dtype='d')
    heading = _unit(np.asarray(direction, dtype='d'))
    if heading is None:
        return NOBODY
    bodies = stage(world, arena, without=looker)
    try:
        found = raycast.raycast(world, start, heading, max_distance=reach)
    finally:
        unstage(world, bodies)
    return NOBODY if found is None else bodies.get(found.body, NOBODY)


def can_see(world: Any, arena: Any, looker: str, target: str, seen: Optional[dict] = None) -> bool:
    """Whether ``looker`` has an unobstructed view of ``target``.

    Eyes to eyes.  The dead cannot be seen, which is what stops a bot aiming at
    a corpse until it respawns somewhere else.
    """
    from_one = arena.combatant(looker)
    to_other = arena.combatant(target)
    if from_one is None or to_other is None or not to_other.alive:
        return False
    # Whether two people can see each other is one fact about the pair, not two
    # about each of them: the segment between their eyes is the same segment
    # either way round.  ``seen`` is a caller's memo for one tick, so a room in
    # which everybody looks at everybody casts each ray once instead of twice.
    key = (looker, target) if looker < target else (target, looker)
    if seen is not None:
        found = seen.get(key)
        if found is not None:
            return found
    answer = raycast.line_of_sight(world, _eye(from_one), _eye(to_other))
    if seen is not None:
        seen[key] = answer
    return answer


def aim_at(arena: Any, shooter: str, target: str) -> Optional[np.ndarray]:
    """A unit heading from one combatant's eyes to another's, or None."""
    from_one = arena.combatant(shooter)
    to_other = arena.combatant(target)
    if from_one is None or to_other is None or from_one is to_other:
        return None
    return _unit(_eye(to_other) - _eye(from_one))


def visible_targets(world: Any, arena: Any, looker: str,
                    within: Optional[float] = None,
                    facing: Optional[Sequence[float]] = None,
                    cone: Optional[float] = None,
                    seen: Optional[dict] = None) -> List[str]:
    """Everyone alive that ``looker`` can see, nearest first.

    The question a bot's perception asks each time it thinks.  It goes through
    the *same* line of sight every difficulty uses — a bot that could see
    through a wall would not be difficult, it would be annoying.

    ``within`` is how far the looker can see, in metres; ``facing`` and ``cone``
    are which way it is looking and how wide, in degrees either side.  Both are
    optional and both are **rejections applied before the line of sight**,
    because casting a ray is the expensive half of a bot and a target that is
    too far away or behind them was never going to count.  Asking the cheap
    questions first does not change the answer, only the work: looking is
    quadratic in how many are in the room, and every difficulty pays it.
    """
    from_one = arena.combatant(looker)
    if from_one is None or not from_one.alive:
        return []
    here = np.asarray(from_one.position, dtype='d')
    furthest = None if within is None else float(within) ** 2
    ahead, least = None, -1.0
    if facing is not None and cone is not None:
        ahead = _unit(np.asarray(facing, dtype='d'))
        least = math.cos(math.radians(float(cone)))
    found = []
    for other in arena.ids():
        if other == looker:
            continue
        target = arena.combatant(other)
        if target is None or not target.alive:
            continue
        to = np.asarray(target.position, dtype='d') - here
        gap = float(to.dot(to))
        if gap < 1e-18 or (furthest is not None and gap > furthest):
            continue
        if ahead is not None and float(ahead.dot(to)) < least * math.sqrt(gap):
            continue
        if can_see(world, arena, looker, other, seen=seen):
            found.append((math.sqrt(gap), other))
    return [other for _distance, other in sorted(found)]


# -- putting people in the world ---------------------------------------------

def stage(world: Any, arena: Any, without: str = NOBODY) -> dict:
    """Add a capsule for every living combatant; return ``{body: id}``.

    Added for the query and taken away again by :func:`unstage`, so the
    physics world stays what it is between frames — the map's collision
    geometry — and a trace never meets a body left behind by an earlier shot.

    ``without`` leaves somebody out rather than having the ray cast skip them,
    which is what a hitscan shot does with its shooter: their capsule is
    around their own muzzle, and a shot that had to be *told* to ignore it
    would be a shot that hit them whenever anyone forgot.  A projectile wants
    the opposite — everybody staged, and its owner skipped only until it has
    cleared them — so this is a parameter rather than a rule.
    """
    pool = _capsules(world)
    bodies = {}
    for id in arena.ids():
        if id == without:
            continue
        one = arena.combatant(id)
        if one is None or not one.alive:
            continue
        bodies[pool.take(world, one.position)] = id
    return bodies


class _Capsules:
    """Reusable capsule bodies for staging combatants in one physics world.

    **A pool rather than a body per shot.**  A world's arrays are columnar and
    index-addressed, so nothing can be *removed* from one — removing a body
    would renumber every body after it, and something else is holding those
    numbers.  Adding a fresh capsule per shot therefore grows the world for
    the length of the match, and every ray cast walks every body in it: a
    firefight in the tenth minute would cast more slowly than one in the
    first, for no reason a player could see.

    One shape serves them all, because every combatant is the same capsule.
    """

    def __init__(self, world: Any) -> None:
        middle = max(BODY_HEIGHT - 2 * BODY_RADIUS, 1e-3)
        self.shape = world.add_shape(model.Shape.capsule(height=middle,
                                                         radius=BODY_RADIUS))
        self.bodies: List[int] = []
        #: How many of them are staged right now.
        self.taken = 0

    def take(self, world: Any, feet: np.ndarray) -> int:
        """A capsule standing at ``feet``; returns its body index.

        Grown only when a match has more combatants alive at once than it has
        ever had before, so the pool settles at the size of the biggest fight.
        """
        if self.taken >= len(self.bodies):
            self.bodies.append(world.add_body(
                model.Motion(type=model.KINEMATIC),
                collider=model.Collider(shape=self.shape)))
        body = self.bodies[self.taken]
        self.taken += 1
        centre = (np.asarray(feet, dtype='d')
                  + np.array([0.0, BODY_HEIGHT * 0.5, 0.0]))
        world.collider_shape[body] = self.shape
        # Through the world rather than into its position array: a body's own
        # bounding box is what a ray is rejected against, and a box left where
        # the capsule used to be answers about where somebody used to be.
        world.place_body(body, position=centre)
        return body

    def release(self, world: Any) -> None:
        """Switch every staged capsule back off and hand them all back."""
        for body in self.bodies[:self.taken]:
            world.collider_shape[body] = -1
        self.taken = 0


def _capsules(world: Any) -> _Capsules:
    """The capsule pool for one world, made on first use.

    Kept against the world rather than in a module-level table so it goes when
    the world does and two maps never share one -- the same rule the ray
    caster's own mesh cache follows.
    """
    pool = _POOLS.get(world)
    if pool is None:
        pool = _POOLS[world] = _Capsules(world)
    return pool


def unstage(world: Any, bodies: dict) -> None:
    """Take the staged capsules back out of the world, ready to be used again.

    By dropping their colliders rather than by removing the bodies: see
    :class:`_Capsules` for why a world cannot have anything taken out of it,
    and why that makes reuse the only way to keep it from growing.

    ``bodies`` is what :func:`stage` returned, and is accepted so the two read
    as a pair even though the pool is what knows which are staged.
    """
    _capsules(world).release(world)


def _eye(one: Any) -> np.ndarray:
    """Where a combatant looks from."""
    return np.asarray(one.position, dtype='d') + np.array([0.0, EYE_HEIGHT, 0.0])


def _scattered(heading: np.ndarray, spread: float,
               scatter: random.Random) -> np.ndarray:
    """One trace inside a cone of half-angle ``spread`` degrees about ``heading``.

    Sampled over the spherical *cap* rather than by perturbing two angles: the
    second concentrates traces toward the middle and makes a shotgun's pattern
    a dot with a halo instead of an even spray.
    """
    angle = math.radians(max(0.0, float(spread)))
    if angle <= 0.0:
        return heading
    cosine = 1.0 - scatter.random() * (1.0 - math.cos(angle))
    sine = math.sqrt(max(0.0, 1.0 - cosine * cosine))
    about = scatter.random() * 2.0 * math.pi
    side, up = _frame(heading)
    return (heading * cosine
            + side * (sine * math.cos(about))
            + up * (sine * math.sin(about)))


def _frame(heading: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Two unit vectors across ``heading``, however it is pointed."""
    # Whichever world axis the heading is least aligned with, so the cross
    # product never collapses -- straight up is the case that would.
    axis = np.array([0.0, 1.0, 0.0])
    if abs(float(np.dot(heading, axis))) > 0.9:
        axis = np.array([1.0, 0.0, 0.0])
    side = np.cross(heading, axis)
    side = side / np.linalg.norm(side)
    return (side, np.cross(heading, side))


def _unit(vector: np.ndarray) -> Optional[np.ndarray]:
    """``vector`` normalised, or None if it has no direction."""
    length = float(np.linalg.norm(vector))
    if length < 1e-9:
        return None
    return vector / length
