"""Putting a match into a map, and driving it from a frame loop.

Everything between the rules — which are :mod:`twig_bb.arena`,
:mod:`twig_bb.combat` and :mod:`twig_bb.bots`, and know nothing about
windows — and the viewer, which has a window and should know as little about
the rules as possible.

So this is where a match is **placed**: combatants at the map's own spawn
points, bots given bodies to be seen and shot, events turned into the lines a
player reads. Each of those is a function that takes what it needs and returns
what it made, which is why the whole of the wiring is tested with no window
even though the thing it wires up has one.
"""

from __future__ import annotations

import logging
import math
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from OpenGLContext import entropy
from OpenGLContext.scenegraph.appearance import Appearance
from OpenGLContext.scenegraph.box import Box
from OpenGLContext.scenegraph.group import Group
from OpenGLContext.scenegraph.instancedshape import (
    InstancedModel, placement_matrices,
)
from OpenGLContext.scenegraph.material import Material
from OpenGLContext.scenegraph.quadrics import Cylinder, Sphere
from OpenGLContext.scenegraph.shape import Shape
from OpenGLContext.scenegraph.transform import Transform

from . import arena as arenamod
from . import art
from . import avatar
from . import blast
from . import bots as botsmod
from . import characters as charactersmod
from . import combat
from . import falling
from . import projectiles as projectilesmod

log = logging.getLogger(__name__)

__all__ = ['BOT_SPEED', 'PLAYER_ID', 'bot_bodies', 'heading_rotation',
           'item_bodies', 'item_look', 'messages', 'move_items',
           'heading_quaternions', 'move_projectiles', 'place_bots',
           'projectile_bodies', 'shoot',
           'spawn_for', 'start_match', 'step_bots', 'step_projectiles']

#: The session stream the opponents' minds are seeded from when a caller pins
#: no seed: see :func:`place_bots` and :mod:`OpenGLContext.entropy`.
BOT_STREAM = 'twig-bots'

#: How large a seed a bot is given. Comfortably inside a machine word, since
#: each bot is handed this number plus its place in the room.
BOT_SEED_BITS = 32

#: The player's own id in the match.  A fixed string rather than a name,
#: because a name is something a player types and an id is what the rules
#: address.
PLAYER_ID = 'player'

#: What a bot looks like until §5's art arrives: a capsule, plainly drawn.
#: **The capsule is the designed fallback and not an oversight** — navigation
#: and fighting have to be developable before there is any art at all, and a
#: bot with no model is still a bot.
BODY_COLOUR = (0.75, 0.25, 0.2)
BODY_HEIGHT = combat.BODY_HEIGHT
BODY_RADIUS = combat.BODY_RADIUS

#: From the feet up to the eyes.  What a camera is bound to, given a body.
EYE_OFFSET = np.array([0.0, combat.EYE_HEIGHT, 0.0])

#: How long a shot is shown for, in seconds.  Pulling a trigger is an instant
#: and a firing animation is not, so the moment is held: long enough that a
#: single shot is seen at all, short enough that it is not mistaken for a
#: burst.  Read by :func:`move_bodies` off :attr:`Combatant.firing`.
SHOT_SHOWN = 0.28

#: How near the *best* spawn point a point has to be, as a fraction of its
#: clear space, to be worth arriving at.  Below one there is variety and at
#: one there is exactly one answer -- which is what let a player stand still
#: at the far end of a level and shoot each arrival as it appeared.  Ours, and
#: chosen so that on a map with a dozen spawns several are usually in play
#: without any of them being next to whoever just killed you.
SPAWN_SPREAD = 0.7

#: How fast a bot walks, in metres per second.  Its own number rather than the
#: player's: a bot that moved exactly as fast as the player can would be
#: impossible to escape and dull to chase.  It reaches a bot as the
#: ``walkSpeed`` of the capsule :mod:`twig_bb.walkers` gives it, so a bot
#: and a player are the same body moving at different speeds rather than two
#: different ideas of what walking is.
BOT_SPEED = 3.6


def start_match(loaded: Any, setup: Any, weapons: Any,
                chooser: Optional[random.Random] = None) -> arenamod.Arena:
    """Build the match ``setup`` describes, in ``loaded``.

    The player takes the map's first spawn point, which is the one its author
    put first.  **Each bot then goes wherever a respawn would put it**, by the
    same :func:`spawn_for` rule: away from everybody already placed, and
    chosen among the points that qualify rather than always the same one.
    Without that, two matches on one level open identically -- the opening
    thirty seconds of a fight are the part a player replays most, and they
    were the part that never changed.

    A map with fewer spawn points than the match has fighters simply reuses
    them, which is common on a small level and better than refusing to start.
    """
    match = arenamod.Arena(weapons=weapons, fragLimit=int(setup.fragLimit),
                           timeLimit=float(setup.timeLimit))
    spawns = _spawns(loaded)
    match.add(PLAYER_ID, position=spawns[0], name='You')
    for index in range(max(0, int(setup.bots))):
        id = 'bot%d' % (index + 1,)
        where = spawn_for(spawns, match, id, chooser=chooser)
        match.add(id, position=spawns[0] if where is None else where,
                  bot=True, difficulty=str(setup.difficulty),
                  name='Bot %d' % (index + 1,))
    return match


def _spawns(loaded: Any) -> List[np.ndarray]:
    """Every spawn point of a map as a place to *stand*.

    A map's spawn entity does not mark the floor, and everything in the arena
    is addressed by its feet — that is where a capsule sits and what a shot at
    the legs meets.  The correction is
    :func:`twig_bb.avatar.feet_of`, which is the *same* one the camera's
    own spawn goes through: dropping by a different amount here is what put
    every bot a metre inside the floor, where nothing could dig them out
    because nothing was trying to.
    """
    found = [avatar.feet_of(spawn.position)
             for spawn in (loaded.spawn_points() if loaded is not None else [])]
    return found or [np.zeros(3)]


def spawn_for(spawns: Sequence[np.ndarray], match: arenamod.Arena,
              id: str, chooser: Optional[random.Random] = None,
              spread: float = SPAWN_SPREAD) -> Optional[np.ndarray]:
    """Where ``id`` should come back, as a place to stand.

    **One of the spawn points far from everybody currently alive**, chosen at
    random among them.  Two failures are being avoided at once and they pull
    in opposite directions.  A respawn that always chose the same point put
    the whole match on one square -- standing inside one another, and shot
    again before the screen has settled.  But a respawn that always chose the
    *furthest* point is just as predictable: a player who stands still waits at
    the far end of the level and shoots each arrival as it appears, and the
    opponents look as though they are on rails.

    Distance to the *nearest* living combatant is what is measured, not the
    total: a point far from the crowd but touching one opponent is the worst
    place in the level to arrive, and a sum would call it a good one.  Any
    point within :data:`SPAWN_SPREAD` of the best is then as good as the best,
    and one of those is taken at random.

    ``chooser`` is the caller's own generator, so a match replays from its
    inputs; without one the module's is used, which is right for a one-off.

    The one coming back is left out of the reckoning.  They are either dead --
    and so nowhere -- or, if this is being used to place them at the start of a
    match, standing at a position that is about to be replaced.
    """
    if not len(spawns):
        return None
    points = [np.asarray(spawn, dtype='d') for spawn in spawns]
    others = [np.asarray(one.position, dtype='d') for one in
              (match.combatant(other) for other in match.ids())
              if one is not None and one.alive and one.id != id]
    if not others:
        # Nobody to be far from: every point is as good as every other, and a
        # match that always opened on the same one would open the same way.
        return (chooser or random).choice(points)
    crowd = np.asarray(others)
    room = [float(np.min(np.linalg.norm(crowd - spawn, axis=1)))
            for spawn in points]
    best = max(room)
    good = [spawn for spawn, clear in zip(points, room, strict=True)
            if clear >= best * max(0.0, min(1.0, float(spread)))]
    return (chooser or random).choice(good)


def place_bots(match: arenamod.Arena, seed: Optional[int] = None,
               projectiles: Optional[Any] = None) -> Dict[str, botsmod.Bot]:
    """One mind per bot in the match, by id.

    Each is given the match's own weapon table, so a bot chooses from exactly
    what the player can carry — and ``projectiles`` so it can tell a rocket
    from a rifle and keep out of its own blast.

    ``seed`` pins the whole room of them, which is what a test does with it;
    each bot is given that number plus its place in the room, so no two of them
    arrive facing the same way.  Without one the numbers come from the
    **session's** own stream (:mod:`OpenGLContext.entropy`), so a match staged
    twice in one session is two different matches while a session run again
    from its seed stages exactly the one it staged before.
    """
    if seed is None:
        seed = entropy.randomizer(BOT_STREAM).getrandbits(BOT_SEED_BITS)
    return {one.id: botsmod.Bot(one.id, difficulty=one.difficulty,
                                seed=seed + index,
                                weapons=match.weapons,
                                projectiles=projectiles)
            for index, one in enumerate(match.bots())}


def step_bots(world: Any, match: arenamod.Arena,
              minds: Dict[str, botsmod.Bot], dt: float,
              weapon: Any, seed: Optional[int] = None,
              surfaces: Optional[Any] = None,
              flight: Optional[Any] = None,
              walking: Optional[Any] = None) -> None:
    """Run every bot's mind for one tick and apply what it decided.

    The command a bot produces is consumed here, and the same shape of record
    is what a key press and — later — a packet produce, which is the whole
    point of a bot deciding rather than acting.

    ``surfaces`` is the map's :class:`~twig_bb.collision.MapCollision`, so
    that a bot's shots report the material they met exactly as the player's do
    — a bot firing at a wall behind the player is one of the sounds that tells
    the player they are being shot at.

    ``walking`` is the :class:`~twig_bb.walkers.Walkers` that gives each of
    them a body.  Without one a bot has no way to be moved at all and simply
    stands and fights, which is what a match assembled without a physics world
    can honestly do.
    """
    # Whether two people can see each other is one fact about the pair, and in
    # a tick where several of them look around, each pair would otherwise be
    # cast twice -- once from each end of the same segment.  The memo lives for
    # this tick only: anybody may have moved by the next one.
    seen: Dict[tuple, bool] = {}
    for id, mind in minds.items():
        one = match.combatant(id)
        if one is None or not one.alive:
            continue
        command = mind.think(world, match, dt, seen=seen)
        _apply(world, match, one, command, weapon, dt, seed, surfaces,
               flight, walking)


def _apply(world: Any, match: arenamod.Arena, one: Any, command: Any,
           weapon: Any, dt: float, seed: Optional[int],
           surfaces: Optional[Any] = None,
           flight: Optional[Any] = None,
           walking: Optional[Any] = None) -> None:
    """Turn one bot's command into movement, shots and a direction to face."""
    # Where a bot is looking is part of what it decided, and the only record of
    # it that outlives the tick: its mind is the AI's business, its facing is
    # the match's, and what draws a body reads the match.
    # Let go of it again when there is nothing in view: a facing that only
    # ever gained values is a bot that saw somebody once and then walked
    # sideways for the rest of the match, still pointing at where they were.
    one.facing = (np.asarray(command.aim, dtype='d') if command.aim is not None
                  else np.zeros(3))
    if walking is not None:
        # Every tick, whether or not it wanted to move: gravity, a slope and
        # whatever a burst threw it with do not wait for a decision.
        _shoved(match, one, walking)
        one.position = walking.walk(one.id, one.position, command.move, dt)
    if command.fired and command.aim is not None:
        chosen = _wanted(match, command, weapon)
        # A bot pays for its shots out of the loadout it carries, exactly as a
        # player does: a round it cannot afford is an empty click, not a free
        # rocket.  Its mind already prefers a weapon it can fire (see
        # `Bot._chosen`), so this bites only once it has emptied everything.
        if chosen is None or not one.player.spend(chosen):
            return
        one.firing = SHOT_SHOWN
        shoot(world, match, one.id, chosen,
              origin=one.position + EYE_OFFSET,
              direction=command.aim, spread=float(chosen.restSpread),
              seed=seed, surfaces=surfaces, flight=flight)


def _wanted(match: arenamod.Arena, command: Any, weapon: Any) -> Any:
    """The weapon a bot's command asked for, or the one it was handed.

    A command naming nothing is a bot with no loadout to choose from, and a
    command naming something the table does not have is a mismatch worth
    ignoring rather than crashing over -- either way what it was given is a
    weapon and firing it is better than not firing.
    """
    if not command.weapon:
        return weapon
    return match.weapons.by_key(command.weapon) or weapon


def shoot(world: Any, match: arenamod.Arena, shooter: str, weapon: Any,
          origin: Any, direction: Any, spread: float = 0.0,
          seed: Optional[int] = None,
          surfaces: Optional[Any] = None,
          flight: Optional[Any] = None) -> None:
    """Fire one shot, however this weapon fires.

    **The one place that decides between a trace and a throw**, so the player
    and every bot take the same road to it and a weapon that changes from
    hitscan to a projectile is a table edit.  Which it is is the weapon's
    ``projectile`` field and nothing else.

    ``flight`` is the batch a projectile joins; without one a projectile
    weapon does nothing at all, which is what a match built with no batch
    should do rather than crash.
    """
    thrown = str(weapon.projectile)
    if not thrown:
        combat.fire(world, match, shooter, weapon, origin=origin,
                    direction=direction, spread=spread, seed=seed,
                    surfaces=surfaces)
        return
    if flight is None:
        return
    kind = flight.table.by_key(thrown)
    if kind is None:
        log.warning('%s throws a %r and nothing in the table is one',
                    weapon.key, thrown)
        return
    # Announced whether or not the batch had room: a launcher that made no
    # sound when it was full would read as a broken trigger.
    match.fired(shooter, weapon.key, origin=origin, direction=direction)
    flight.launch(kind, origin=origin, direction=direction, owner=shooter)


def step_projectiles(world: Any, match: arenamod.Arena, flight: Any,
                     dt: float) -> List[Any]:
    """Fly everything in the air one tick, and let what lands go off.

    The two halves in the order they have to happen: a projectile finds out
    what it met, and then its burst finds out who was standing near that.
    Returns what went off, which is what a test reads.
    """
    if flight is None:
        return []
    gone = flight.step(world, match, dt)
    if gone:
        blast.answer(world, match, flight.table, gone)
    return gone


def _shoved(match: arenamod.Arena, one: Any, walking: Any) -> None:
    """Hand a bot whatever a burst threw it with, through its own capsule.

    **The controller's impulse**, which is what a jump pad uses and what the
    player takes a rocket with, so a bot is blown off a ledge by the same
    machinery a player is -- in all three axes rather than the horizontal
    only, which is all a bot that was a bare position could express.

    Spent rather than applied every tick: the arena says how hard somebody was
    shoved and knows nothing about a capsule, and the capsule carries the
    speed from there.
    """
    push = match.spend_push(one.id)
    if float(np.linalg.norm(push)) < 1e-6:
        return
    walking.shove(one.id, push)


def bot_bodies(match: arenamod.Arena,
               cast: Optional[Any] = None) -> Tuple[Group, Dict[str, Transform]]:
    """A group holding a body for each bot, and the transforms to move them.

    Returned together because the caller needs both: the group goes in the
    scene once, and the transforms are written every frame.

    ``cast`` is a :class:`twig_bb.characters.Cast`, and each bot is drawn as
    its figure.  Without one -- and for a bot the cast has no figure for --
    the body is a capsule, which is what keeps a match playable with no art at
    all: §6 was built against it and it is still the answer when a model will
    not resolve.
    """
    group = Group(children=[])
    bodies: Dict[str, Transform] = {}
    for one in match.bots():
        drawn = None if cast is None else cast.subtree(one.id)
        body = Transform(translation=tuple(one.position),
                         children=[drawn] if drawn is not None else capsule())
        bodies[one.id] = body
        group.children = list(group.children) + [body]
    return (group, bodies)


def capsule() -> List[Any]:
    """The parts of a stand-in body, standing on its feet."""
    look = Appearance(material=Material(diffuseColor=BODY_COLOUR,
                                        shininess=0.2))
    middle = max(BODY_HEIGHT - 2 * BODY_RADIUS, 0.1)
    return [
        Transform(translation=(0.0, BODY_HEIGHT * 0.5, 0.0), children=[
            Shape(geometry=Cylinder(radius=BODY_RADIUS, height=middle),
                  appearance=look)]),
        Transform(translation=(0.0, BODY_RADIUS, 0.0), children=[
            Shape(geometry=Sphere(radius=BODY_RADIUS), appearance=look)]),
        Transform(translation=(0.0, BODY_HEIGHT - BODY_RADIUS, 0.0), children=[
            Shape(geometry=Sphere(radius=BODY_RADIUS), appearance=look)]),
    ]


#: How big the fallback ball is drawn, in metres.  Larger than a projectile's
#: collision radius on purpose: what a player has to do with an incoming rocket
#: is *see* it in time, and a body the size of its hit box is a dot.  Each
#: kind's own model and the size it is drawn at are in
#: :func:`twig_bb.projectiles.default_table`, with the rest of its numbers.
PROJECTILE_DRAW_RADIUS = 0.16

#: What that ball looks like: hot, and bright enough to read against a dark
#: level.
PROJECTILE_COLOUR = (1.0, 0.62, 0.2)

#: Which way the projectile model is authored, in its own frame.  glTF calls
#: -Z forward and the model leaves Blender already pointing that way, so
#: aiming one along its flight is a turn from here onto its velocity.
MODEL_FORWARD = (0.0, 0.0, -1.0)

#: Where a body is parked when nothing is using it.  Far below any level, so
#: it is out of every frustum without the scene having to be edited.
OFFSTAGE = (0.0, -10_000.0, 0.0)


def _spark() -> Shape:
    """A glowing ball, for when the rocket model will not load.

    Something in flight that cannot be seen is a shot that reads as not having
    been fired, so the projectile is the one piece of art with a shape of its
    own to fall back on.
    """
    look = Appearance(material=Material(diffuseColor=PROJECTILE_COLOUR,
                                        emissiveColor=PROJECTILE_COLOUR,
                                        shininess=0.6))
    return Shape(geometry=Sphere(radius=PROJECTILE_DRAW_RADIUS), appearance=look)


def projectile_bodies(table: Any = None
                      ) -> Tuple[Group, Dict[str, InstancedModel]]:
    """Bodies for things in flight, keyed by which kind of thing they are.

    One :class:`~OpenGLContext.scenegraph.instancedshape.InstancedModel` per
    kind, made once: the model's parts are the nodes, and how many are in the
    air is an array of matrices on them rather than a subtree apiece.  What the
    render pass gathers is therefore a handful of objects whatever the batch's
    capacity, and firing edits no scenegraph -- a level that has never seen a
    rocket costs the same as one in the middle of a firefight.

    A model per kind rather than one that changes shape, because a rocket and a
    grenade are different models; each is placed from its own array.
    """
    if table is None:
        table = projectilesmod.default_table()
    bodies: Dict[str, InstancedModel] = {}
    children: List[Any] = []
    for kind in table.kinds:
        look = art.load(str(kind.model)) if str(kind.model) else None
        if look is None:
            look = _spark()
        model = InstancedModel(model=look)
        bodies[str(kind.key)] = model
        children.append(model)
    return (Group(children=children), bodies)


def heading_quaternions(directions: Any,
                        forward: Sequence[float] = MODEL_FORWARD) -> np.ndarray:
    """``(N,4)`` ``(x,y,z,w)`` rotations turning ``forward`` onto each direction.

    The batch form of :func:`heading_rotation`, for placing a whole set of
    projectiles in one pass.  A direction of nothing leaves the model facing the
    way it was authored, and one pointing straight backwards is turned about an
    axis picked across the model, since every axis across it turns it equally.
    """
    headings = np.asarray(directions, dtype='d').reshape(-1, 3)
    lengths = np.linalg.norm(headings, axis=1)
    safe = lengths > 0.0
    unit = np.zeros_like(headings)
    unit[safe] = headings[safe] / lengths[safe, None]
    facing = np.asarray(forward, dtype='d')
    axes = np.cross(np.broadcast_to(facing, unit.shape), unit)
    sines = np.linalg.norm(axes, axis=1)
    angles = np.arctan2(sines, unit @ facing)
    # Straight backwards: no axis comes out of the cross product, so one is
    # chosen across the model rather than derived from it.
    across = (1.0, 0.0, 0.0) if abs(facing[0]) < 0.9 else (0.0, 1.0, 0.0)
    reversed_ = safe & (sines < 1e-9) & (angles > 1e-9)
    if reversed_.any():
        axes[reversed_] = np.cross(facing, np.asarray(across, dtype='d'))
        sines = np.linalg.norm(axes, axis=1)
    turning = safe & (sines > 0.0)
    quaternions = np.zeros((len(headings), 4), dtype='d')
    quaternions[:, 3] = 1.0
    if turning.any():
        unit_axes = axes[turning] / np.linalg.norm(axes[turning], axis=1)[:, None]
        half = angles[turning] / 2.0
        quaternions[turning, :3] = unit_axes * np.sin(half)[:, None]
        quaternions[turning, 3] = np.cos(half)
    return quaternions


def heading_rotation(direction: Sequence[float],
                     forward: Sequence[float] = MODEL_FORWARD,
                     ) -> Tuple[float, float, float, float]:
    """The axis and angle that turn ``forward`` onto ``direction``.

    ``forward`` is which way the model is authored to face in its own frame,
    which is not the same answer for everything: a projectile leaves Blender
    pointing down -Z and a figure, following the avatar conventions, faces +Z.

    A rotation rather than a matrix because that is what a ``Transform`` holds.
    Something going nowhere is left alone: a projectile with no velocity has no
    heading to be pointed along, and spinning it to some default would be a
    visible flick at the moment one is launched.
    """
    heading = np.asarray(direction, dtype=float)[:3]
    length = float(np.linalg.norm(heading))
    if length == 0.0:
        return (0.0, 1.0, 0.0, 0.0)
    heading = heading / length
    facing = np.asarray(forward, dtype=float)
    axis = np.cross(facing, heading)
    angle = math.atan2(float(np.linalg.norm(axis)),
                       float(np.dot(facing, heading)))
    if float(np.linalg.norm(axis)) < 1e-9:
        if angle < 1e-9:                    # already facing that way
            return (0.0, 1.0, 0.0, 0.0)
        # Straight backwards: every axis across the model turns it equally, so
        # one has to be picked rather than derived.
        across = (1.0, 0.0, 0.0) if abs(facing[0]) < 0.9 else (0.0, 1.0, 0.0)
        axis = np.cross(facing, np.asarray(across, dtype=float))
    axis = axis / float(np.linalg.norm(axis))
    return (float(axis[0]), float(axis[1]), float(axis[2]), float(angle))


def move_projectiles(flight: Any, bodies: Dict[str, InstancedModel]) -> None:
    """Place each kind's model once per projectile of that kind in the air.

    The batch keeps its living entries packed at the front, but *its* slot
    numbering mixes the kinds together, so the slots are sorted by kind and each
    kind's model is handed its own set in one go.  A kind with nothing in the
    air is placed nowhere, which is what draws nothing.
    """
    live = 0 if flight is None else len(flight)
    slots: Dict[str, List[int]] = {key: [] for key in bodies}
    for slot in range(live):
        kind = flight.kind_at(slot)
        if kind is not None and str(kind.key) in slots:
            slots[str(kind.key)].append(slot)
    scales = {}
    if flight is not None:
        for kind in getattr(flight.table, 'kinds', ()):
            scales[str(kind.key)] = float(kind.modelScale)
    for key, model in bodies.items():
        mine = slots[key]
        if not mine:
            model.place(())
            continue
        index = np.asarray(mine, dtype='i4')
        scale = scales.get(key, 1.0)
        model.place(placement_matrices(
            translations=flight.position[index],
            rotations=heading_quaternions(flight.velocity[index]),
            scales=np.full((len(index), 3), scale, dtype='f'),
        ))


#: How big a pickup is drawn, in metres, and how fast it turns in radians a
#: second.  A pickup has to be **recognisable across a room** — half of what a
#: level's circuit is worth is knowing where the armour is before you commit
#: to the jump — so it is drawn larger than it collides and it moves, because
#: a still object at that distance reads as part of the wall.
ITEM_SIZE = 0.36
ITEM_SPIN = 1.6

#: How far away a pickup has to be, in metres, before it is turned in steps
#: rather than continuously.  "Across a room" is what the turning is *for*, and
#: thirty metres is past the far wall of the largest room these maps have.  At
#: that distance a pickup is under a dozen pixels across on a 1080p screen, so
#: a step of the turn moves an edge by a fraction of one.
ITEM_SPIN_RANGE = 30.0

#: How often a pickup past :data:`ITEM_SPIN_RANGE` is turned, in steps a second.
#: It still tracks the same clock, so approaching one shows no jump: what
#: changes with distance is the size of the step, not the angle it is at.
ITEM_SPIN_FAR_RATE = 5.0

#: How much of a pickup's own colour it emits regardless of what is lighting
#: it.  A map places **no dynamic lights at all** — both families bake their
#: lighting into lightmaps — so an item dropped into an unlit corner is a black
#: shape, and the one thing a pickup may never be is hard to see.  A floor
#: rather than a light: it lifts the item and touches nothing else.
ITEM_GLOW = 0.45


def item_look(kind: Any) -> Any:
    """What one kind of pickup is drawn as: its model, or a box in its colour.

    Shared by every pickup of that kind rather than built per item — a map
    places fifty of them and most maps place several of a kind, so this is the
    difference between one medikit in the scenegraph and eight.

    **A box is still the answer for a kind whose art does not exist yet**, and
    is a designed fallback rather than an error: a level's item circuit has to
    be playable before every pickup has been modelled, which is the same reason
    the bots are capsules.  A model that fails to load falls back to it too, so
    a corrupt ``.glb`` costs the item its shape and not the match.

    The placement is one node and not three: a `Transform` scales about its own
    origin, so translating by ``modelScale × modelOffset`` puts the middle of
    the model on the middle of the pickup in a single step.
    """
    colour = tuple(float(value) for value in kind.colour)
    name = str(getattr(kind, 'model', ''))
    if name:
        model = art.load(name)
        if model is not None:
            if bool(getattr(kind, 'tinted', True)):
                art.recolour(model, colour, glow=ITEM_GLOW)
            else:
                art.brighten(model, ITEM_GLOW)
            scale = float(kind.modelScale)
            return Transform(
                translation=tuple(scale * float(value)
                                  for value in kind.modelOffset),
                scale=(scale, scale, scale),
                children=[model])
    look = Appearance(material=Material(diffuseColor=colour,
                                        emissiveColor=tuple(
                                            value * ITEM_GLOW
                                            for value in colour),
                                        shininess=0.4))
    return Shape(geometry=Box(size=(ITEM_SIZE,) * 3), appearance=look)


def item_bodies(pickups: Any) -> Tuple[Group, List[Transform]]:
    """A group holding a body for each pickup, and the transforms to move them.

    One :func:`item_look` each, shared between every pickup of a kind, in a
    transform of its own that :func:`move_items` turns and parks.

    Made once and parked out of sight when taken, rather than added and
    removed: a map places fifty of these on average
    (``SPEC-Q3ENTITIES §3.1.1``) and a scenegraph edited every time one is
    collected is one rebuilt through every firefight.
    """
    bodies: List[Transform] = []
    looks: Dict[str, Any] = {}
    for item in (pickups.items if pickups is not None else []):
        key = str(item.kind.key)
        if key not in looks:
            looks[key] = item_look(item.kind)
        bodies.append(Transform(
            translation=tuple(float(value) for value in item.position),
            children=[looks[key]]))
    return (Group(children=list(bodies)), bodies)


def move_items(pickups: Any, bodies: List[Transform], now: float,
               near: Any = None) -> None:
    """Turn each pickup on the spot, and park the ones that have been taken.

    ``now`` is a clock the caller reads, because turning is presentation and
    the rules must not know what time it is; the rules decide only whether a
    thing is *there*.

    ``near`` is where the viewer is, and decides **how often** a pickup is
    turned rather than whether it turns.  Writing a transform is not the cost:
    the cost is that every part of the model beneath it then has its place in
    the world worked out again, and a map places fifty of these
    (``SPEC-Q3ENTITIES §3.1.1``).  Turning all of them on every frame was the
    single largest thing the renderer did per frame with nothing else going on.

    So a pickup far enough away that its turning cannot be *read* is turned at
    :data:`ITEM_SPIN_FAR_RATE` instead, in steps rather than continuously.  It
    is still turning, and it is still at the angle the clock says, so walking
    towards one shows no jump -- only the size of the step it moves in changes,
    and at that distance a step is a fraction of a pixel.  A caller with no
    viewer to measure from turns everything every time, which is what a test and
    a fly-through both want.
    """
    live = pickups.items if pickups is not None else []
    angle = (now * ITEM_SPIN) % (2.0 * math.pi)
    # The same angle, held for a step: floor to the far rate's tick so the value
    # written is unchanged between ticks and the assignment below is skipped.
    stepped = ((math.floor(now * ITEM_SPIN_FAR_RATE) / ITEM_SPIN_FAR_RATE)
               * ITEM_SPIN) % (2.0 * math.pi)
    watching = None if near is None else tuple(float(v) for v in near[:3])
    for slot, body in enumerate(bodies):
        if slot >= len(live) or not live[slot].available:
            if tuple(body.translation) != OFFSTAGE:
                body.translation = OFFSTAGE
            continue
        item = live[slot]
        where = tuple(float(value) for value in item.position)
        if tuple(body.translation) != where:
            body.translation = where
        turn = angle
        if watching is not None:
            gap = ((where[0] - watching[0]) ** 2 + (where[1] - watching[1]) ** 2
                   + (where[2] - watching[2]) ** 2)
            if gap > ITEM_SPIN_RANGE * ITEM_SPIN_RANGE:
                turn = stepped
        spun = (0.0, 1.0, 0.0, turn)
        if tuple(body.rotation) != spun:
            body.rotation = spun


def move_bodies(match: arenamod.Arena, bodies: Dict[str, Transform],
                cast: Optional[Any] = None, walking: Optional[Any] = None,
                dt: float = 0.0, mode: Any = None) -> None:
    """Put each bot's body where the rules say it is, and play what it is doing.

    A dead bot is moved out of sight rather than removed, because editing the
    scenegraph every time somebody dies costs a rebuild of what the pass has
    gathered — and they are coming back in a second and a half.  A dying one is
    left where it fell for as long as its death clip runs, because a body that
    vanishes on the frame it is killed reads as a bug rather than as a kill.

    With a ``cast``, each figure is also turned to face the way it is moving
    and asked to play the clip its motion calls for.  ``walking`` is the
    :class:`~twig_bb.walkers.Walkers` the bodies move in, which is what knows
    a bot's speed and whether it is on the ground.
    """
    for id, body in bodies.items():
        one = match.combatant(id)
        if one is None:
            continue
        if one.alive:
            body.translation = tuple(float(value) for value in one.position)
        elif cast is None:
            body.translation = (0.0, -10_000.0, 0.0)
        if cast is None:
            continue
        walker = None if walking is None else walking.of(id)
        # **Everything the drawing reads comes from the rules' own record.**
        # What is in somebody's hands is what they selected; whether the
        # trigger is down is a moment the rules noticed and held on to.
        shooting = float(getattr(one, 'firing', 0.0) or 0.0)
        one.firing = max(0.0, shooting - max(0.0, float(dt)))
        # **Where it is drawn facing lags where its owner is looking.** A body
        # that arrived at a new facing on the frame its owner decided on one
        # would snap round the moment a bot noticed somebody; and turning is
        # something the drawing does on its way there, which the rules know
        # nothing about -- so what it is doing while it turns comes back here
        # rather than going in.
        facing, turning = cast.face(id, _wanted_facing(one, walker), dt)
        motion = charactersmod.motion_of(
            walker, weapon=str(one.player.selected or ''),
            firing=shooting > 0.0, dead=not one.alive,
            facing=facing, turning=turning)
        cast.update(id, motion, dt)
        if facing is not None:
            body.rotation = heading_rotation(facing,
                                             forward=charactersmod.FORWARD)
    if cast is not None and hasattr(cast, 'pose'):
        # Every figure has now said what it is playing; posing them is one run
        # of arithmetic over the lot rather than one each.  How far each is from
        # the player decides how often its limbs are worked out -- see
        # :meth:`twig_bb.characters.Cast.pose`; where it *is* was set above,
        # every frame, whatever the distance.
        watcher = match.combatant(PLAYER_ID)
        gaps = None
        if watcher is not None:
            here = np.asarray(watcher.position, dtype='d')
            gaps = {}
            for id in match.ids():
                one = match.combatant(id)
                if one is not None:
                    gaps[id] = float(np.linalg.norm(
                        np.asarray(one.position, dtype='d') - here))
        cast.pose(dt, mode=mode, distances=gaps)


def _wanted_facing(one: Any, walker: Any) -> Optional[Tuple[float, ...]]:
    """Which way a body wants to be facing, or None for no opinion.

    **Where somebody is looking beats where they are going.** A combatant with
    something in view faces it, whether they are standing, backing off or
    sidestepping across you -- which is what makes a figure shooting at you
    look like it is shooting at you, and what the directional walk cycles are
    for. With nothing in view there is nothing to face but the way they are
    walking, and a body going nowhere at all is left alone rather than snapped
    to some default.
    """
    facing = getattr(one, 'facing', None)
    if facing is not None and float(np.linalg.norm(np.asarray(facing[:3],
                                                              dtype=float))):
        return (float(facing[0]), 0.0, float(facing[2]))
    if walker is None:
        return None
    across = (float(walker.velocity[0]), 0.0, float(walker.velocity[2]))
    if math.hypot(across[0], across[2]) >= charactersmod.WALK_SPEED:
        return across
    return None


def messages(events: Sequence[Any], match: arenamod.Arena) -> List[str]:
    """What a player should be *told* about what just happened.

    Deaths and the end of the match; not every hit, because a line per bullet
    is a wall of text over the middle of a fight.  Hits are shown by the
    reticule's hit mark, which is what that is for.
    """
    lines: List[str] = []
    for event in events:
        if isinstance(event, arenamod.Death):
            lines.append(_death_line(event, match))
        elif isinstance(event, arenamod.MatchOver):
            winner = match.combatant(event.winner)
            lines.append('MATCH OVER — %s wins (%s)'
                         % (winner.name if winner else 'nobody', event.reason))
    return lines


#: How a death by something that is not a weapon is phrased.  A map's own
#: hazards read better named than as a bare "died", and the cause travels with
#: the event so nothing has to guess at it from an empty killer.
DEATH_CAUSES = {
    'lava': '%s burned up in the lava',
    'slime': '%s dissolved in the slime',
    falling.FELL: '%s fell out of the world',
}


def _death_line(event: arenamod.Death, match: arenamod.Arena) -> str:
    """One death, phrased from the player's point of view."""
    died = match.combatant(event.target)
    killer = match.combatant(event.by)
    who = died.name if died else event.target
    if event.cause:
        return DEATH_CAUSES.get(event.cause, '%s died') % (who,)
    if event.by == event.target or not killer:
        return '%s died' % (who,)
    if event.by == PLAYER_ID:
        return 'You fragged %s' % (who,)
    if event.target == PLAYER_ID:
        return '%s fragged you' % (killer.name,)
    return '%s fragged %s' % (killer.name, who)


def scoreboard_lines(match: arenamod.Arena) -> List[str]:
    """The scoreboard, as lines a HUD can show."""
    lines = ['%-16s %5s %6s' % ('', 'FRAGS', 'DEATHS')]
    for row in match.scoreboard():
        lines.append('%-16s %5d %6d' % (row.name[:16], row.frags, row.deaths))
    return lines
