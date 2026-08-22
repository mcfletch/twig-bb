"""Opponents that decide for themselves.

A bot **emits the same per-tick command record a key press does** and writes
nothing to the match. That is [§11](../PROJECT-PLAN.md)'s first seam and it is
what makes all of this testable: a bot's whole mind can be run against a
constructed world with no window, no frame loop and no clock, and a remote
player is later just a third producer of an existing type.

**The difficulty is the axis this is built along**, not a multiplier bolted on
at the end. A difficulty is a declared node with typed fields — like the
movement modes and the weapon table — so a menu can present it, a match can mix
them, and the numbers can be tested. What scales: how long before a new
sighting is answered, how far off the aim is, how far it looks around, how often
it decides.

**What never scales is the senses.** Every difficulty uses the same
:meth:`Bot.perceive`, which goes through the same line-of-sight ray cast the
player's own shots do. No seeing through walls, no knowing where somebody is
without having perceived them, no hidden damage. A bot that cheats is not
difficult, it is annoying — and once one hidden advantage is allowed the scale
stops meaning anything, because there is no longer a reason to believe the next
rung is skill rather than another exemption.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from vrml import field, node

from . import combat

log = logging.getLogger(__name__)

__all__ = ['Bot', 'Command', 'Difficulty', 'PRESETS', 'preset', 'reach',
           'safe_range']

#: How far a bot can see, in metres.  The same for every difficulty, because it
#: is a sense.
SIGHT_RANGE = 60.0

#: How wide its view is, in degrees either side of where it faces.  Also the
#: same for every difficulty, and also because it is a sense.
FIELD_OF_VIEW = 100.0

#: Seconds between one look around and the next.
#:
#: Looking is the expensive half of a bot: every one of them asks line of
#: sight of every other combatant, which is quadratic in the count and put a
#: tick past a whole frame at eight opponents — for a menu that offers
#: fifteen.  The casts themselves are cheap; the number of them is the
#: problem, so a bot **looks less often** rather than seeing less.
#:
#: Shorter than the fastest reaction on the ladder, so it cannot be noticed:
#: a bot answers a sighting no sooner than its ``reactionTime``, and delaying
#: the sighting itself by less than that changes nothing a player could feel.
#: Slowing a *sense* down far enough to matter would be a difficulty change by
#: the back door, which is exactly what this file exists to prevent.
PERCEPTION_INTERVAL = 0.1

#: Seconds since the last shot that a fresh mind starts with, which is longer
#: than any weapon's ``fireInterval``: a bot arrives with a loaded weapon, and
#: what delays its first shot is its reaction time and nothing else.
LOADED = 1e6

#: Metres a bot tries to keep between itself and what it is fighting.  Close
#: enough to be a threat, far enough that it is not standing on you.
PREFERRED_RANGE = 6.0

#: How near is near enough not to bother adjusting.
RANGE_SLACK = 2.0

#: How much further than a burst's own radius a careful bot keeps before it
#: will fire a splash weapon.  A margin rather than the radius itself, because
#: a target moves while the projectile is in the air and a bot standing
#: exactly at the edge of its own blast is a bot that occasionally kills
#: itself for no gain.
BLAST_MARGIN = 1.6

#: About how many seconds a bot with nothing to fight walks one way before
#: choosing another.  The actual hold is spread either side of it, so a room
#: of them does not turn in unison -- which reads as a script even when every
#: turn is random.
WANDER_INTERVAL = 2.5

#: How far a thrown shot may fall below the line it was aimed along and still
#: be worth taking, in metres.  A body's own height, because a projectile that
#: has dropped less than that is still arriving somewhere on the target.
AIM_DROP = combat.BODY_HEIGHT


class Difficulty(node.Node):
    """One rung of the ladder, as numbers rather than as a branch in the code."""

    PROTO = 'BotDifficulty'

    name = field.newField('name', 'SFString', 1, '')
    #: Seconds between seeing somebody new and doing anything about it.
    reactionTime = field.newField('reactionTime', 'SFFloat', 1, 0.4)
    #: How far off the aim is, in degrees.  The knob that decides whether a
    #: fight is survivable.
    aimError = field.newField('aimError', 'SFFloat', 1, 6.0)
    #: How fast the aim closes on a target, 0 to 1 per decision.
    aimSpeed = field.newField('aimSpeed', 'SFFloat', 1, 0.5)
    #: Seconds between decisions.  A slower thinker is a bot you can outrun.
    decisionInterval = field.newField('decisionInterval', 'SFFloat', 1, 0.2)
    #: Whether it fights at all.  False is near-passive, which is both a real
    #: setting and the fixture navigation is verified with.
    fights = field.newField('fights', 'SFBool', 1, True)
    #: How readily it closes rather than holds; 0 hangs back, 1 charges.
    aggression = field.newField('aggression', 'SFFloat', 1, 0.5)
    #: How well it aims *ahead* of a target moving across it, 0 to 1.  A slow
    #: projectile fired where somebody is arrives where they were, so leading
    #: is most of what makes a rocket dangerous -- and it is therefore a skill
    #: and belongs on the ladder rather than being something every bot does
    #: perfectly.
    leadsTargets = field.newField('leadsTargets', 'SFFloat', 1, 0.5)
    #: How well it keeps out of its own blast, 0 to 1.  Zero will fire a
    #: rocket at a wall two feet away, which is exactly what the bottom of the
    #: ladder should do; one keeps a burst's radius and a margin between
    #: itself and anything it fires at.
    blastSense = field.newField('blastSense', 'SFFloat', 1, 0.6)

    UI_HINTS = {
        'name': {'skip': True},
        'reactionTime': {'label': 'Reaction (s)', 'minimum': 0.0,
                         'maximum': 2.0, 'step': 0.05},
        'aimError': {'label': 'Aim error (deg)', 'minimum': 0.0,
                     'maximum': 30.0, 'step': 0.5},
        'aimSpeed': {'label': 'Aim speed', 'minimum': 0.05, 'maximum': 1.0,
                     'step': 0.05},
        'decisionInterval': {'label': 'Thinks every (s)', 'minimum': 0.02,
                             'maximum': 1.0, 'step': 0.02},
        'fights': {'label': 'Fights'},
        'aggression': {'label': 'Aggression', 'minimum': 0.0, 'maximum': 1.0,
                       'step': 0.05},
        'leadsTargets': {'label': 'Leads a moving target', 'minimum': 0.0,
                         'maximum': 1.0, 'step': 0.05},
        'blastSense': {'label': 'Keeps out of its own blast', 'minimum': 0.0,
                       'maximum': 1.0, 'step': 0.05},
    }


def _presets() -> Dict[str, Difficulty]:
    """The ladder, easiest first.

    Near-passive walks about and does not shoot; nightmare answers a sighting
    in a fifth of a second and is barely off target.  The rungs between are
    spaced so each is noticeably different to play against rather than
    arithmetically even.
    """
    return {
        'near-passive': Difficulty(name='near-passive', fights=False,
                                   reactionTime=1.5, aimError=25.0,
                                   aimSpeed=0.15, decisionInterval=0.5,
                                   aggression=0.0, leadsTargets=0.0,
                                   blastSense=0.0),
        'easy': Difficulty(name='easy', reactionTime=1.0, aimError=14.0,
                           aimSpeed=0.25, decisionInterval=0.4,
                           aggression=0.25, leadsTargets=0.15,
                           blastSense=0.2),
        'medium': Difficulty(name='medium', reactionTime=0.55, aimError=7.0,
                             aimSpeed=0.45, decisionInterval=0.25,
                             aggression=0.5, leadsTargets=0.5,
                             blastSense=0.6),
        'hard': Difficulty(name='hard', reactionTime=0.3, aimError=3.0,
                           aimSpeed=0.7, decisionInterval=0.12,
                           aggression=0.75, leadsTargets=0.8,
                           blastSense=0.85),
        'nightmare': Difficulty(name='nightmare', reactionTime=0.15,
                                aimError=1.0, aimSpeed=0.95,
                                decisionInterval=0.05, aggression=1.0,
                                leadsTargets=1.0, blastSense=1.0),
    }


#: The ladder, built once.
PRESETS: Dict[str, Difficulty] = _presets()

#: What an unrecognised difficulty gets.  A saved setting from a version that
#: declared more must still play rather than refusing to start.
DEFAULT_DIFFICULTY = 'medium'


def preset(name: str) -> Difficulty:
    """The numbers behind a difficulty name; the default for an unknown one."""
    found = PRESETS.get(name)
    if found is None:
        log.warning('no bot difficulty called %r; playing at %s',
                    name, DEFAULT_DIFFICULTY)
        return PRESETS[DEFAULT_DIFFICULTY]
    return found


@dataclass
class Command:
    """What one bot wants to do this tick.

    The same shape a key press contributes to, which is the point: the
    simulation consumes commands and does not care who produced them.
    """

    id: str
    #: A unit heading to look and shoot along, or None for nothing in view.
    aim: Optional[np.ndarray] = None
    #: A unit heading to walk along, or None to stand still.
    move: Optional[np.ndarray] = None
    #: Whether it pulled the trigger this tick.
    fired: bool = False
    #: Who it is fighting, for a debug overlay.
    target: str = ''
    #: Which weapon it wants, by key, or empty for "whatever I am holding".
    #: A bot built with no loadout names nothing and leaves the choice to
    #: whoever applies the command, which is how a match with one weapon in
    #: it still works.
    weapon: str = ''


class Bot:
    """One opponent's mind.

    Holds only what a mind may hold: where it is looking, what it has *seen*,
    and how long it has been looking at it.  Everything else it asks the world
    for, through the same queries a player's own shots go through.
    """

    def __init__(self, id: str, difficulty: str = DEFAULT_DIFFICULTY,
                 seed: Optional[int] = None, weapons: Any = None,
                 projectiles: Any = None) -> None:
        self.id = id
        self.difficulty = difficulty
        self.skill = preset(difficulty)
        #: What it may choose between, and what those weapons throw.  Both
        #: optional: a bot given neither uses whatever the caller hands it,
        #: which is what a match with a single weapon in it wants.
        self.weapons = weapons
        self.projectiles = projectiles
        #: Which way it is looking.  Its own, not the arena's: where a bot
        #: faces is part of its state and is what its field of view is about.
        self.facing = np.array([-1.0, 0.0, 0.0])
        # Aim wander is presentation-adjacent but must be reproducible for a
        # replay test, so it is a seeded generator rather than the module's.
        self._wobble = random.Random(seed)
        #: How far through its first look-around interval this bot starts, in
        #: seconds.  Its own generator rather than a draw from ``_wobble``,
        #: because the aim sequence is pinned by tests and a bot's timing must
        #: not be able to shift it.  Spread on purpose: a room full of bots
        #: that all looked on the same frame would turn a saving into a
        #: stutter every few frames.
        self._phase = random.Random(seed).random() * PERCEPTION_INTERVAL
        self.reset()

    def reset(self) -> None:
        """Forget what it was doing.  What a respawn leaves it as.

        **Not the same state every time.**  Two bots built from one difficulty
        and dropped into one room used to play the first few seconds out
        identically, which is most of what made them look scripted: they faced
        the same way, walked the same way and committed on the same frame.
        Which way it happens to be looking when it arrives, and how long it
        takes before it first commits, are spread here.  Neither is a
        difficulty -- a hard bot is not one that arrives facing you -- and
        both are what a person entering a room does differently every time.
        """
        self.target = ''
        self.watching = 0.0
        self.facing = _around(self._wobble)
        # Negative, so a fresh mind has to *wait* before its first decision:
        # arriving is not the same thing as shooting.
        self.since_decision = -self._wobble.random() \
            * float(self.skill.decisionInterval)
        #: Seconds since it last pulled the trigger, against which its
        #: weapon's own ``fireInterval`` is measured.  Starting long enough
        #: ago that the first shot waits for the reaction time and nothing
        #: else -- coming back holding a spent rocket launcher would be a
        #: rule nobody could see and nobody asked for.
        self.since_shot = LOADED
        #: Where it walks when there is nothing to fight, and how long is left
        #: of holding that heading.  Held rather than redrawn every tick: a
        #: bot picking a fresh angle sixty times a second does not wander, it
        #: vibrates on the spot.
        self._heading: Optional[np.ndarray] = None
        self._wandering = 0.0
        #: Where the target was last tick and how long ago, so how fast they
        #: are crossing can be *observed* rather than read out of the rules.
        #: A bot may not know a velocity it has not watched happen.
        self._seen_at: Optional[np.ndarray] = None
        self._seen_dt = 0.0
        self._drift = np.zeros(3)
        #: Who it could see when it last looked, and how long ago that was.
        #: Forgotten by a reset, so a bot that has just respawned somewhere
        #: else looks afresh rather than acting on a view from across the map.
        self._seen: List[str] = []
        #: Enough that the very next :meth:`look` takes one: a bot with
        #: nothing remembered has no answer to give.
        self._since_look = PERCEPTION_INTERVAL
        #: Spent on that first look instead of resetting the clock to zero,
        #: which is the whole of the stagger: two bots made at the same moment
        #: land on different frames from then on and stay there.
        self._offset = self._phase

    # -- the senses, identical at every difficulty -----------------------
    def perceive(self, world: Any, arena: Any) -> List[str]:
        """Everyone this bot can *actually* see, nearest first.

        Line of sight through the physics world, plus a field of view.  There
        is one of these and every difficulty uses it: the difference between an
        easy bot and a nightmare one is what each does about what it saw, never
        what it is allowed to see.
        """
        me = arena.combatant(self.id)
        if me is None or not me.alive:
            return []
        # Range and field of view go *into* the question rather than filtering
        # its answer: they are two comparisons, the line of sight behind them is
        # a ray cast, and asking the cheap ones first is the difference between
        # casting at everybody in the level and casting at whoever could
        # plausibly be seen.  See :func:`twig_bb.combat.visible_targets`.
        return combat.visible_targets(world, arena, self.id,
                                      within=SIGHT_RANGE, facing=self.facing,
                                      cone=FIELD_OF_VIEW)

    def look(self, world: Any, arena: Any, dt: float) -> List[str]:
        """Everyone this bot can see, looked up again only now and then.

        :meth:`perceive` is the *sense* and is unchanged; this is how often it
        is asked.  Between looks the last answer stands, minus anybody who has
        died since — a remembered sighting must not become a bot emptying a
        magazine into a corpse, and checking who is alive costs no ray casts.

        See :data:`PERCEPTION_INTERVAL` for why looking less often is the
        right saving and seeing less would not be.
        """
        self._since_look += max(0.0, float(dt))
        if self._since_look >= PERCEPTION_INTERVAL:
            # Set rather than decremented: a frame long enough to owe several
            # looks is answered by one, which is what a look *is*.  The offset
            # is spent here, on the first look after a reset.
            self._since_look, self._offset = self._offset, 0.0
            self._seen = self.perceive(world, arena)
            return self._seen
        return [id for id in self._seen if _alive(arena, id)]

    def _in_view(self, heading: np.ndarray) -> bool:
        """Whether something in this direction is in front of the bot."""
        facing = self.facing / max(float(np.linalg.norm(self.facing)), 1e-9)
        cosine = float(np.dot(facing, heading))
        return cosine >= math.cos(math.radians(FIELD_OF_VIEW))

    # -- thinking ---------------------------------------------------------
    def think(self, world: Any, arena: Any, dt: float) -> Command:
        """One tick of this bot's mind; returns what it wants to do.

        It writes nothing.  Applying the command is somebody else's job, which
        is what lets a whole fight be played out in a test.
        """
        step = max(0.0, float(dt))
        self.since_decision += step
        self.since_shot += step
        me = arena.combatant(self.id)
        if me is None or not me.alive:
            self.reset()
            return Command(id=self.id)
        seen = self.look(world, arena, step)
        self._watch(seen, step)
        if not self.target:
            self._watch_drift(None, step)
            return Command(id=self.id, move=self._wander(step))
        return self._fight(arena, me, step)

    def _watch(self, seen: Sequence[str], dt: float) -> None:
        """Keep track of what is in view, and for how long.

        Losing sight resets the clock, so a target stepping out of cover is
        answered by a reaction rather than by an instant shot.
        """
        if self.target and self.target in seen:
            self.watching += dt
            return
        self.target = seen[0] if seen else ''
        self.watching = dt if self.target else 0.0

    def _fight(self, arena: Any, me: Any, dt: float) -> Command:
        """Aim, close or back off, and shoot when the reaction has elapsed."""
        heading = combat.aim_at(arena, self.id, self.target)
        if heading is None:
            return Command(id=self.id, move=self._wander(dt))
        them = arena.combatant(self.target)
        gap = float(np.linalg.norm(np.asarray(them.position, dtype='d')
                                   - np.asarray(me.position, dtype='d'))) \
            if them is not None else 0.0
        self._watch_drift(them, dt)
        weapon = self._chosen(gap, me.player)
        aim = self._swung(self._aimed(self._led(heading, weapon, gap)))
        self.facing = aim
        ready = self.watching >= float(self.skill.reactionTime)
        fired = bool(ready and self.skill.fights and self._loaded(weapon)
                     and self._decided())
        if fired:
            self.since_shot = 0.0
        return Command(id=self.id, aim=aim, target=self.target, fired=fired,
                       weapon='' if weapon is None else str(weapon.key),
                       move=self._approach(arena, me, heading))

    def _loaded(self, weapon: Any) -> bool:
        """Whether the weapon it has chosen is ready to fire again.

        **How often a bot thinks and how often its weapon fires are two
        different clocks**, and only the first of them is a difficulty.  The
        hardest bot decides twenty times a second; a rocket launcher fires
        rather less often than that, and a bot held to nothing but its own
        decision rate empties whatever it is holding into the first person it
        sees, in the frame it sees them.  What is difficult about a good
        opponent is that it aims well and commits quickly -- not that it has a
        different rifle from the one the player picked up.

        A bot with no weapon table has nothing to be held to, and fires at its
        own rate as before.
        """
        if weapon is None:
            return True
        return self.since_shot >= float(weapon.fireInterval)

    # -- which weapon, and where to point it ------------------------------
    def _chosen(self, gap: float, loadout: Any = None) -> Any:
        """The weapon to use at this range, or None if there is no table.

        **A splash weapon at a distance and a trace up close.**  A rocket is
        worth more than a rifle whenever it can be used, and the whole of
        "whenever" is that the burst must not reach back: how far that is
        comes from the projectile's own radius, and how much a bot *cares*
        comes from its difficulty.  A careless one fires anyway, which is what
        the bottom of the ladder is for.

        ``loadout`` is the body's :class:`~twig_bb.player.PlayerState` -- what
        it has picked up and what it has spent -- so a weapon it never found or
        has emptied is not on the menu.  That is what stops every bot opening a
        fight on a rocket: like a player, it reaches for the launcher only once
        the level has handed it one.
        """
        if self.weapons is None:
            return None
        best = None
        for weapon in self.weapons.weapons:
            if not self._usable(weapon, gap, loadout):
                continue
            if best is None or self._worth(weapon, gap) > self._worth(best, gap):
                best = weapon
        return best if best is not None else self._anything()

    def _anything(self) -> Any:
        """The first weapon in the table: better than naming none at all."""
        return self.weapons.weapons[0] if self.weapons.weapons else None

    def _usable(self, weapon: Any, gap: float, loadout: Any = None) -> bool:
        """Whether this weapon may be used at this range and it has a round.

        A trace has no range worth speaking of and is always allowed.  A
        thrown one has **both** ends: nearer than :func:`safe_range` and the
        burst reaches back to the thrower, further than :func:`reach` and it
        never arrives at all.  Either way, a weapon the body cannot pay for is
        no more usable than one out of range.
        """
        if not self._has_ammo(weapon, loadout):
            return False
        kind = self._thrown(weapon)
        if kind is None:
            return True
        return (safe_range(kind, float(self.skill.blastSense))
                <= gap <= reach(kind))

    def _has_ammo(self, weapon: Any, loadout: Any) -> bool:
        """Whether the body this mind drives has a round left for this weapon.

        A bot fires from the same loadout a player does, so a launcher it never
        found is not an option and one it has emptied drops out of the running
        until it finds more -- which is what makes the weapon it reaches for a
        thing the level handed it rather than a thing it was born holding.

        A mind with no body to ask -- handed a bare weapon table in a test,
        with no loadout behind it -- is held to no count and may fire what it
        likes, the same courtesy :meth:`_loaded` gives a bot with no weapon
        table at all.
        """
        if loadout is None:
            return True
        return bool(loadout.can_fire(weapon))

    def _worth(self, weapon: Any, gap: float) -> float:
        """How much a bot would rather have this weapon at this range.

        A splash weapon outranks a trace, and between two of a kind the one
        that does more **where the target actually is**: a shotgun across a
        level costs nothing at all, and a bot that chose it there would stand
        in the open firing at somebody it could not hurt.  Crude on purpose
        beyond that: what makes a bot difficult is its aim and its timing, and
        a bot agonising over a loadout is a bot standing still.
        """
        kind = self._thrown(weapon)
        if kind is None:
            return weapon.damage_at(gap) * float(weapon.pellets)
        return 1000.0 + float(kind.splashDamage)

    def _thrown(self, weapon: Any) -> Any:
        """What a weapon throws, or None for a hitscan one."""
        key = str(weapon.projectile)
        if not key or self.projectiles is None:
            return None
        return self.projectiles.by_key(key)

    def _watch_drift(self, them: Any, dt: float) -> None:
        """Notice how fast the target is crossing, by watching them move.

        Observed rather than read off the rules: a bot may not know a velocity
        it has not seen happen, which is the same rule its eyes follow.
        """
        step = max(1e-6, float(dt))
        where = (None if them is None
                 else np.asarray(them.position, dtype='d').copy())
        if where is not None and self._seen_at is not None:
            self._drift = (where - self._seen_at) / step
        elif where is None:
            self._drift = np.zeros(3)
        self._seen_at = where

    def _led(self, heading: np.ndarray, weapon: Any,
             gap: float) -> np.ndarray:
        """Where to point so a *slow* shot and the target arrive together.

        Nothing is led for a hitscan weapon: a trace arrives instantly, so
        aiming ahead of somebody would only miss them.
        """
        kind = None if weapon is None else self._thrown(weapon)
        skill = float(self.skill.leadsTargets)
        if kind is None or skill <= 0.0 or gap <= 0.0:
            return heading
        # How long the shot *actually* takes to arrive, thrust and all -- not
        # gap over its launch speed, which for a rocket that leaves slowly and
        # builds would lead by the muzzle pace it holds for only an instant and
        # aim a long way ahead of where it will really be.
        travel = kind.time_to(gap)
        if not math.isfinite(travel) or travel <= 0.0:
            return heading
        ahead = self._drift * travel * skill
        aimed = heading * gap + ahead
        length = float(np.linalg.norm(aimed))
        return heading if length < 1e-9 else aimed / length

    def _decided(self) -> bool:
        """Whether enough time has passed for another decision."""
        if self.since_decision < float(self.skill.decisionInterval):
            return False
        self.since_decision = 0.0
        return True

    def _swung(self, wanted: np.ndarray) -> np.ndarray:
        """Move the aim part of the way towards where it wants to be.

        A bot whose aim arrives the instant it decides is a bot nobody can
        dodge: strafing across one is answered before the step has landed, and
        the only thing that ever saves a player is how badly it happens to be
        aiming.  How fast the aim *closes* is therefore its own rung on the
        ladder -- ``aimSpeed`` -- and it is what makes a slow bot beatable by
        moving rather than only by being lucky.

        A speed of one arrives at once, which is what the top of the ladder
        should feel like, and a speed of nothing never turns at all, which is
        a real setting rather than an accident.
        """
        speed = max(0.0, min(1.0, float(self.skill.aimSpeed)))
        if speed >= 1.0:
            return wanted
        moved = self.facing + (wanted - self.facing) * speed
        length = float(np.linalg.norm(moved))
        # Zero only when the aim is being swung through exactly half a turn
        # and has reached the middle of it, where there is no direction left
        # to normalise -- take the answer rather than a nan.
        return wanted if length < 1e-9 else moved / length

    def _aimed(self, heading: np.ndarray) -> np.ndarray:
        """The true heading, moved off by this difficulty's aim error.

        Scattered over the cone rather than by two angles, for the same reason
        a shotgun's pellets are: perturbing two angles crowds the samples
        toward the middle, which would make a bot far more accurate than its
        stated error.
        """
        error = math.radians(float(self.skill.aimError))
        if error <= 0.0:
            return heading
        cosine = 1.0 - self._wobble.random() * (1.0 - math.cos(error))
        sine = math.sqrt(max(0.0, 1.0 - cosine * cosine))
        about = self._wobble.random() * 2.0 * math.pi
        side, up = _frame(heading)
        aimed = (heading * cosine + side * (sine * math.cos(about))
                 + up * (sine * math.sin(about)))
        return aimed / max(float(np.linalg.norm(aimed)), 1e-9)

    def _approach(self, arena: Any, me: Any,
                  heading: np.ndarray) -> Optional[np.ndarray]:
        """Close, hold or back off, by how far away the target is.

        Standing on top of somebody is neither threatening nor readable, so a
        bot keeps a range — and how *willingly* it closes is what aggression
        means.
        """
        them = arena.combatant(self.target)
        if them is None:
            return None
        gap = float(np.linalg.norm(np.asarray(them.position, dtype='d')
                                   - np.asarray(me.position, dtype='d')))
        wanted = PREFERRED_RANGE * (1.5 - float(self.skill.aggression))
        if gap > wanted + RANGE_SLACK:
            return _flat(heading)
        if gap < wanted - RANGE_SLACK:
            return _flat(-heading)
        return None

    def _wander(self, dt: float) -> np.ndarray:
        """Somewhere to go when nothing is in view.

        A bot standing still in an empty room reads as a broken bot, so it
        keeps moving; where is §6's navmesh's business when there is one, and
        until then it is a heading it **holds** until something interesting
        happens.  Held is the operative word: this used to draw a fresh angle
        every tick, which is not wandering but shaking, and sixty conflicting
        headings a second is also the worst possible input to a capsule
        sliding along a wall.

        How long it holds one is spread about :data:`WANDER_INTERVAL`, so a
        room of bots does not pivot in unison -- which reads as a script even
        when each turn is random.
        """
        self._wandering -= max(0.0, float(dt))
        if self._heading is None or self._wandering <= 0.0:
            self._heading = _around(self._wobble)
            self._wandering = WANDER_INTERVAL * (0.5 + self._wobble.random())
        return self._heading


def safe_range(kind: Any, sense: float) -> float:
    """How far a bot with this much sense keeps before firing a splash weapon.

    The projectile's **own** radius plus a margin, scaled by the sense: a
    bigger burst has to be kept further away, and a constant here would be
    wrong the first time anybody retuned the table.  A sense of zero makes
    everywhere safe, which is a bot that will happily kill itself.
    """
    sense = max(0.0, min(1.0, float(sense)))
    if sense <= 0.0:
        return 0.0
    return (float(kind.splashRadius) + BLAST_MARGIN) * sense


def reach(kind: Any, drop: float = AIM_DROP) -> float:
    """How far this projectile can be thrown *at* somebody and arrive, in metres.

    Two limits, whichever comes first.

    It **stops existing**.  A fuse ends it in the air and a lifetime gives up
    on one that met nothing, and neither is going to arrive at anybody past
    the point it went off.

    And it **falls**.  A bot aims straight down the line to what it is
    fighting — :meth:`Bot._led` leads a target that is crossing and never
    lofts a shot — so a projectile with gravity is ``g t² / 2`` below that
    line by the time it gets there.  Once that is more than ``drop`` it is
    landing in the floor short of them, which is what a grenade thrown forty
    metres does.

    Everything here is the projectile's own numbers, so a table edit moves the
    range a bot will use it at without anything else being touched.
    """
    speed = float(kind.speed)
    if speed <= 0.0:
        return 0.0
    ends = [seconds for seconds in (float(kind.fuse), float(kind.lifetime))
            if seconds > 0.0]
    seconds = min(ends) if ends else 0.0
    gravity, fall = float(kind.gravity), max(0.0, float(drop))
    if gravity > 0.0:
        seconds = min(seconds, math.sqrt(2.0 * fall / gravity))
    # How far it actually gets in that time, thrust included -- a rocket that
    # builds speed reaches a good deal further over its life than its launch
    # speed alone would say, and gating a bot on the launch speed would have it
    # decline a shot it could easily make.
    return kind.distance_in(seconds)


def _around(chance: random.Random) -> np.ndarray:
    """A unit heading somewhere on the level: level, and any way at all."""
    angle = chance.random() * 2.0 * math.pi
    return np.array([math.cos(angle), 0.0, math.sin(angle)])


def _alive(arena: Any, id: str) -> bool:
    """Whether ``id`` is still in the fight."""
    one = arena.combatant(id)
    return one is not None and bool(one.alive)


def _frame(heading: np.ndarray) -> Any:
    """Two unit vectors across ``heading``, however it is pointed."""
    axis = np.array([0.0, 1.0, 0.0])
    if abs(float(np.dot(heading, axis))) > 0.9:
        axis = np.array([1.0, 0.0, 0.0])
    side = np.cross(heading, axis)
    side = side / np.linalg.norm(side)
    return (side, np.cross(heading, side))


def _flat(heading: np.ndarray) -> np.ndarray:
    """A heading with the vertical taken out: a bot walks, it does not fly."""
    flat = np.array([heading[0], 0.0, heading[2]])
    length = float(np.linalg.norm(flat))
    if length < 1e-9:
        return np.array([1.0, 0.0, 0.0])
    return flat / length
