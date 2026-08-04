"""The match: who is in it, what hurts them, and who is winning.

The rules of *this* game, kept away from anything that draws or reads a key.
All of it is data and arithmetic, which is what lets a whole match be played out
in a test in a millisecond — and a bot debugged by watching it is a bot debugged
slowly.

Three seams from [§11](../PROJECT-PLAN.md) shape this, and they are worth taking
even if multiplayer never happens, because each is better design on its own
terms:

**State is addressed by id.** A combatant is a record in a dictionary, not
attributes scattered over a scenegraph node, so the whole match can be
enumerated, copied, compared in a test — and later sent.

**The simulation emits events; presentation consumes them.** A hit, a death, a
match ending. The HUD, the sounds and the effects subscribe to that list and
never write back, which is what keeps a damage number from being computed
inside a draw call and what will make an effect fire identically for a remote
player.

**Nothing here reads a clock.** Time arrives through :meth:`Arena.advance`, so a
match replays from its inputs and a test can run ten minutes of it instantly.
There is a test that greps this module for a wall clock, because the rule is
easy to break by accident and invisible afterwards.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .player import PlayerState

log = logging.getLogger(__name__)

__all__ = ['Arena', 'Combatant', 'Damaged', 'Death', 'Detonated', 'Fired',
           'Impact', 'MatchOver', 'ScoreRow', 'RESPAWN_DELAY',
           'STARTING_HEALTH']

#: What everyone spawns with.  The player record's own default, named here so
#: the match's rules read in one place.
STARTING_HEALTH = 100

#: Seconds between dying and being allowed back in.  Long enough that a death
#: costs something, short enough that it is not a punishment.
RESPAWN_DELAY = 1.5

#: The id a death with no killer is attributed to — lava, a long fall, the
#: floor of the map.  Empty rather than a name, because it is the *absence* of
#: a killer and inventing one would put "The World" on the scoreboard.
NOBODY = ''


def _point(value: Any) -> Tuple[float, float, float]:
    """Three numbers as a plain tuple.

    Events are written down and — §11 — sent, so nothing in one is an array
    that shares storage with the simulation it came from.  A tuple of floats
    also compares and prints the way a test wants it to.
    """
    return (float(value[0]), float(value[1]), float(value[2]))


def _heading(value: Any) -> Tuple[float, float, float]:
    """A direction as a plain unit tuple, or straight up if it has no length.

    Normalised here, once, so that every listener may assume it: a sound
    placed along a heading and an effect oriented by one would otherwise each
    have to check, and the one that forgot would be a bug nobody could see.
    """
    array = np.asarray(value, dtype='d')
    length = float(np.linalg.norm(array))
    if length < 1e-12:
        return (0.0, 1.0, 0.0)
    return _point(array / length)


# -- what the simulation says happened ---------------------------------------

@dataclass(frozen=True)
class Damaged:
    """Something took damage.  ``amount`` is what actually landed."""

    target: str
    amount: int
    by: str
    point: Optional[Tuple[float, float, float]] = None
    #: What did it, when that is not a weapon: ``lava``, ``slime``.  Empty for
    #: an ordinary shot.  A **cause** rather than an invented killer, because
    #: a pool of lava is not a combatant and putting one on the scoreboard to
    #: make a message read would be a lie the whole match then has to carry.
    cause: str = ''


@dataclass(frozen=True)
class Fired:
    """Somebody used a weapon.

    Emitted whether or not it landed, and for bots as much as for the player,
    because a shot that missed still made a noise from somewhere — and a
    gunshot heard from the shooter's position is how a player finds an
    opponent they cannot see.  Nothing else in the stream implies this: damage
    says somebody was *hurt*, which is a different fact.
    """

    #: Who fired, and which weapon by its :attr:`~twig_bb.weapons.Weapon.key`.
    shooter: str
    weapon: str
    #: Where the shot left from, in world coordinates.
    origin: Tuple[float, float, float]
    #: Which way it went, as a **unit** heading, so a listener can place a
    #: sound along it without normalising first.
    direction: Tuple[float, float, float]


@dataclass(frozen=True)
class Impact:
    """A shot met something.

    The event an impact effect and an impact sound are placed and chosen from.
    It is emitted for a wall as much as for a person: the two answer different
    questions for a player — *where did that go* against *did I hit them* — and
    the second is the one they act on.
    """

    #: Where, in world coordinates, and the surface normal there, facing back
    #: along the trace.  An effect is placed by the first and oriented by the
    #: second.
    point: Tuple[float, float, float]
    normal: Tuple[float, float, float]
    #: The texture path of the level surface met, or empty for a hit on a
    #: person and for geometry whose surface could not be named.  A **name**
    #: rather than a style object because this record is meant to be written
    #: to a replay and sent over a network, and because the name is the whole
    #: basis on which a material is classified anyway.
    surface: str = ''
    #: Who was hit, or empty for the level.
    target: str = ''
    #: Whose shot it was.
    by: str = ''
    #: Which weapon it came out of, by key, or empty for one that named none.
    #: Here because **a round arriving is as much the weapon's sound as the
    #: report is** — a rifle round lands with a chunk and a pistol round with
    #: a ping — and an event that said only *something hit stone* could not
    #: tell those apart.  A key rather than the weapon, because this record is
    #: meant to be written to a replay and sent over a network.
    weapon: str = ''

    @property
    def on_somebody(self) -> bool:
        """Whether this landed on a combatant rather than on the level."""
        return bool(self.target)


@dataclass(frozen=True)
class Detonated:
    """A projectile went off.

    Separate from :class:`Impact` because it is a different event to draw and
    to hear: an impact is a bullet meeting a wall and a detonation is a burst
    with a radius, and the two want different effects, different sounds and —
    once splash damage exists — different consequences for everybody standing
    nearby.
    """

    #: Where it went off, and which kind of projectile it was.
    point: Tuple[float, float, float]
    kind: str
    #: Who fired it, and who it hit directly, if anybody.
    by: str = ''
    target: str = ''


@dataclass(frozen=True)
class Death:
    """Something ran out of health."""

    target: str
    by: str
    #: What did it, when that is not a weapon; see :attr:`Damaged.cause`.
    cause: str = ''


@dataclass(frozen=True)
class PickedUp:
    """Somebody collected something a map had placed.

    On the stream rather than handled where it happens, for the same reason
    every other outcome is: what a pickup *sounds like*, what it writes on the
    HUD and whether it flashes are three presentation questions, and the rules
    should not have to know that any of them exist.  A player who cannot hear
    and see that they just took armour has, as far as they can tell, not taken
    it — which is the whole of why the item entities being missing read as the
    game being broken rather than as a feature not yet built.
    """

    #: Who took it, and which kind by its
    #: :attr:`~twig_bb.items.ItemKind.key`.
    target: str
    key: str
    #: What to call it on screen.
    title: str = ''
    #: Where it was, in world coordinates, so a sound comes from the thing.
    point: Optional[Tuple[float, float, float]] = None


@dataclass(frozen=True)
class MatchOver:
    """The match reached its limit."""

    winner: str
    reason: str


@dataclass(frozen=True)
class ScoreRow:
    """One line of the scoreboard."""

    id: str
    name: str
    frags: int
    deaths: int
    alive: bool


# -- who is in it ------------------------------------------------------------

@dataclass
class Combatant:
    """One player or bot, and everything the rules know about them.

    Health, armour and what they are carrying live in a
    :class:`~twig_bb.player.PlayerState` rather than being copied here: the
    HUD already reads one, and two records of the same health would eventually
    disagree.
    """

    id: str
    name: str = ''
    player: PlayerState = field(default_factory=PlayerState)
    position: np.ndarray = field(default_factory=lambda: np.zeros(3))
    #: Whether a person is driving this one.  Bots are told apart from the
    #: player here rather than by their id, because an id is a name.
    bot: bool = False
    #: Which difficulty a bot plays at; empty for the player.
    difficulty: str = ''
    frags: int = 0
    deaths: int = 0
    #: Seconds since dying, or None while alive.
    dead_for: Optional[float] = None
    #: An impulse this combatant has been given and not yet spent, in metres
    #: per second.  **The rules say how hard somebody was shoved; what moves
    #: them decides what that means** — for the player it becomes the
    #: character controller's own impulse, and for a bot it becomes a step —
    #: which is what keeps knockback out of the movement code and the camera
    #: out of the rules.
    push: np.ndarray = field(default_factory=lambda: np.zeros(3))

    @property
    def alive(self) -> bool:
        return self.player.alive

    @property
    def health(self) -> int:
        return self.player.health

    @property
    def armour(self) -> int:
        return self.player.armour

    @armour.setter
    def armour(self, value: int) -> None:
        self.player.armour = int(value)


class Arena:
    """One match in progress.

    Built by the start screen from a :class:`~twig_bb.match.MatchSetup` and
    then driven by the frame loop: :meth:`advance` for the clock,
    :meth:`damage` for what happens, :meth:`drain` for what to show.
    """

    def __init__(self, weapons: Any, fragLimit: int = 15,
                 timeLimit: float = 10.0) -> None:
        self.weapons = weapons
        self.fragLimit = int(fragLimit)
        #: Minutes, as the setup states it and as a player thinks of it.
        self.timeLimit = float(timeLimit)
        self._combatants: Dict[str, Combatant] = {}
        #: What has happened and not yet been shown.  Presentation drains it.
        self.events: List[Any] = []
        #: Seconds of match played, advanced by the caller and never read from
        #: a clock.
        self.elapsed = 0.0
        self.over = False

    # -- who is in it ----------------------------------------------------
    def add(self, id: str, position: Any = (0.0, 0.0, 0.0),
            name: str = '', bot: bool = False,
            difficulty: str = '') -> Combatant:
        """Put a combatant in the match, holding what a spawn hands out.

        The **starting** loadout and not the whole table, for the reason
        :meth:`PlayerState.restore` gives back the same thing: what a map
        places is what a player goes and gets, and somebody who spawned
        holding every weapon has no reason to leave the room they are in.
        Handing out the table here while restoring the starting loadout on a
        respawn made a first death cost four weapons and never return them.
        """
        if id in self._combatants:
            raise ValueError('%r is already in this match' % (id,))
        made = Combatant(id=id, name=name or id, bot=bot, difficulty=difficulty,
                         player=PlayerState.starting(self.weapons),
                         position=np.asarray(position, dtype='d'))
        self._combatants[id] = made
        return made

    def ids(self) -> List[str]:
        return list(self._combatants)

    def combatant(self, id: str) -> Optional[Combatant]:
        """The combatant with this id, or None.

        None rather than raising, because the commonest caller is a shot that
        landed on something that has since left the match.
        """
        return self._combatants.get(id)

    def bots(self) -> List[Combatant]:
        return [one for one in self._combatants.values() if one.bot]

    # -- what happens to them --------------------------------------------
    def damage(self, target: str, amount: float, by: str = NOBODY,
               point: Optional[Sequence[float]] = None,
               cause: str = '') -> int:
        """Hurt somebody; returns how much actually landed.

        Nothing happens to the dead.  Without that, a burst of fire that
        arrives in the same tick as a kill scores several frags for it.

        ``cause`` names what did it when that is not a weapon -- the lava, the
        slime -- and travels with the death, so the line a player reads can be
        the true one without anything having to guess from an empty killer.
        """
        hurt = self._combatants.get(target)
        if hurt is None or not hurt.alive:
            return 0
        taken = hurt.player.take_damage(amount)
        where = ((float(point[0]), float(point[1]), float(point[2]))
                 if point is not None else None)
        self.events.append(Damaged(target=target, amount=taken, by=by,
                                   point=where, cause=cause))
        if not hurt.alive:
            self._died(hurt, by, cause)
        return taken

    def kill(self, target: str, cause: str = '', by: str = NOBODY) -> bool:
        """End somebody outright; returns whether this call is what did it.

        **Not damage.**  Some things are not hits: the bottom of the world is
        not something armour can take a share of, and expressing them as a
        very large number would leave a player with enough armour surviving a
        fall out of the level.  A death that cannot be survived is its own
        rule and says so, and it reaches the same :meth:`_died` bookkeeping so
        the score, the respawn timer and the death notice are unchanged.
        """
        hurt = self._combatants.get(target)
        if hurt is None or not hurt.alive:
            return False
        # Reported as damage as well, because the whole of the presentation
        # layer -- the damage indicator, the flash, the log -- listens for
        # that and a death with no hit before it arrives out of nowhere.
        taken = hurt.player.health
        hurt.player.health = 0
        self.events.append(Damaged(target=target, amount=taken, by=by,
                                   point=None, cause=cause))
        self._died(hurt, by, cause)
        return True

    def fired(self, shooter: str, weapon: str, origin: Sequence[float],
              direction: Sequence[float]) -> None:
        """Say a weapon was used.  See :class:`Fired`.

        The heading is normalised here rather than being trusted, so every
        listener reads a unit vector and none of them has to check.
        """
        self.events.append(Fired(shooter=shooter, weapon=str(weapon),
                                 origin=_point(origin),
                                 direction=_heading(direction)))

    def impact(self, point: Sequence[float], normal: Sequence[float],
               surface: str = '', target: str = NOBODY,
               by: str = NOBODY, weapon: str = '') -> None:
        """Say a shot met something.  See :class:`Impact`."""
        self.events.append(Impact(point=_point(point), normal=_heading(normal),
                                  surface=str(surface), target=target, by=by,
                                  weapon=str(weapon)))

    def shove(self, target: str, velocity: Sequence[float]) -> None:
        """Add an impulse to somebody, in metres per second.

        Added rather than set, because two rockets landing in the same tick
        are two shoves: replacing would quietly lose one, and the one lost
        would be the one that made the jump.

        Nothing happens to the dead; a corpse has nowhere to be thrown.
        """
        one = self._combatants.get(target)
        if one is None or not one.alive:
            return
        one.push = one.push + np.asarray(velocity, dtype='d')

    def spend_push(self, target: str) -> np.ndarray:
        """Take somebody's unspent impulse and clear it.

        Taken rather than read, so an impulse is applied exactly once however
        many things are watching for one.
        """
        one = self._combatants.get(target)
        if one is None:
            return np.zeros(3)
        taken, one.push = one.push, np.zeros(3)
        return taken

    def detonated(self, point: Sequence[float], kind: str, by: str = NOBODY,
                  target: str = NOBODY) -> None:
        """Say a projectile went off.  See :class:`Detonated`."""
        self.events.append(Detonated(point=_point(point), kind=str(kind),
                                     by=by, target=target))

    def picked_up(self, target: str, key: str, title: str = '',
                  point: Optional[Sequence[float]] = None) -> None:
        """Say somebody collected something.  See :class:`PickedUp`."""
        self.events.append(PickedUp(target=target, key=str(key),
                                    title=str(title),
                                    point=None if point is None
                                    else _point(point)))

    def _died(self, hurt: Combatant, by: str, cause: str = '') -> None:
        """Score a death and say so."""
        hurt.deaths += 1
        hurt.dead_for = 0.0
        killer = self._combatants.get(by)
        if killer is not None and killer is not hurt:
            killer.frags += 1
        else:
            # Killing yourself, or dying to the map, costs a frag.  Otherwise
            # the quickest route to the top of the scoreboard is the lava.
            hurt.frags -= 1
        self.events.append(Death(target=hurt.id, by=by, cause=cause))
        self._checkOver()

    def respawn(self, id: str, position: Any) -> Optional[Combatant]:
        """Put a dead combatant back in, at ``position``.

        The score is kept: a death costs a frag when it happens and does not
        also wipe the ones already earned.

        **The same record comes back, restored** rather than replaced.  Every
        reader of a player's state holds that object -- the HUD reads it, the
        input path writes it -- and handing out a new one leaves all of them
        looking at the corpse.  See
        :meth:`~twig_bb.player.PlayerState.restore`.
        """
        back = self._combatants.get(id)
        if back is None:
            return None
        back.player.restore(self.weapons)
        back.position = np.asarray(position, dtype='d')
        back.dead_for = None
        # A shove given to the body that just died has nowhere to land.
        back.push = np.zeros(3)
        return back

    def due_to_respawn(self) -> List[str]:
        """Everyone who has been dead long enough to come back."""
        return [one.id for one in self._combatants.values()
                if one.dead_for is not None and one.dead_for >= RESPAWN_DELAY]

    # -- the clock -------------------------------------------------------
    def advance(self, dt: float) -> None:
        """Move the match on by ``dt`` seconds.

        Time arrives here rather than being read, which is what makes a match
        replayable from its inputs and lets a test play ten minutes of one.
        """
        step = max(0.0, float(dt))
        self.elapsed += step
        for one in self._combatants.values():
            if one.dead_for is not None:
                one.dead_for += step
        self._checkOver()

    # -- who is winning --------------------------------------------------
    def score(self, id: str) -> int:
        one = self._combatants.get(id)
        return one.frags if one is not None else 0

    def scoreboard(self) -> List[ScoreRow]:
        """Every combatant, best first; ties broken by fewest deaths then name.

        The dead are on it: a scoreboard that dropped them would flicker every
        time somebody respawned.
        """
        rows = [ScoreRow(id=one.id, name=one.name, frags=one.frags,
                         deaths=one.deaths, alive=one.alive)
                for one in self._combatants.values()]
        return sorted(rows, key=lambda row: (-row.frags, row.deaths, row.name))

    def winner(self) -> Optional[str]:
        """Who is ahead, or None while nobody has scored."""
        rows = self.scoreboard()
        if not rows or rows[0].frags <= 0:
            return None
        return rows[0].id

    def _checkOver(self) -> None:
        """End the match if a limit has been reached.  Ends it once."""
        if self.over:
            return
        reason = ''
        if self.fragLimit > 0 and any(one.frags >= self.fragLimit
                                      for one in self._combatants.values()):
            reason = 'frag limit'
        elif self.timeLimit > 0 and self.elapsed >= self.timeLimit * 60.0:
            reason = 'time limit'
        if not reason:
            return
        self.over = True
        self.events.append(MatchOver(winner=self.winner() or NOBODY,
                                     reason=reason))

    # -- what to show ----------------------------------------------------
    def drain(self) -> List[Any]:
        """Take everything that has happened since the last time this was asked.

        Draining rather than reading, because an event shown twice is a hit
        marker that flickers and a frag message that repeats.
        """
        taken, self.events = self.events, []
        return taken

    def describe(self) -> Dict[str, Any]:
        """The match, as rows for the developer overlay."""
        return {
            'combatants': len(self._combatants),
            'bots': len(self.bots()),
            'elapsed': round(self.elapsed, 1),
            'leader': self.winner() or '-',
            'over': self.over,
        }
