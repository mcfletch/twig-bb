"""Things that fly: rockets and grenades, stepped together as one batch.

**A batch, not bodies.**  A projectile is a position, a velocity, an owner and
a fuse, and hundreds of them are those things in numpy arrays stepped in one
pass.  Making each one a rigid body would put a solver on something that never
needs one, and would make a hundred rockets a hundred of everything.

**Swept, never tunnelling.**  Each tick a projectile casts from where it *was*
to where it wants to be, through :mod:`omi_physics.raycast`.  A rocket
integrated position-by-position is a rocket that is on one side of a wall at
900 units a second and on the other side a frame later, having touched nothing
in between; the cast is what makes the wall real.

**A rocket and a grenade differ in three declared numbers, not in code**:
whether gravity applies, what contact does — detonate, or bounce with a
restitution — and the fuse.  Two weapons that needed two code paths would be a
sign the table was not carrying the design, so there is one flight routine and
:func:`default_table` is where a rocket becomes a rocket.

**The owner matters for the first few metres and not after.**  A projectile
leaves from inside the person who fired it, so it ignores them until it has
cleared :data:`ARMING_DISTANCE` — and then stops ignoring them, because a
grenade bounced back off a wall coming home is the game working.

Splash damage, knockback and rocket jumps are :mod:`twig_bb.blast`, which
answers the :class:`~twig_bb.arena.Detonated` events this emits.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

import numpy as np

from omi_physics import raycast
from vrml import field, node

from . import combat

log = logging.getLogger(__name__)

__all__ = [
    'Detonation', 'Projectile', 'ProjectileTable', 'Projectiles',
    'default_table', 'ARMING_DISTANCE', 'GRENADE', 'ROCKET',
]

#: The kinds the stand-in loadout fires.
ROCKET = 'rocket'
GRENADE = 'grenade'

#: Metres a projectile must travel before it can meet the person who fired it.
#: Enough to clear a body — the capsule is 0.6 m across — and no further: a
#: projectile that ignored its owner for ten metres would make point-blank
#: rocket jumps impossible, and those are the interesting ones.
ARMING_DISTANCE = 1.2

#: How much of its own speed a projectile must keep after a bounce to go on
#: bouncing.  Below this it is put to rest, because a grenade that bounced for
#: ever at a millimetre a second is a grenade rattling under the player's feet
#: until its fuse runs out.
REST_SPEED = 0.6

#: Metres of clearance a bounce is nudged off the surface it met.  Without it
#: the next cast starts exactly on the triangle and may meet it again at zero
#: distance, which is a grenade welded to the floor.
BOUNCE_CLEARANCE = 0.02


class Projectile(node.Node):
    """One kind of thing that flies, as data.

    Speeds are **metres per second**, distances **metres**, times **seconds**
    and ``gravity`` is a downward acceleration in metres per second squared.
    The units are named because this table is the design: it is meant to be
    edited by somebody tuning the game rather than read by somebody following
    the code that consumes it.
    """

    PROTO = 'Projectile'
    key = field.newField('key', 'SFString', 1, '')

    #: How fast it leaves, and how hard it falls.  Zero gravity is a rocket.
    speed = field.newField('speed', 'SFFloat', 1, 24.0)
    gravity = field.newField('gravity', 'SFFloat', 1, 0.0)
    #: How near a surface it has to pass to touch it.
    radius = field.newField('radius', 'SFFloat', 1, 0.12)

    #: Seconds until it goes off in the air; 0 for one that never does.
    fuse = field.newField('fuse', 'SFFloat', 1, 0.0)
    #: Seconds before an unspent projectile is given up on, so a shot into the
    #: sky is not carried for the rest of the match.
    lifetime = field.newField('lifetime', 'SFFloat', 1, 8.0)

    #: How much of its speed a bounce keeps.  0 detonates on contact.
    bounce = field.newField('bounce', 'SFFloat', 1, 0.0)

    #: What a direct hit takes off.  It is **the whole of** what a direct hit
    #: costs: whoever is struck head-on is left out of the burst that follows
    #: (see :func:`twig_bb.blast.burst`), so that a hit is one hit with one
    #: number behind it rather than two that have to be tuned against each
    #: other.  Which means this number alone decides whether landing one is
    #: worth the aim, and at less than a full life the answer was no — a
    #: grenade square in somebody's chest left them walking, which is the one
    #: outcome nobody watching it would accept.
    damage = field.newField('damage', 'SFFloat', 1, 110.0)
    #: What the burst does at its centre, how far it reaches, and how hard it
    #: pushes there in metres per second.  Read by :mod:`twig_bb.blast`.
    splashDamage = field.newField('splashDamage', 'SFFloat', 1, 60.0)
    splashRadius = field.newField('splashRadius', 'SFFloat', 1, 4.0)
    #: The exponent of the falloff from the centre to the edge: 1 is linear,
    #: above 1 concentrates the damage near the middle and below 1 spreads it
    #: out.  The curve is a design decision and this is where it is written.
    splashFalloff = field.newField('splashFalloff', 'SFFloat', 1, 1.35)
    knockback = field.newField('knockback', 'SFFloat', 1, 9.0)
    #: The share of splash a shooter takes from their own burst.  Below one
    #: because a rocket jump has to be survivable to be a move; above zero
    #: because it has to be a *decision*.
    selfDamage = field.newField('selfDamage', 'SFFloat', 1, 0.5)


class ProjectileTable(node.Node):
    """Every kind of projectile this game knows about."""

    PROTO = 'ProjectileTable'
    kinds = field.newField('kinds', 'MFNode', 1, list)

    def by_key(self, key: str) -> Optional[Projectile]:
        """The kind with that key, or None -- an unknown key is not fatal."""
        for kind in self.kinds:
            if str(kind.key) == key:
                return kind
        return None


def default_table() -> ProjectileTable:
    """The two kinds the stand-in loadout fires.

    The numbers are ours; "right" means *plays well* and is settled by playing.
    What they are chosen around is the contrast: a rocket is fast, flat and
    unforgiving at close range, and a grenade is slow, thrown in an arc, and
    useful precisely because it goes where a straight line cannot.

    A function rather than a constant, because every field is writable and one
    match's tuning must not become every match's.
    """
    return ProjectileTable(kinds=[
        # Both direct hits are lethal against a full, unarmoured target, and
        # deliberately: a direct hit is the hardest shot either weapon has and
        # is the only thing that distinguishes aiming one from lobbing it in
        # the general direction.  Armour still saves you, which is what makes
        # armour worth the detour.
        Projectile(
            key=ROCKET, speed=26.0, gravity=0.0, radius=0.14,
            fuse=0.0, lifetime=6.0, bounce=0.0,
            damage=110.0, splashDamage=60.0, splashRadius=4.0,
            knockback=9.5, selfDamage=0.5),
        Projectile(
            key=GRENADE, speed=16.0, gravity=14.0, radius=0.12,
            # Longer than the flight to anywhere it can be usefully thrown, so
            # the fuse is a decision about *timing* rather than a range limit.
            fuse=2.2, lifetime=6.0, bounce=0.42,
            damage=110.0, splashDamage=80.0, splashRadius=4.5,
            knockback=8.0, selfDamage=0.6),
    ])


@dataclass(frozen=True)
class Detonation:
    """One projectile going off: where, what, whose, and what it hit directly."""

    point: np.ndarray
    kind: str
    by: str
    #: Who it hit head-on, or empty for one that met the level or its fuse.
    target: str = ''
    #: The surface normal where it landed, which is what an effect faces along.
    normal: Optional[np.ndarray] = None


class Projectiles:
    """Everything in flight, held as arrays and stepped in one pass.

    ``capacity`` is a budget, not a limit that is ever an error: a batch that
    is full refuses the next launch, which is a shot that does nothing rather
    than a frame that allocates.
    """

    def __init__(self, table: Optional[ProjectileTable] = None,
                 capacity: int = 256) -> None:
        self.table = table if table is not None else default_table()
        self.capacity = int(max(0, capacity))
        self.live = 0
        size = self.capacity
        self.position = np.zeros((size, 3), dtype='d')
        self.velocity = np.zeros((size, 3), dtype='d')
        self.age = np.zeros(size, dtype='d')
        #: How far each has travelled, for :data:`ARMING_DISTANCE`.
        self.travelled = np.zeros(size, dtype='d')
        #: Whether each has cleared the person who fired it.
        self.armed = np.zeros(size, dtype=bool)
        #: Which kind and whose, as indices into the two registries below —
        #: numpy holds numbers and these are names, and a parallel Python list
        #: would have to be compacted in step with the arrays anyway.
        self.kind = np.zeros(size, dtype='i4')
        self.owner = np.zeros(size, dtype='i4')
        self._kinds: List[Projectile] = []
        self._owners: List[str] = []

    def __len__(self) -> int:
        return self.live

    # -- launching --------------------------------------------------------
    def launch(self, kind: Any, origin: Sequence[float],
               direction: Sequence[float], owner: str = '') -> bool:
        """Put one in the air.  False if there was no room, or nowhere to go.

        ``direction`` need not be normalised — a caller with an aim vector
        should not have to care — and a direction of nothing is a shot that
        does not happen rather than an error.
        """
        if self.live >= self.capacity or kind is None:
            return False
        heading = np.asarray(direction, dtype='d')
        length = float(np.linalg.norm(heading))
        if length < 1e-12:
            return False
        index = self.live
        self.position[index] = np.asarray(origin, dtype='d')
        self.velocity[index] = heading / length * float(kind.speed)
        self.age[index] = 0.0
        self.travelled[index] = 0.0
        self.armed[index] = False
        self.kind[index] = self._index(self._kinds, kind)
        self.owner[index] = self._index(self._owners, owner)
        self.live = index + 1
        return True

    @staticmethod
    def _index(registry: List[Any], value: Any) -> int:
        """``value``'s place in a registry, added if it is not there yet."""
        for at, held in enumerate(registry):
            if held is value or held == value:
                return at
        registry.append(value)
        return len(registry) - 1

    def clear(self) -> None:
        """Take everything out of the air -- a respawn, a new match."""
        self.live = 0

    # -- flying -----------------------------------------------------------
    def step(self, world: Any, arena: Any, dt: float) -> List[Detonation]:
        """Advance every projectile by ``dt``; returns what went off.

        Combatants are staged into the world once for the whole batch rather
        than once per projectile: a firefight's worth of rockets otherwise adds
        and removes the same capsules a hundred times a tick.
        """
        if self.live <= 0 or dt <= 0.0:
            return []
        bodies = combat.stage(world, arena)
        try:
            return self._advance(world, arena, float(dt), bodies)
        finally:
            combat.unstage(world, bodies)

    def _advance(self, world: Any, arena: Any, dt: float,
                 bodies: dict) -> List[Detonation]:
        """One tick's flight, with the world already staged."""
        self._fall(dt)
        self.age[:self.live] += dt
        # Whose capsule is whose, worked out once for the batch: every unarmed
        # projectile asks the same question, and a scan per projectile per tick
        # is the sort of cost that only shows up when a firefight is busy.
        staged: dict = {}
        for body, id in bodies.items():
            staged.setdefault(id, []).append(body)
        gone: List[Detonation] = []
        spent: List[int] = []
        for index in range(self.live):
            if self._fly(world, arena, index, dt, staged, bodies, gone):
                spent.append(index)
        self._bury(spent)
        return gone

    def _fall(self, dt: float) -> None:
        """Apply each kind's gravity to the whole batch at once."""
        if not self._kinds:
            return
        pull = np.array([float(kind.gravity) for kind in self._kinds])
        self.velocity[:self.live, 1] -= pull[self.kind[:self.live]] * dt

    def _fly(self, world: Any, arena: Any, index: int, dt: float, staged: dict,
             bodies: dict, gone: List[Detonation]) -> bool:
        """Move one projectile; returns whether it is finished with.

        The whole of the swept step: cast from here to where it wants to be,
        and either arrive, detonate, or bounce and carry on.
        """
        kind = self._kinds[int(self.kind[index])]
        if self._expired(index, kind, arena, gone):
            return True
        start = self.position[index].copy()
        step = self.velocity[index] * dt
        distance = float(np.linalg.norm(step))
        if distance < 1e-12:
            return False
        found = raycast.raycast(world, start, step,
                                max_distance=distance + float(kind.radius),
                                skip=self._ignored(index, staged))
        if found is None:
            self.position[index] = start + step
            self.travelled[index] += distance
            self._arm(index)
            return False
        self.travelled[index] += float(found.distance)
        self._arm(index)
        target = bodies.get(found.body, '')
        if target or float(kind.bounce) <= 0.0:
            self._detonate(arena, index, kind, found.point, found.normal,
                           target, gone)
            return True
        self._bounce(index, kind, found)
        return False

    def _ignored(self, index: int, staged: dict) -> Sequence[int]:
        """Bodies this projectile's cast passes through.

        Its owner, and only until it has cleared them: a projectile leaves
        from inside the person who fired it, and one that went on ignoring
        them could never be bounced back into their own feet — which is the
        move this genre is built on.
        """
        if self.armed[index]:
            return ()
        return staged.get(self._owners[int(self.owner[index])], ())

    def _arm(self, index: int) -> None:
        """Notice that a projectile has cleared whoever fired it."""
        if not self.armed[index] and self.travelled[index] >= ARMING_DISTANCE:
            self.armed[index] = True

    def _expired(self, index: int, kind: Projectile, arena: Any,
                 gone: List[Detonation]) -> bool:
        """Whether a fuse or a lifetime has finished this one off.

        A fuse **detonates** and a lifetime does not: a grenade going off in
        the air is the feature, and a rocket that flew out of the level for
        six seconds bursting in the sky would be a bang from nowhere.
        """
        fuse = float(kind.fuse)
        if fuse > 0.0 and self.age[index] >= fuse:
            self._detonate(arena, index, kind, self.position[index], None,
                           '', gone)
            return True
        return self.age[index] >= float(kind.lifetime)

    def _detonate(self, arena: Any, index: int, kind: Projectile,
                  point: np.ndarray, normal: Optional[np.ndarray],
                  target: str, gone: List[Detonation]) -> None:
        """Apply a direct hit, announce the burst, and record it."""
        owner = self._owners[int(self.owner[index])]
        if target:
            arena.damage(target, float(kind.damage), by=owner, point=point)
        arena.detonated(point, kind=str(kind.key), by=owner, target=target)
        gone.append(Detonation(point=np.asarray(point, dtype='d').copy(),
                               kind=str(kind.key), by=owner, target=target,
                               normal=None if normal is None
                               else np.asarray(normal, dtype='d').copy()))

    def _bounce(self, index: int, kind: Projectile, found: Any) -> None:
        """Reflect a projectile off what it met, keeping ``bounce`` of its speed.

        Put a little clear of the surface, because a cast that starts exactly
        on a triangle meets it again at no distance at all — which is a grenade
        welded to the floor rather than one rolling along it.

        **The rest of the tick is not travelled.**  A grenade that bounces half
        way through a frame loses the other half of that frame's motion, which
        at sixty frames a second is a centimetre or two; carrying the remainder
        through would mean casting again, and again, for one rattling in a
        corner.
        """
        normal = np.asarray(found.normal, dtype='d')
        velocity = self.velocity[index]
        reflected = (velocity - 2.0 * float(np.dot(velocity, normal)) * normal)
        reflected *= float(kind.bounce)
        if float(np.linalg.norm(reflected)) < REST_SPEED:
            reflected[:] = 0.0
        self.velocity[index] = reflected
        self.position[index] = (np.asarray(found.point, dtype='d')
                                + normal * (float(kind.radius)
                                            + BOUNCE_CLEARANCE))

    def _bury(self, spent: List[int]) -> None:
        """Compact the survivors down over the gaps, keeping them packed.

        Back to front, so an index taken from the end has not itself been
        moved by an earlier swap in the same pass.
        """
        for index in reversed(spent):
            last = self.live - 1
            if index != last:
                for column in (self.position, self.velocity, self.age,
                               self.travelled, self.armed, self.kind,
                               self.owner):
                    column[index] = column[last]
            self.live = last

    # -- what is in the air -----------------------------------------------
    def describe(self) -> dict:
        """What is flying, as rows for the developer overlay."""
        return {'in flight': self.live, 'budget': self.capacity}
