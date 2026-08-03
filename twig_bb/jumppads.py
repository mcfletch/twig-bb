"""Push volumes: jump pads, wind tunnels and freeze volumes.

Everything here cites ``SPEC-TRIGGER-PUSH``.  A push volume is a brush entity
whose bounding box, when a player is inside it, *replaces* that player's
velocity with a vector derived from the entity's orientation and ``speed``
(``§2.1``, ``§2.4``).  The viewer reproduces that with the character
controller's ``apply_impulse``, which is the same primitive: it discards the
capsule's current motion, carries the horizontal part unscaled by air control
until ground friction bleeds it away, and ungrounds the capsule so the
step-down snap does not eat the launch.

Three behaviours are easy to get wrong and are each pinned by a test:

* ``speed`` of exactly zero means the default, not a dead pad (``§1.4``);
* a pad with no orientation is a **freeze volume**, not a no-op (``§3.5``,
  ``§3.6``) — the direction is the zero vector and the assignment still
  happens, so maps may rely on it pinning whoever stands there;
* the overlap test has two units of slack and never consults the brush's
  planes (``§5.4``–``§5.6``), so a tight test misses pads that work in the
  original.

Contacts come from the physics world's own trigger system, and are evaluated
after the frame's movement (``§7.6``); a player in a noclip movement mode
generates none at all (``§7.8``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from omi_physics import model
from omi_physics.world import PhysicsWorld

from .entities import Entity
from .worldgeometry import SCENE_SCALE, to_scene_directions, to_scene_points

log = logging.getLogger(__name__)

#: ``SPEC-TRIGGER-PUSH §1.2``, ``§1.4`` -- the default `speed`, substituted for
#: an absent key *and* for a value of exactly zero.
DEFAULT_PUSH_SPEED = 1000.0

#: ``SPEC-TRIGGER-PUSH §2.1``, ``§2.2`` -- velocity = direction x speed x 10.
#: The factor is unconditional and is not derived from the tick rate.
SPEED_TO_VELOCITY = 10.0

#: ``SPEC-TRIGGER-PUSH §8.1`` -- world gravity in units per second squared,
#: the figure pad speeds are conventionally quoted against.
DEFAULT_GRAVITY = 800.0

#: ``SPEC-TRIGGER-PUSH §5.4``, ``§5.5`` -- linking grows every entity's box by
#: one unit on each face, and the overlap test runs between two grown boxes, so
#: the effective slack against the raw brush bounds is two units per axis.
TRIGGER_SLACK = 2.0

#: ``SPEC-TRIGGER-PUSH §4.1`` -- the only spawnflag bit `trigger_push` reads.
PUSH_ONCE = 1

#: ``SPEC-TRIGGER-PUSH §3.4`` -- two orientation triples are not orientations
#: at all but select a fixed vertical direction, matched on the whole triple by
#: exact equality.
STRAIGHT_UP_TRIPLE = (0.0, -1.0, 0.0)
STRAIGHT_DOWN_TRIPLE = (0.0, -2.0, 0.0)

#: ``SPEC-TRIGGER-PUSH §9.4`` -- `trigger_monsterjump`'s defaults, and the
#: interval its retrigger is limited to.  Despite the name, this fork throws
#: player clients too.
MONSTERJUMP_SPEED = 200.0
MONSTERJUMP_HEIGHT = 200.0
MONSTERJUMP_INTERVAL = 0.1

#: ``SPEC-Q3PUSH §2.3`` -- how far above the higher end of the arc its apex
#: sits, in map units.  A choice, not an engine fact: the trajectory through a
#: destination is a one-parameter family and nothing observable picks a member.
ARC_CLEARANCE = 128.0

PUSH_CLASSNAME = 'trigger_push'
MONSTERJUMP_CLASSNAME = 'trigger_monsterjump'

#: Size of the box that stands in for the player in the sensor world, in map
#: units.  ``SPEC-BSP38 §3.2`` gives the standing character as 56 units tall on
#: a 32 x 32 footprint, and ``SPEC-TRIGGER-PUSH §5.6`` makes the test
#: box-against-box, so a box is the faithful shape — not a capsule.
PLAYER_BOX = (32.0, 32.0, 56.0)


@dataclass
class PushVolume:
    """One push entity: an axis-aligned box and the velocity it assigns."""

    #: Map-space bounds, already grown by the slack of ``§5.4``–``§5.5``.
    mins: np.ndarray
    maxs: np.ndarray
    #: Map-unit velocity per second the volume assigns (``§2.1``).
    velocity: np.ndarray
    #: ``§4.1`` -- destroy the volume after the first contact of any kind.
    once: bool = False
    #: ``§9.4`` -- seconds between retriggers, or 0 for every frame (``§7.1``).
    retrigger_interval: float = 0.0
    classname: str = PUSH_CLASSNAME

    @property
    def is_noop(self) -> bool:
        """Always False: even a zero velocity is an effect (``§3.6``).

        A volume with no orientation assigns (0, 0, 0) every frame a player is
        inside it, which pins them.  The property exists to make that explicit
        where a reader would otherwise assume "no direction" meant "skip me".
        """
        return False

    def scene_velocity(self) -> np.ndarray:
        """The velocity in scene units: metres per second, +Y up."""
        return to_scene_directions(self.velocity.reshape((1, 3)))[0] * SCENE_SCALE

    def scene_box(self) -> Tuple[np.ndarray, np.ndarray]:
        """The volume's bounds in scene space, as ``(low, high)`` corners."""
        corners = to_scene_points(np.array([self.mins, self.maxs]))
        return (corners.min(axis=0), corners.max(axis=0))


def map_gravity(entities: Sequence[Entity]) -> float:
    """The map's gravity in units per second squared (``§8.1``, ``§8.2``).

    ``worldspawn`` may override the engine default for the whole level; a map
    that supplies no such key uses 800.
    """
    for entity in entities:
        if entity.classname == 'worldspawn':
            value = entity.number('gravity', DEFAULT_GRAVITY)
            return value if value > 0 else DEFAULT_GRAVITY
    return DEFAULT_GRAVITY


def orientation_triple(entity: Entity) -> Tuple[float, float, float]:
    """The entity's (pitch, yaw, roll) triple (``§3.1``–``§3.3``).

    ``angle`` is a yaw-only shorthand equivalent to the triple (0, a, 0), and
    it overwrites any prior value, so it is read after ``angles``.
    """
    triple = entity.vector('angles')
    if 'angle' in entity:
        triple = (0.0, entity.number('angle'), 0.0)
    return triple


def push_direction(entity: Entity) -> np.ndarray:
    """The unit push direction of an entity, or the zero vector (``§3``)."""
    return direction_from_triple(orientation_triple(entity))


def direction_from_triple(triple: Tuple[float, float, float]) -> np.ndarray:
    """The direction one orientation triple selects (``§3.4``–``§3.6``, ``§6.3``)."""
    if triple == STRAIGHT_UP_TRIPLE:
        return np.array([0.0, 0.0, 1.0])
    if triple == STRAIGHT_DOWN_TRIPLE:
        return np.array([0.0, 0.0, -1.0])
    if triple == (0.0, 0.0, 0.0):
        # §3.5: the direction is computed only for a non-zero triple, and §3.6
        # requires an importer to reproduce the zero vector rather than fix it.
        return np.zeros(3)
    return forward_vector(triple[0], triple[1])


def forward_vector(pitch: float, yaw: float) -> np.ndarray:
    """``(cos p cos y, cos p sin y, -sin p)`` (``§6.3``).

    Roll does not appear (``§6.4``), and the result is unit length for all
    finite pitch and yaw (``§6.5``).  Positive pitch aims **downward**
    (``§6.2``) — the sign an importer is most likely to get backwards.
    """
    p, y = np.radians(pitch), np.radians(yaw)
    return np.array([np.cos(p) * np.cos(y), np.cos(p) * np.sin(y), -np.sin(p)])


def push_speed(entity: Entity) -> float:
    """The `speed` key with the zero-means-default rule applied (``§1.4``)."""
    speed = entity.number('speed', DEFAULT_PUSH_SPEED)
    return speed if speed else DEFAULT_PUSH_SPEED


def gravity_rescale(map_g: float, scene_g: float) -> float:
    """``sqrt(scene gravity / map gravity)``, which preserves apex and range.

    Pad speeds are tuned against the map's own gravity (``§8.1``, ``§8.2``).
    Running the scene at a different gravity and scaling the whole velocity by
    this factor leaves the launch's height and distance alone and changes only
    how long the flight takes.
    """
    if map_g <= 0 or scene_g <= 0:
        return 1.0
    return float(np.sqrt(scene_g / map_g))


def push_velocity(entity: Entity, map_g: float = DEFAULT_GRAVITY,
                  scene_g: float = DEFAULT_GRAVITY) -> np.ndarray:
    """The map-unit velocity a `trigger_push` assigns (``§2.1``)."""
    velocity = push_direction(entity) * push_speed(entity) * SPEED_TO_VELOCITY
    return velocity * gravity_rescale(map_g, scene_g)


def monsterjump_velocity(entity: Entity, map_g: float = DEFAULT_GRAVITY,
                         scene_g: float = DEFAULT_GRAVITY) -> np.ndarray:
    """The map-unit velocity a `trigger_monsterjump` assigns (``§9.4``).

    ``speed`` scales the direction's horizontal part; ``height`` *is* the
    vertical component rather than scaling the direction's own vertical part.
    A yaw of exactly zero is read as 360 first, so unlike `trigger_push` this
    entity can never end up aimed nowhere.
    """
    triple = orientation_triple(entity)
    if triple[1] == 0.0 and triple not in (STRAIGHT_UP_TRIPLE, STRAIGHT_DOWN_TRIPLE):
        triple = (triple[0], 360.0, triple[2])
    direction = direction_from_triple(triple)
    speed = entity.number('speed', MONSTERJUMP_SPEED) or MONSTERJUMP_SPEED
    height = entity.number('height', MONSTERJUMP_HEIGHT) or MONSTERJUMP_HEIGHT
    velocity = np.array([direction[0] * speed, direction[1] * speed, height])
    return velocity * gravity_rescale(map_g, scene_g)


def arc_flight_time(source: Any, destination: Any, gravity: float) -> float:
    """How long the aimed arc of ``SPEC-Q3PUSH §2.3`` is in the air.

    Rise to an apex ``ARC_CLEARANCE`` above the higher end, then fall to the
    destination: the two halves are ordinary free fall, so the time is the sum
    of their durations.
    """
    source = np.asarray(source, dtype='d')
    destination = np.asarray(destination, dtype='d')
    gravity = abs(float(gravity)) or DEFAULT_GRAVITY
    rise = max(destination[2] - source[2], 0.0) + ARC_CLEARANCE
    drop = rise - (destination[2] - source[2])
    return float(np.sqrt(2.0 * rise / gravity) + np.sqrt(2.0 * drop / gravity))


def aimed_velocity(source: Any, destination: Any, gravity: float) -> np.ndarray:
    """The map-unit launch velocity that carries a player to ``destination``.

    ``SPEC-Q3PUSH §2.1``: a version 46 pad is aimed at a place rather than
    pointed in a direction, so the velocity is solved rather than read.  The
    vertical component is whatever reaches the apex of ``§2.3``; the horizontal
    one is the separation divided by the flight time, which is what makes the
    arc pass through the destination rather than merely towards it.
    """
    source = np.asarray(source, dtype='d')
    destination = np.asarray(destination, dtype='d')
    gravity = abs(float(gravity)) or DEFAULT_GRAVITY
    rise = max(destination[2] - source[2], 0.0) + ARC_CLEARANCE
    flight = arc_flight_time(source, destination, gravity)
    velocity = (destination - source) / flight
    velocity[2] = np.sqrt(2.0 * gravity * rise)
    return velocity


def _destinations(entities: Sequence[Entity]) -> Dict[str, np.ndarray]:
    """Every ``targetname`` a pad may be aimed at, and where it is.

    ``SPEC-Q3PUSH §1.3``: the match is on the name, not on the classname --
    three different classnames carry one in the shipped maps and nothing
    distinguishes them for this purpose.
    """
    found: Dict[str, np.ndarray] = {}
    for entity in entities:
        name = entity.get('targetname')
        if name and entity.get('origin'):
            found.setdefault(name.lower(),
                             np.asarray(entity.vector('origin'), dtype='d'))
    return found


def push_volumes(source: Any, scene_gravity: Optional[float] = None
                 ) -> List[PushVolume]:
    """Every push volume of a map.

    ``source`` supplies ``entities`` and ``model_bounds(index)``.  ``§5.1``:
    the volume is the brush model's axis-aligned bounding box, which no entity
    key can resize; ``§5.3``: the `origin` key translates it.
    """
    gravity = map_gravity(source.entities)
    scene_g = gravity if scene_gravity is None else scene_gravity
    destinations = _destinations(source.entities)
    volumes: List[PushVolume] = []
    for entity in source.entities:
        classname = entity.classname
        if classname not in (PUSH_CLASSNAME, MONSTERJUMP_CLASSNAME):
            continue
        index = entity.brush_model()
        bounds = source.model_bounds(index) if index is not None else None
        if bounds is None:
            log.warning('%s references brush model %r, which the map does not '
                        'have', classname, entity.get('model'))
            continue
        origin = np.asarray(entity.vector('origin'), dtype='d')
        low = np.asarray(bounds[0], dtype='d') + origin - TRIGGER_SLACK
        high = np.asarray(bounds[1], dtype='d') + origin + TRIGGER_SLACK
        if classname == MONSTERJUMP_CLASSNAME:
            velocity = monsterjump_velocity(entity, gravity, scene_g)
            interval = MONSTERJUMP_INTERVAL
        else:
            interval = 0.0                      # §7.1: every frame
            destination = destinations.get((entity.get('target') or '').lower())
            if destination is not None:
                # The launch starts where a player stands: on top of the pad
                # brush, not on its floor -- and on the brush itself rather
                # than on the box grown by the link slack of ``§5.4``, which
                # exists for the overlap test and is not part of the geometry.
                brush_low = np.asarray(bounds[0], dtype='d') + origin
                brush_high = np.asarray(bounds[1], dtype='d') + origin
                start = np.array([(brush_low[0] + brush_high[0]) * 0.5,
                                  (brush_low[1] + brush_high[1]) * 0.5,
                                  brush_high[2]])
                velocity = aimed_velocity(start, destination, gravity)
            else:
                if entity.get('target'):
                    log.warning('%s is aimed at %r, which the map does not '
                                'define', classname, entity.get('target'))
                velocity = push_velocity(entity, gravity, scene_g)
        volumes.append(PushVolume(
            mins=low, maxs=high, velocity=velocity,
            once=bool(int(entity.number('spawnflags')) & PUSH_ONCE),
            retrigger_interval=interval, classname=classname))
    return volumes


class PushSystem:
    """Runs push volumes as physics triggers against a player-sized box.

    A sensor-only world holds one trigger body per volume and one dynamic body
    standing in for the player, posed by hand each frame.  Two constraints
    shape that: the broadphase skips pairs of two non-dynamic bodies, so the
    player proxy must be dynamic; and a body posed by hand must be kept awake
    or it stops generating events.
    """

    def __init__(self, volumes: Sequence[PushVolume],
                 player_size: Tuple[float, float, float] = PLAYER_BOX) -> None:
        self.volumes = list(volumes)
        self._events: Dict[int, str] = {}
        self._fired: Dict[int, float] = {}
        self._removed: set = set()
        self._time = 0.0
        self.world = PhysicsWorld(gravity=model.Gravity(gravity=0.0),
                                  sleep_enabled=False)
        self._body_volume: Dict[int, int] = {}
        for index, volume in enumerate(self.volumes):
            low, high = volume.scene_box()
            shape = self.world.add_shape(model.Shape.box(tuple(high - low)))
            body = self.world.add_body(
                motion=model.Motion(type=model.STATIC),
                trigger=model.Trigger(shape=shape),
                position=tuple((low + high) * 0.5))
            self._body_volume[body] = index
        size = to_scene_directions(np.array([player_size]))[0] * SCENE_SCALE
        player_shape = self.world.add_shape(model.Shape.box(tuple(np.abs(size))))
        # §5.6: the test is box-against-box, so the proxy is a box even though
        # the avatar itself is a capsule.  Dynamic with no gravity so it stays
        # exactly where it is posed.
        self.player = self.world.add_body(
            motion=model.Motion(type=model.DYNAMIC, mass=1.0, gravityFactor=0.0),
            collider=model.Collider(shape=player_shape))
        self.world.add_trigger_listener(self._on_trigger)

    def _on_trigger(self, event: str, trigger_body: int, other_body: int) -> None:
        """Record an overlap event for the volume behind ``trigger_body``."""
        if other_body != self.player:
            return
        index = self._body_volume.get(trigger_body)
        if index is not None:
            self._events[index] = event

    def update(self, dt: float, position: Any,
               noclip: bool = False) -> Optional[np.ndarray]:
        """Step the sensors and return the velocity to assign, or None.

        ``position`` is the player's scene-space centre, already moved for this
        frame: ``§7.6`` evaluates contacts after movement is resolved, so a
        caller that steps this first would ask where the player was last frame.
        ``§7.8``: a noclip player generates no contacts at all.
        """
        self._time += dt
        if noclip:
            self._events.clear()
            return None
        self._events.clear()
        self.world.position[self.player] = np.asarray(position, dtype='d')
        self.world.wake(self.player)
        self.world.step(dt)
        return self._resolve()

    def _resolve(self) -> Optional[np.ndarray]:
        """The velocity of the last volume that fired this frame, if any.

        ``§2.5``: overlapping volumes do not sum, and the one applied last in a
        frame wins.
        """
        chosen: Optional[np.ndarray] = None
        for index, _event in sorted(self._events.items()):
            if index in self._removed:
                continue
            volume = self.volumes[index]
            if volume.once:
                # §4.3: the removal is unconditional on whether anything was
                # actually pushed -- first contact of any kind destroys it.
                self._removed.add(index)
            elif volume.retrigger_interval:
                last = self._fired.get(index)
                if last is not None and self._time - last < volume.retrigger_interval:
                    continue
            self._fired[index] = self._time
            chosen = volume.scene_velocity()
        return chosen


# Kept out of ``PushVolume`` so a caller can build volumes without a physics
# world: the viewer's overlay reports what a map contains even when navigation
# is off.
def describe(volumes: Sequence[PushVolume]) -> str:
    """A one-line summary of a map's push volumes, for the viewer's overlay."""
    if not volumes:
        return 'no push volumes'
    pads = sum(1 for v in volumes if v.classname == PUSH_CLASSNAME)
    jumps = len(volumes) - pads
    frozen = sum(1 for v in volumes if not v.velocity.any())
    parts = ['%d trigger_push' % pads] if pads else []
    if jumps:
        parts.append('%d trigger_monsterjump' % jumps)
    if frozen:
        parts.append('%d with no direction (freeze volumes)' % frozen)
    return ', '.join(parts)
