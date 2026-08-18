"""What a combatant's body is doing, and the clip that shows it.

A body in a match is three things that have to agree: the capsule it *walks*
in (:mod:`twig_bb.walkers`), the capsule a shot *meets*
(:mod:`twig_bb.avatar`), and the figure it is *drawn* as. This is the third,
and the only part of it that is a rule of this game rather than machinery:
which of the rig's clips a body is playing, given what the rules already know
about it.

**The engine plays; this decides.** Blending one clip into the next, layering
the arms over the legs and hanging a weapon on a hand are
:mod:`OpenGLContext.character`'s job and would be the same in any game. What
is ours is the vocabulary -- ``idle`` / ``walk`` / ``run`` / ``jump`` /
``fall`` / ``land`` / ``die`` / ``turn_left`` / ``turn_right``, and
``hold_`` / ``aim_`` / ``fire_`` per weapon -- and the thresholds a body
crosses between them. Both are written down in
[CHARACTER-RIG.md](../CHARACTER-RIG.md), which is what a
contributor authoring a character makes their model satisfy.

**Two layers, because a body does two things at once.** The legs run while the
arms fire, so the movement clip plays over the whole body and the weapon clip
plays over an ``upper`` layer masked to the spine and everything above it. A
figure that stopped running to pull its trigger would read as a game that
cannot chew gum and walk.

**No art is not an error.** :func:`load` gives back a body drawn as a plain
capsule when a model will not resolve, and everything above still runs -- the
state machine is data, and a match is decided by rules rather than by whether
a ``.glb`` was there.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from . import art

log = logging.getLogger(__name__)

__all__ = [
    'Motion', 'Locomotion', 'Character', 'Cast', 'Armoury',
    'WALK_SPEED', 'RUN_SPEED', 'TURN_RATE', 'LAND_TIME',
    'MOVEMENT', 'ONE_SHOTS', 'WEAPON_FAMILY', 'AIMED', 'FORWARD', 'BUILDS',
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
MOVEMENT = ('idle', 'walk', 'run', 'jump', 'fall', 'land', 'die',
            'turn_left', 'turn_right')
ONE_SHOTS = frozenset({'jump', 'land', 'die'})

#: Metres a second below which somebody is standing still, and above which
#: they are running rather than walking. Our numbers: they are a statement
#: about how the art reads at speed, not about what the physics can do.
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
    #: Radians a second of turn, positive to the left.
    turning: float = 0.0
    #: The weapon key being carried, or '' for empty-handed.
    weapon: str = ''
    #: Whether the trigger is down, and whether the sights are up.
    firing: bool = False
    aiming: bool = False
    dead: bool = False


def motion_of(walker: Any, weapon: str = '', **named: Any) -> Motion:
    """Read a :class:`~omi_physics.character.CharacterController` as a Motion.

    A body the physics has not been given yet -- a bot before its first tick,
    a match assembled without a world -- reads as standing still rather than
    as an error, because that is what it looks like.
    """
    velocity = getattr(walker, 'velocity', None) or (0.0, 0.0, 0.0)
    x, y, z = (float(velocity[0]), float(velocity[1]), float(velocity[2]))
    return Motion(speed=math.hypot(x, z),
                  grounded=bool(getattr(walker, 'grounded', True)),
                  rising=y > 0.1 and not getattr(walker, 'grounded', True),
                  weapon=weapon, **named)


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

    def update(self, motion: Motion, dt: float) -> str:
        """The clip to play this frame, given ``motion`` over ``dt`` seconds."""
        if motion.dead:
            self.dead = True
        if self.dead:
            return 'die'
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
        if motion.speed >= RUN_SPEED:
            return 'run'
        if motion.speed >= WALK_SPEED:
            return 'walk'
        if abs(motion.turning) >= TURN_RATE:
            return 'turn_left' if motion.turning > 0 else 'turn_right'
        return 'idle'


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

    def __init__(self, model: Any = None, group: Any = None,
                 armoury: Any = None) -> None:
        self.model = model
        #: The scenegraph subtree to draw. The model's own where there is one.
        self.group = group if model is None else model.group
        #: Where the model for a weapon comes from; None for a figure that is
        #: never seen holding one.
        self.armoury = armoury
        self.locomotion = Locomotion()
        self.holding: Optional[str] = None
        self._held: Any = None
        self._upper_mask = frozenset() if model is None else model.mask('spine')

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

    def drop(self) -> None:
        """Take whatever is in the weapon hand out of it."""
        if self.model is not None and self._held is not None:
            self.model.detach('grip', self._held)
        self.holding, self._held = None, None

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
        movement = self.locomotion.update(motion, dt)
        arms = weapon_clip(motion)
        # What is in the hand follows the clip rather than the rules directly,
        # so the one thing that decides a figure is empty-handed decides it
        # once: a body playing no weapon clip is holding nothing, which is what
        # takes the rifle out of a dead man's hand.
        self.carry(motion.weapon if arms else '')
        if self.model is not None:
            self._play(movement, arms, dt)
        return (movement, arms)

    def _play(self, movement: str, arms: Optional[str], dt: float) -> None:
        clips = self.model.clips
        if movement in clips:
            self.model.play(movement, fade=self.FADE,
                            loop=movement not in ONE_SHOTS)
        upper = self.model.layer(self.UPPER, mask=self._upper_mask)
        if arms and arms in clips:
            # A shot is a one-shot over the carry it returns to, and it is
            # faded in quickly: a recoil that eases in over a sixth of a second
            # is a recoil nobody connects to the trigger.
            fade = self.QUICK_FADE if arms.startswith('fire_') else self.FADE
            upper.play(arms, fade=fade, loop=not arms.startswith('fire_'))
        elif upper.tracks:
            upper.stop(fade=self.FADE)
        self.model.update(dt)


def load(name: str, group: Any = None) -> Character:
    """The character model called ``name``, or a body with no art.

    ``name`` is a file under ``assets/characters`` without its suffix, so the
    art a combatant is drawn as is a string in a table and never a code change
    -- which is the whole of what makes swapping the figures configuration.
    """
    relative = os.path.join(CHARACTERS, '%s.glb' % name)
    path = art.path_for(relative)
    try:
        from OpenGLContext.character import CharacterModel
        return Character(CharacterModel.load(path))
    except Exception:                       # noqa: BLE001 - art, not rules
        log.warning('could not load the character %s', path, exc_info=True)
        return Character(group=group)


class Cast:
    """A drawn figure for everybody the rules move, by combatant id.

    Made once for a match: a scenegraph rebuilt whenever somebody spawns is a
    scenegraph rebuilt during a fight, and the figures are the same people the
    whole way through. Which build each of them gets is taken round-robin from
    :data:`BUILDS`, so a room of bots is not a room of identical twins.

    Every figure is loaded separately even where two share a build, because a
    skinned mesh carries its own deformed vertices and its own materials --
    which is also what lets one figure be recoloured without touching another
    wearing the same suit.
    """

    def __init__(self, ids: Any, builds: Any = BUILDS,
                 fallback: Any = None, armoury: Any = None) -> None:
        chosen = list(builds) or list(BUILDS)
        #: One armoury for the whole cast, so a weapon is loaded once for the
        #: match however many people are carrying one.
        self.armoury = armoury
        self.figures: Dict[str, Character] = {}
        for index, id in enumerate(ids):
            figure = load(chosen[index % len(chosen)],
                          group=None if fallback is None else fallback())
            figure.armoury = armoury
            self.figures[id] = figure

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
