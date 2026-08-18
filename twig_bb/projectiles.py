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
import math
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
    #: Thrust along its own heading, in metres per second squared: a motor
    #: rather than a muzzle.  Zero is an unpowered round -- a grenade, a
    #: bullet, a thrown thing -- that leaves at :attr:`speed` and from then on
    #: only ever slows.  Above zero is a rocket that leaves *slowly* and
    #: builds: what makes one worth dodging at a distance is that it arrives
    #: before a sidestep can, and what keeps it fair up close is that at the
    #: range a rocket jump is taken it has barely begun to move.  Applied at
    #: the end of a tick, so "leaves at :attr:`speed`" is true for the first
    #: instant of flight.
    acceleration = field.newField('acceleration', 'SFFloat', 1, 0.0)
    #: The speed a motor levels off at, in metres per second; 0 for one whose
    #: thrust never stops (which only a fused or short-lived kind should be,
    #: or it accelerates until its lifetime runs out).  It caps the whole
    #: speed and so is meant for a gravity-free thruster like a rocket rather
    #: than for something also being pulled down.
    maxSpeed = field.newField('maxSpeed', 'SFFloat', 1, 0.0)
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

    #: What one looks like in the air, relative to :data:`twig_bb.art.ASSETS`,
    #: and how big it is drawn.  A rocket and a grenade differ by three numbers
    #: in this table and not in code (see the module docstring); what they are
    #: *shaped* like is a fourth, and belongs here for the same reason.  Empty
    #: falls back to a glowing ball, which is what a kind whose art has not
    #: been made yet is drawn as.
    model = field.newField('model', 'SFString', 1, '')
    #: Larger than life on purpose: what a player has to do with an incoming
    #: rocket is *see* it in time, and a round drawn at the size it really is
    #: crosses a room as a dot.
    modelScale = field.newField('modelScale', 'SFFloat', 1, 1.0)

    def time_to(self, distance: float) -> float:
        """Seconds a shot of this kind takes to fly ``distance`` in a straight
        line, given its launch speed, its thrust and its top speed.

        The flat-flight answer: gravity is not in it, because the only caller
        that needs it leads a target's aim, a thrown arc is never led, and a
        flat shot is the one whose time this has to get right.  A kind that
        cannot move takes forever, reported as infinity rather than a division
        by zero, so a caller dividing by it simply declines to lead.
        """
        distance = max(0.0, float(distance))
        if distance == 0.0:
            return 0.0
        launch = float(self.speed)
        thrust = float(self.acceleration)
        top = float(self.maxSpeed)
        if thrust <= 0.0:
            return distance / launch if launch > 0.0 else math.inf
        # If it has a ceiling, how far it gets before reaching it -- past that
        # the flight is at a constant top speed and the rest is plain division.
        if top > launch:
            climb = (top - launch) / thrust
            reached = launch * climb + 0.5 * thrust * climb * climb
            if distance > reached:
                return climb + (distance - reached) / top
        # Still gaining the whole way: solve distance = launch t + thrust t^2/2.
        return (math.sqrt(launch * launch + 2.0 * thrust * distance)
                - launch) / thrust

    def distance_in(self, seconds: float) -> float:
        """How far a shot of this kind gets in ``seconds``, flat, thrust and all.

        The companion to :meth:`time_to`, and the honest range of a gravity-free
        motor: a rocket that leaves at 16 m/s and climbs to 60 covers far more
        ground over its life than its launch speed alone would say.  Gravity is
        not in it for the same reason it is not in ``time_to`` -- the flat
        flight is the one whose reach a bot gates on.
        """
        seconds = max(0.0, float(seconds))
        launch = float(self.speed)
        thrust = float(self.acceleration)
        top = float(self.maxSpeed)
        if thrust <= 0.0:
            return launch * seconds
        if top > launch:
            climb = (top - launch) / thrust
            if seconds > climb:
                reached = launch * climb + 0.5 * thrust * climb * climb
                return reached + top * (seconds - climb)
        return launch * seconds + 0.5 * thrust * seconds * seconds


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
        # And both bursts are worth dodging on their own.  A launcher whose
        # splash has to land on somebody is only a slow rifle: what these
        # weapons ask a player to do is aim at the floor beside an opponent
        # rather than at the opponent, and that trade is worth taking only if
        # the floor beside them costs a third of a life.  The exponent is what
        # decides that, more than the damage is -- much above 1 and everything
        # but a hit at the feet is a puff of smoke.
        Projectile(
            # A motor, not a bullet: it leaves at 16 m/s -- walking pace for a
            # rocket, slow enough that up close it is a splash weapon aimed at
            # the floor and not a flat one aimed at a chest -- and thrusts hard
            # to a top speed of 60, which a sidestep at any real distance
            # cannot beat.  It spends its first ~24 m getting there; beyond
            # that it cruises.  The old flat 26 m/s was dodgeable everywhere
            # and threatening nowhere.
            key=ROCKET, speed=16.0, acceleration=70.0, maxSpeed=60.0,
            gravity=0.0, radius=0.14,
            fuse=0.0, lifetime=6.0, bounce=0.0,
            damage=110.0, splashDamage=85.0, splashRadius=4.0,
            splashFalloff=1.15, knockback=11.0, selfDamage=0.45,
            model='weapons/javelin-rocket.glb', modelScale=1.6),
        Projectile(
            key=GRENADE, speed=16.0, gravity=14.0, radius=0.12,
            # Longer than the flight to anywhere it can be usefully thrown, so
            # the fuse is a decision about *timing* rather than a range limit.
            fuse=2.2, lifetime=6.0, bounce=0.42,
            damage=110.0, splashDamage=80.0, splashRadius=4.5,
            splashFalloff=1.15, knockback=10.0, selfDamage=0.55,
            # The 40 mm round the launcher fires, drawn at three times life so
            # a tumbling grenade is something a player can pick out and run
            # away from rather than a speck.
            model='weapons/grenade-round.glb', modelScale=3.0),
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


def _clear_of(kind: Projectile, found: Any) -> np.ndarray:
    """Where a round that met ``found`` has its warhead: a radius off it.

    A projectile is a sphere of :attr:`Projectile.radius` and the cast reports
    where its *nose* touched, so its middle -- which is where the burst is --
    is that far back along the surface normal.  The normal from a cast always
    faces back along the ray, so this always moves towards the shooter and a
    burst is never pushed through the wall it landed on.

    A centimetre and a half of geometry buys much more than it looks like.  The
    burst asks whether it can see each person near it, and a point sitting
    exactly on a triangle is on both sides of that triangle at once: the cast
    out of it meets the same triangle at no distance at all, whenever the
    rounding happens to fall that way, and everybody in the room is reported to
    be behind cover.  A rocket at somebody's feet then costs them nothing and
    moves them nowhere.
    """
    return (np.asarray(found.point, dtype='d')
            + np.asarray(found.normal, dtype='d') * float(kind.radius))


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

    def kind_at(self, slot: int) -> Optional[Projectile]:
        """Which kind of projectile is in ``slot``, or None if nothing is.

        The batch stores the kind as an index into a registry of its own, which
        is the right shape for stepping a hundred of them as arrays and the
        wrong shape for anybody else.  This is how the renderer asks what it is
        drawing without reaching inside.
        """
        if not 0 <= int(slot) < self.live:
            return None
        return self._kinds[int(self.kind[int(slot)])]

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
        # After the move, so this tick flew at the speed it started with and
        # a motor's gain is felt on the next one -- which is what makes "a
        # rocket leaves at ``speed``" exactly true and keeps every launch-speed
        # test honest.
        self._accelerate(dt)
        return gone

    def _fall(self, dt: float) -> None:
        """Apply each kind's gravity to the whole batch at once."""
        if not self._kinds:
            return
        pull = np.array([float(kind.gravity) for kind in self._kinds])
        self.velocity[:self.live, 1] -= pull[self.kind[:self.live]] * dt

    def _accelerate(self, dt: float) -> None:
        """Add each kind's thrust along its own heading, capped at its top speed.

        Vectorised over the whole batch like :meth:`_fall`.  A motor is a
        change to how *fast* a projectile goes and not to *where* -- so it
        scales the velocity a projectile already has rather than picking a
        fresh one, which keeps a rocket following the bounce it just took
        instead of snapping back onto the heading it was fired along.
        """
        live = self.live
        if not self._kinds or live <= 0:
            return
        which = self.kind[:live]
        thrust = np.array([float(k.acceleration) for k in self._kinds])[which]
        if not np.any(thrust > 0.0):
            return
        top = np.array([float(k.maxSpeed) for k in self._kinds])[which]
        speed = np.linalg.norm(self.velocity[:live], axis=1)
        powered = (thrust > 0.0) & (speed > 1e-9)
        if not np.any(powered):
            return
        gained = speed[powered] + thrust[powered] * dt
        ceiling = top[powered]
        capped = ceiling > 0.0
        gained[capped] = np.minimum(gained[capped], ceiling[capped])
        rows = np.nonzero(powered)[0]
        self.velocity[rows] *= (gained / speed[powered])[:, None]

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
            self._detonate(arena, index, kind, _clear_of(kind, found),
                           found.normal, target, gone)
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
