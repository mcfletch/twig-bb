"""What a combatant's body is doing, and which clip shows it.

The rules already know how fast somebody is going, which way they are looking,
what they are carrying and whether they are dead. This is the *reading* of that
-- a state machine over what is known rather than a second copy of it -- and
what comes out is the clip a figure plays and the weapon in its hand.

Three things it decides that a viewer notices immediately when they are wrong:

* **Which way the body is travelling, in its own frame.** The same three metres
  a second is a walk, a backward walk or a sidestep depending on where the
  walker is *looking*, and a figure that ran forwards while it moved backwards
  is the first thing anybody sees.
* **How fast the cycle plays.** A walk authored at one speed and played at
  another is a figure skating; scaling it by the speed the body is really going
  is what pins the feet down.
* **What is in the hand.** Followed every frame from what the rules say is
  carried, so picking a different weapon up needs no event -- and kept when
  somebody dies, because a weapon that blinks out on the frame they are shot
  reads as a bug.

Nothing here draws anything or touches a scenegraph: :class:`Character` is
handed a model and asks it for clips, and :class:`Cast` holds one per
combatant. ``twig-bb-bots`` (:mod:`twig_bb.botreview`) plays the whole of it in
front of a camera, out of the game, which is how it is reviewed.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np

from . import art

log = logging.getLogger(__name__)

__all__ = [
    'Motion', 'Locomotion', 'Character', 'Cast', 'Armoury',
    'WALK_SPEED', 'RUN_SPEED', 'TURN_RATE', 'LAND_TIME',
    'MOVEMENT', 'ONE_SHOTS', 'WEAPON_FAMILY', 'AIMED', 'FORWARD', 'BUILDS',
    'MOVEMENT_FALLBACK', 'CLIP_SPEED', 'heading_in',
    'motion_of', 'weapon_clip', 'load',
]

#: Which way a figure is authored to face in its own frame. Avatar models face
#: +Z, which is the opposite of what a projectile or a weapon is authored to,
#: so it is stated here rather than shared with them.
FORWARD = (0.0, 0.0, 1.0)

#: The figures that ship with the game, in the order combatants are handed
#: them, so a match of several bots is not several copies of one person.
BUILDS = ('male_character', 'female_character')

#: Where a character model lives, relative to :data:`twig_bb.art.ASSETS`.
CHARACTERS = 'characters'

#: The movement clips the rig contract names, and which of them play once
#: rather than looping. A one-shot is held on its last frame when it runs out,
#: which is what makes ``die`` a body left on the floor rather than one that
#: springs up and dies again.
MOVEMENT = ('idle', 'walk', 'run', 'walk_back', 'strafe_left', 'strafe_right',
            'jump', 'fall', 'land', 'die', 'die_forward',
            'turn_left', 'turn_right')
ONE_SHOTS = frozenset({'jump', 'land', 'die', 'die_forward'})

#: Metres a second below which somebody is standing still, and above which
#: they are running rather than walking. Our numbers: they are a statement
#: about how the art reads at speed, not about what the physics can do.
#: How fast a body may turn to face where it is looking, in radians a second.
#: A body that arrived at a new facing the instant its owner decided on one
#: would snap round on the frame a bot noticed somebody, which reads as a
#: glitch rather than as a reaction. Fast enough to be a soldier turning,
#: slow enough to be seen.
FACE_RATE = 7.0

WALK_SPEED = 0.6
RUN_SPEED = 4.0

#: Radians a second of turn that counts as turning on the spot. Below it a
#: standing body is idle; a body that is also moving walks or runs whatever it
#: is doing with its heading.
TURN_RATE = 1.2

#: How long the landing clip is given before movement takes over again.
LAND_TIME = 0.35

#: Which weapon's clips each weapon key plays. A weapon with no stance of its
#: own borrows the nearest one that has the same number of hands in it, which
#: is why grenades are thrown from the rocket launcher's stance.
WEAPON_FAMILY: Dict[str, str] = {
    'pistol': 'pistol',
    'shotgun': 'shotgun',
    'rifle': 'rifle',
    'rocket': 'rocket',
    'grenade': 'rocket',
}

#: What to play instead, for a figure that has not got the clip its motion
#: asked for. A model authored before the directional cycles existed still
#: walks -- forwards, which is wrong, but a body that freezes because a clip is
#: missing is worse and the contract says a missing clip is not an error.
MOVEMENT_FALLBACK: Dict[str, str] = {
    'walk_back': 'walk', 'strafe_left': 'walk', 'strafe_right': 'walk',
    'run': 'walk', 'die_forward': 'die',
}

#: How fast each movement clip is authored to travel, in metres a second, so a
#: cycle can be played at the rate the body is actually going and its feet stay
#: on the ground instead of sliding over it.
CLIP_SPEED: Dict[str, float] = {
    'walk': WALK_SPEED, 'run': RUN_SPEED,
    'walk_back': WALK_SPEED, 'strafe_left': WALK_SPEED,
    'strafe_right': WALK_SPEED,
}

#: How far a clip's rate may be pushed either way before it reads as a figure
#: in fast-forward rather than one hurrying.
RATE_RANGE = (0.55, 2.1)

#: The stance a weapon nothing knows about is held in.
DEFAULT_FAMILY = 'rifle'

#: The weapons with a sighted stance. The rest are fired from the carry.
AIMED = frozenset({'pistol', 'rifle'})


@dataclass(frozen=True)
class Motion:
    """What the rules know about one body this frame.

    Everything here is already known to the arena, the walker or the command a
    bot produced, which is what keeps the state machine a *reading* of the game
    rather than a second copy of it.
    """

    #: Ground speed in metres a second. Vertical speed is not in it: a body
    #: dropping down a shaft is falling, not sprinting.
    speed: float = 0.0
    #: Whether there is floor under the feet.
    grounded: bool = True
    #: Whether it is going up rather than coming down, which is the whole
    #: difference between a jump and a fall.
    rising: bool = False
    #: Radians a second the body is turning, positive to the left. Decided by
    #: the *drawing* rather than by the rules: what the rules say is where
    #: somebody is looking, and turning is what a body does on its way there.
    turning: float = 0.0
    #: The weapon key being carried, or '' for empty-handed.
    weapon: str = ''
    #: Whether the trigger is down, and whether the sights are up.
    firing: bool = False
    aiming: bool = False
    dead: bool = False
    #: Which way the body is moving **in its own frame**: how much of the
    #: movement is across it and how much along it, as a unit pair, with
    #: ``across`` positive to the body's right. Straight ahead by default,
    #: which is what a body with nothing in view is doing by definition -- it
    #: faces the way it walks.
    #:
    #: This is what tells a walk from a backward walk from a sidestep. Without
    #: it a figure backing away from you runs at you while travelling
    #: backwards, which is the single most obvious thing wrong with a bot.
    direction: Tuple[float, float] = (0.0, 1.0)


def motion_of(walker: Any, weapon: str = '', facing: Any = None,
              **named: Any) -> Motion:
    """Read a :class:`~omi_physics.character.CharacterController` as a Motion.

    A body the physics has not been given yet -- a bot before its first tick,
    a match assembled without a world -- reads as standing still rather than
    as an error, because that is what it looks like.

    ``facing`` is the world direction the body is pointed, which is what turns
    a velocity into a *direction*: the same three metres a second is a walk, a
    backward walk or a sidestep depending on where the walker is looking, and
    only the caller knows that.
    """
    velocity = getattr(walker, 'velocity', None)
    if velocity is None:
        velocity = (0.0, 0.0, 0.0)
    x, y, z = (float(velocity[0]), float(velocity[1]), float(velocity[2]))
    speed = math.hypot(x, z)
    return Motion(speed=speed,
                  grounded=bool(getattr(walker, 'grounded', True)),
                  rising=y > 0.1 and not getattr(walker, 'grounded', True),
                  weapon=weapon, direction=heading_in((x, z), facing, speed),
                  **named)


def _flat(direction: Any) -> Any:
    """``direction`` as a unit vector in the ground plane, or None."""
    if direction is None:
        return None
    flat = np.array([float(direction[0]), 0.0, float(direction[2])])
    length = float(np.linalg.norm(flat))
    return None if length < 1e-9 else flat / length


def heading_in(velocity: Tuple[float, float], facing: Any,
               speed: float) -> Tuple[float, float]:
    """Movement in the body's own frame, as ``(across, along)``.

    ``across`` is positive to the body's right. A body with nowhere to be, or
    with nothing to face, is walking straight ahead: that is what a figure with
    no target does, since it turns to face where it is going.
    """
    if speed < 1e-6 or facing is None:
        return (0.0, 1.0)
    forward = np.asarray((float(facing[0]), float(facing[2])), dtype='d')
    length = float(np.linalg.norm(forward))
    if length < 1e-9:
        return (0.0, 1.0)
    forward = forward / length
    moving = np.asarray(velocity, dtype='d') / speed
    # The figure faces +Z in its own frame with its right hand towards -X, so
    # its right in the world is (-forward_z, forward_x).
    right = np.array([-forward[1], forward[0]])
    return (float(np.dot(moving, right)), float(np.dot(moving, forward)))


class Locomotion:
    """Which movement clip a body is playing, and why.

    Stateful for one reason: **landing**. Everything else can be read off the
    frame it happens in, but a landing is a thing that *happened* -- the frame
    the feet met the floor -- and it has to be played out for its own length
    rather than for as long as the body happens to be still.
    """

    def __init__(self, land_time: float = LAND_TIME) -> None:
        self.land_time = float(land_time)
        self.reset()

    def reset(self) -> None:
        """Start over, as a respawn does."""
        self.airborne = False
        self.landing = 0.0
        self.dead = False
        self.fell = 'die'

    def update(self, motion: Motion, dt: float) -> str:
        """The clip to play this frame, given ``motion`` over ``dt`` seconds."""
        if motion.dead and not self.dead:
            # **Which way a body falls is decided by where it was going.**
            # Somebody sprinting at you does not sit down; somebody standing,
            # or backing off, does not pitch onto their face. Read once, at
            # the moment of death, because it is a fact about that moment and
            # a corpse has no velocity to keep answering with.
            self.fell = ('die_forward'
                         if (motion.speed >= RUN_SPEED
                             and motion.direction[1] > 0.4) else 'die')
        if motion.dead:
            self.dead = True
        if self.dead:
            return self.fell
        if not motion.grounded:
            self.airborne = True
            self.landing = 0.0
            return 'jump' if motion.rising else 'fall'
        if self.airborne:
            self.airborne = False
            self.landing = self.land_time
        if self.landing > 0.0:
            self.landing -= max(0.0, float(dt))
            if self.landing > 0.0:
                return 'land'
        if motion.speed >= WALK_SPEED:
            return self.travelling(motion)
        if abs(motion.turning) >= TURN_RATE:
            return 'turn_left' if motion.turning > 0 else 'turn_right'
        return 'idle'

    @staticmethod
    def travelling(motion: Motion) -> str:
        """Which way a body on the move is going, in its own frame.

        Decided by whichever of across and along is the larger, so there is no
        threshold to sit on the edge of and flicker across: a body going
        forwards and slightly right walks forwards, and one going right and
        slightly forwards sidesteps.

        Only *forwards* tells a walk from a run. A body backing off or
        sidestepping at speed is playing the same shape faster, which is what
        the clip's own rate is for -- see :meth:`Character._play`.
        """
        across, along = motion.direction
        if abs(along) >= abs(across):
            if along < 0.0:
                return 'walk_back'
            return 'run' if motion.speed >= RUN_SPEED else 'walk'
        return 'strafe_right' if across > 0.0 else 'strafe_left'


def weapon_clip(motion: Motion) -> Optional[str]:
    """The clip the arms play, or None for a body carrying nothing.

    The dead carry nothing whatever they were holding: a corpse still aiming
    down its sights is the one pose that reads as a bug rather than as a body.
    """
    if not motion.weapon or motion.dead:
        return None
    family = WEAPON_FAMILY.get(motion.weapon, DEFAULT_FAMILY)
    if motion.firing:
        return 'fire_%s' % family
    if motion.aiming and family in AIMED:
        return 'aim_%s' % family
    return 'hold_%s' % family


class Armoury:
    """The model each weapon is drawn as in a combatant's hand, by its key.

    Loaded on first use and **shared between figures**, which is the opposite
    of the rule the bodies follow (see :class:`Cast`) and for the opposite
    reason: a weapon is not skinned and carries no per-body state, so twenty
    bots with rifles are twenty references to one subtree rather than twenty
    copies of it -- which is what lets the pass collapse them into a single
    instanced draw.

    Each model is placed by the grip **it** declares rather than by its own
    origin, so a weapon modelled about its balance point still sits in a fist:
    see ``OpenGLContext.character.attachment.mounted`` and CHARACTER-RIG.md.
    """

    #: The attachment point a carried weapon goes on, at both ends.
    POINT = 'grip'

    def __init__(self, table: Any = None) -> None:
        #: The :class:`~twig_bb.weapons.WeaponTable` that says which file each
        #: weapon is, so what a bot is seen holding is a table edit.
        self.table = table
        self.models: Dict[str, Any] = {}

    def of(self, key: str) -> Any:
        """The subtree for the weapon with that key, or None if there is none.

        A key with no weapon, no model or a model that will not load answers
        None and is remembered as None, so a missing file is looked for once
        rather than once a frame.
        """
        if not key:
            return None
        if key not in self.models:
            self.models[key] = self._load(key)
        return self.models[key]

    def _load(self, key: str) -> Any:
        weapon = None if self.table is None else self.table.by_key(key)
        relative = '' if weapon is None else str(weapon.model)
        return art.load(relative, mount=self.POINT) if relative else None


class Character:
    """One drawn body: the figure, what it is holding, and what it is playing.

    ``model`` is an :class:`~OpenGLContext.character.model.CharacterModel`, or
    None for a body with no art -- which still has a :attr:`group` to draw and
    still answers :meth:`update`, so nothing above has to ask which it got.
    """

    #: Seconds a clip takes to blend into the next one. Long enough that a
    #: walk easing into a run is a change of gait rather than a cut, short
    #: enough that a shot looks like it went off when the trigger was pulled.
    FADE = 0.16
    QUICK_FADE = 0.06

    #: The layer the weapon clips play on, over the movement underneath.
    UPPER = 'upper'

    #: What that layer is allowed to move: the arms, and nothing else.
    #:
    #: **Not the spine.** A weapon stance that owned the whole upper body would
    #: take the run's lean and the walk's counter-rotation with it, and a
    #: figure sprinting with a rifle would run bolt upright like a waiter. The
    #: arms are the part that has to stop swinging and hold something; the back
    #: is still doing what the legs are doing.
    ARMS = ('leftShoulder', 'rightShoulder')

    def __init__(self, model: Any = None, group: Any = None,
                 armoury: Any = None) -> None:
        self.model = model
        #: The scenegraph subtree to draw. The model's own where there is one.
        self.group = group if model is None else model.group
        #: Where the model for a weapon comes from; None for a figure that is
        #: never seen holding one.
        self.armoury = armoury
        #: The crowd this figure is posed with, or None for a figure that
        #: poses itself. A cast puts every figure of a build in one, so the
        #: whole cast is posed by one run of arithmetic -- see
        #: :class:`OpenGLContext.character.crowd.Crowd`.
        self.crowd: Any = None
        self.locomotion = Locomotion()
        #: Which way the body is drawn facing, which lags where its owner is
        #: looking by however long the turn takes.
        self.facing: Any = None
        self.holding: Optional[str] = None
        self._held: Any = None
        #: Whether the next clip should snap in rather than blend. True after
        #: a reset, because what a fade would blend *from* is the rest pose --
        #: and a body that comes back alive out of a T-pose is worse than the
        #: cut it was trying to avoid.
        self._fresh = True
        self._upper_mask = (frozenset() if model is None
                            else model.mask(*self.ARMS))

    # -- what it is holding -----------------------------------------------
    def hold(self, weapon: str, node: Any) -> bool:
        """Put ``node`` in the figure's weapon hand; False if it has no hand.

        Replaces whatever was there, so changing weapons is one call and never
        leaves somebody carrying two.
        """
        self.drop()
        if self.model is None or node is None:
            return False
        if self.model.attach('grip', node) is None:
            return False
        self.holding, self._held = weapon, node
        return True

    def reset(self) -> None:
        """Start over: nothing played, nothing held, nothing remembered.

        What a respawn needs. A body that comes back alive must not ease out of
        dying, and :class:`Locomotion` latches death on purpose -- so a figure
        that is not put back stays on the floor for the rest of the match while
        it walks about.
        """
        self.locomotion.reset()
        self.drop()
        self._fresh = True
        if self.model is not None:
            self.model.reset()

    def drop(self) -> None:
        """Take whatever is in the weapon hand out of it."""
        if self.model is not None and self._held is not None:
            self.model.detach('grip', self._held)
        self.holding, self._held = None, None

    def face(self, wanted: Any, dt: float) -> Tuple[Any, float]:
        """Turn towards ``wanted``, at most :data:`FACE_RATE`; where it got to.

        Answers ``(facing, turning)`` -- the direction to draw the body along
        and how fast it is turning, positive to its left. The second is what
        makes a body turning on the spot play a turn rather than stand there
        swivelling: the rules have no idea it is turning, because turning is
        something the *drawing* does on its way to where the rules pointed.
        """
        wanted = _flat(wanted)
        if wanted is None:
            return (self.facing, 0.0)
        if self.facing is None:
            self.facing = wanted
            return (self.facing, 0.0)
        across = float(self.facing[0] * wanted[2] - self.facing[2] * wanted[0])
        along = float(np.dot(self.facing, wanted))
        angle = math.atan2(across, along)
        limit = FACE_RATE * max(0.0, float(dt))
        turn = max(-limit, min(limit, angle))
        if abs(turn) < 1e-6:
            self.facing = wanted
            return (self.facing, 0.0)
        cosine, sine = math.cos(turn), math.sin(turn)
        # Rotating about the vertical, in the same handedness `heading_in` uses.
        self.facing = np.array([
            self.facing[0] * cosine - self.facing[2] * sine, 0.0,
            self.facing[0] * sine + self.facing[2] * cosine])
        return (self.facing, turn / max(dt, 1e-6))

    def carry(self, weapon: str) -> bool:
        """Hold what ``weapon`` names, taking the model from the armoury.

        Called every frame from :meth:`update`, and a no-op when it is already
        the weapon in hand -- which is what lets what a body is *seen* carrying
        follow what the rules say it carries, with nothing having to send an
        event when somebody picks a different one up.

        Answers whether the hand changed.
        """
        if (weapon or None) == self.holding:
            return False
        if not weapon:
            self.drop()
            return True
        node = None if self.armoury is None else self.armoury.of(weapon)
        return self.hold(weapon, node)

    # -- the frame --------------------------------------------------------
    def update(self, motion: Motion, dt: float) -> tuple:
        """Play what ``motion`` calls for; returns the clips it settled on.

        Returned rather than only applied so a test, and the developer
        overlay, can see what a body decided without a window.
        """
        # **Coming back from the dead is a reset.** Death latches, on purpose,
        # so that a body stays down; nothing else clears it, and a figure that
        # respawned without this would walk the rest of the match lying on its
        # face. Alive again, after having been dead, is exactly a respawn.
        if self.locomotion.dead and not motion.dead:
            self.reset()
        movement = self.locomotion.update(motion, dt)
        arms = weapon_clip(motion)
        # **The dead keep what they were holding.** They stop *aiming* it --
        # that is what `weapon_clip` answering None means -- but a weapon that
        # blinks out of existence on the frame somebody is shot is the one
        # thing here a player would call a bug outright.
        self.carry(motion.weapon)
        if self.model is not None:
            self._play(movement, arms, dt, speed=motion.speed)
        return (movement, arms)

    def _play(self, movement: str, arms: Optional[str], dt: float,
              speed: float = 0.0) -> None:
        clips = self.model.clips
        fade = 0.0 if self._fresh else self.FADE
        chosen = self.available(movement)
        if chosen is not None:
            self.model.play(chosen, fade=fade, loop=chosen not in ONE_SHOTS,
                            speed=self.rate(chosen, speed))
        self._fresh = False
        upper = self.model.layer(self.UPPER, mask=self._upper_mask)
        if arms and arms in clips:
            # A shot is a one-shot over the carry it returns to, and it is
            # faded in quickly: a recoil that eases in over a sixth of a second
            # is a recoil nobody connects to the trigger.
            upper.play(arms, loop=not arms.startswith('fire_'), fade=min(
                fade, self.QUICK_FADE if arms.startswith('fire_') else self.FADE))
        elif upper.tracks:
            upper.stop(fade=self.FADE)
        if self.crowd is None:
            # In a cast the figures are posed together, once, after every one
            # of them has said what it is playing -- see Cast.pose.
            self.model.update(dt)

    def available(self, movement: str) -> Optional[str]:
        """The clip to play for ``movement``, following the fallbacks.

        A figure authored before the directional cycles existed has no
        ``walk_back``; it walks forwards, which is wrong but is a great deal
        better than standing still while it travels.
        """
        clips = self.model.clips
        seen = set()
        name: Optional[str] = movement
        while name is not None and name not in seen:
            if name in clips:
                return name
            seen.add(name)
            name = MOVEMENT_FALLBACK.get(name)
        return None

    @staticmethod
    def rate(clip: str, speed: float) -> float:
        """How fast to play a cycle, so its feet keep up with the body.

        A walk cycle authored at one speed and played at another is a figure
        skating: the feet plant and then slide, which reads as ice rather than
        as ground. Scaling the clip's own rate by how fast the body is really
        going is what pins them. Bounded either way, because a cycle at three
        times its rate is a figure in fast-forward and one at a third is a
        figure wading.
        """
        nominal = CLIP_SPEED.get(clip)
        if not nominal or speed <= 0.0:
            return 1.0
        low, high = RATE_RANGE
        return max(low, min(high, float(speed) / nominal))


def _character_path(name: str) -> str:
    """Where the build called ``name`` lives on disk."""
    return art.path_for(os.path.join(CHARACTERS, '%s.glb' % name))


#: Metres past which a figure is drawn as its lighter mesh. Far enough that the
#: change is not something a player catches happening, near enough that a room
#: of bots is mostly drawn at the lighter one -- most of a fight is at range.
LOD_DISTANCE = 18.0

#: Suffix of the lighter mesh that ships beside each build.
LOD_SUFFIX = '_lod1'


def _level_document(name: str) -> Any:
    """The lighter mesh of a build, parsed once, or None where it ships none."""
    path = art.path_for(os.path.join(CHARACTERS, '%s%s.glb' % (name, LOD_SUFFIX)))
    if not os.path.exists(path):
        return None
    try:
        from OpenGLContext.loaders.gltf import parse_gltf
        return parse_gltf(path)
    except Exception:                       # noqa: BLE001 - art, not rules
        log.warning('could not parse the character level %s', path, exc_info=True)
        return None


def _parse_document(name: str) -> Any:
    """Parse a build's file once for a whole cast to share, or None if it will not.

    A :class:`~OpenGLContext.loaders.gltf.SharedDocument` carries the file's JSON
    parse and its decoded vertex and animation arrays, so every figure of one
    build is built from it without reading or decoding the file again.
    """
    path = _character_path(name)
    try:
        from OpenGLContext.loaders.gltf import parse_gltf
        return parse_gltf(path)
    except Exception:                       # noqa: BLE001 - art, not rules
        log.warning('could not parse the character %s', path, exc_info=True)
        return None


def load(name: str, group: Any = None, document: Any = None,
         level: Any = None) -> Character:
    """The character model called ``name``, or a body with no art.

    ``name`` is a file under ``assets/characters`` without its suffix, so the
    art a combatant is drawn as is a string in a table and never a code change
    -- which is the whole of what makes swapping the figures configuration.

    ``document`` is a shared parse of that build (:func:`_parse_document`) to
    build from, so a cast of one build reads its file once; without one the file
    is read and decoded here. ``level`` is the same for the build's lighter
    mesh, which is drawn instead beyond :data:`LOD_DISTANCE`.
    """
    try:
        from OpenGLContext.character import CharacterModel
        if document is not None:
            from OpenGLContext.loaders.gltf import load_gltf
            model = CharacterModel.from_scene(load_gltf(document=document))
        else:
            model = CharacterModel.load(_character_path(name))
        if level is not None:
            model.add_level(None, LOD_DISTANCE, document=level)
        return Character(model)
    except Exception:                       # noqa: BLE001 - art, not rules
        log.warning('could not load the character %s', name, exc_info=True)
        return Character(group=group)


class Cast:
    """A drawn figure for everybody the rules move, by combatant id.

    Made once for a match: a scenegraph rebuilt whenever somebody spawns is a
    scenegraph rebuilt during a fight, and the figures are the same people the
    whole way through. Which build each of them gets is taken round-robin from
    :data:`BUILDS`, so a room of bots is not a room of identical twins.

    Each figure is its own scenegraph even where two share a build, because a
    skinned mesh carries its own deformed vertices and its own materials -- which
    is also what lets one figure be recoloured without touching another wearing
    the same suit. What figures of one build *do* share is the file behind them:
    it is parsed once into a :class:`~OpenGLContext.loaders.gltf.SharedDocument`
    and its immutable vertex and animation data are held in common, so a bigger
    cast costs more posing but not more parsing.

    **And the posing is shared too.** The figures of a build go into one
    :class:`~OpenGLContext.character.crowd.Crowd`, so a frame poses all of them
    in one run over arrays rather than once each: on a few dozen joints almost
    all of what the arithmetic costs is setting it up. Each figure still says
    for itself what it is playing (:meth:`update`); :meth:`pose` is what turns
    all of that into skeletons, and it is called once, after.
    """

    def __init__(self, ids: Any, builds: Any = BUILDS,
                 fallback: Any = None, armoury: Any = None) -> None:
        chosen = list(builds) or list(BUILDS)
        #: One armoury for the whole cast, so a weapon is loaded once for the
        #: match however many people are carrying one.
        self.armoury = armoury
        self.figures: Dict[str, Character] = {}
        #: One crowd per build: a crowd holds figures of one document, so that
        #: a joint means the same joint in all of them.
        self.crowds: Dict[str, Any] = {}
        documents: Dict[str, Any] = {}      # build name -> its parse, done once
        levels: Dict[str, Any] = {}         # and the same for its lighter mesh
        for index, id in enumerate(ids):
            name = chosen[index % len(chosen)]
            if name not in documents:
                documents[name] = _parse_document(name)
                levels[name] = _level_document(name)
            figure = load(name, group=None if fallback is None else fallback(),
                          document=documents[name], level=levels.get(name))
            figure.armoury = armoury
            self._enlist(name, figure)
            self.figures[id] = figure

    def _enlist(self, build: str, figure: Character) -> None:
        """Put a figure in its build's crowd, where it has a model to pose.

        **Only the joints something reaches are written back.** Nothing here
        reads a combatant's joints: what a figure is holding hangs off its grip
        point, and the renderer walks to that through the scenegraph, so that
        point and the joints down to it are what have to say where they are.
        Writing the other fifty is arithmetic nobody collects -- and it is what
        lets the pose be worked out on the GPU, since only what is written has
        to come back.
        """
        if figure.model is None:
            return
        figure.model.mixer.pose_write = 'exposed'
        crowd = self.crowds.get(build)
        if crowd is None:
            from OpenGLContext.character.crowd import Crowd
            crowd = self.crowds[build] = Crowd()
        crowd.add(figure.model)
        figure.crowd = crowd

    def __len__(self) -> int:
        return len(self.figures)

    def __contains__(self, id: str) -> bool:
        return id in self.figures

    def of(self, id: str) -> Optional[Character]:
        """The figure drawn for ``id``, or None if nobody is drawing one."""
        return self.figures.get(id)

    def subtree(self, id: str) -> Any:
        """What to hang under this combatant's body transform."""
        figure = self.figures.get(id)
        return None if figure is None else figure.group

    def update(self, id: str, motion: Motion, dt: float) -> tuple:
        """Play what ``motion`` calls for on one figure."""
        figure = self.figures.get(id)
        return ('', None) if figure is None else figure.update(motion, dt)

    def face(self, id: str, wanted: Any, dt: float) -> Tuple[Any, float]:
        """Turn one figure towards ``wanted`` -- see :meth:`Character.face`."""
        figure = self.figures.get(id)
        return (None, 0.0) if figure is None else figure.face(wanted, dt)

    def pose(self, dt: float, mode: Any = None,
             budget: Optional[int] = None) -> None:
        """Pose the whole cast, once, after every figure has chosen its clips.

        ``mode`` is the rendering context, which is what lets the skeletons and
        joint palettes be composed on the GPU; without it the same arithmetic
        runs in numpy. ``budget`` caps how many figures are brought up to date
        this frame, taken in turn so none is starved.
        """
        for crowd in self.crowds.values():
            crowd.update(dt, budget=budget, mode=mode)
