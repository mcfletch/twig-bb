"""Turning what the simulation said into what the player sees.

**The one loop between the rules and the screen.**  :mod:`twitchoglc.arena`
emits what happened — a hit, an impact, a death, the end of the match — and
this reads that stream and answers it.  Nothing here writes back, and nothing
in the rules knows this exists, which is the seam [§11](../PROJECT-PLAN.md)
asks for: a replay or a network client sees exactly the events the local player
saw and can build exactly the same feedback from them.

Two things a player needs and cannot work out for themselves live here:

**Which way a hit came from.**  How much health was lost is already on the
meter; where the shooter is standing is the part a player must act on within a
second, and the only thing that carries it is a bearing computed from the
camera and the shooter's position.  See :func:`bearing_to`.

**That they are dead and are coming back.**  A death whose only sign is a
message in the corner reads as the message being wrong, because nothing else
about the world changed.  The notice and its honest countdown are what stop a
player wondering whether the game has hung.

A ``hud`` of None is a supported state, not a degenerate one: a capture run
draws no HUD and must still be able to play a match out.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

import numpy as np

from . import arena as arenamod
from . import game as gamemod

log = logging.getLogger(__name__)

__all__ = ['Presenter', 'bearing_to']

#: Damage, as a fraction of full health, that marks the screen as hard as it
#: can be marked.  Not the whole health bar: a hit for a third of a player's
#: life is already as bad as the indicator needs to say, and scaling to 100
#: would leave every ordinary hit a barely visible smudge.
FULL_MARK_DAMAGE = 0.34

#: Which way a camera looks before anything has turned it, in scene space.
#: Down -Z, which is the convention the whole renderer uses.
FORWARD = (0.0, 0.0, -1.0)


def bearing_to(camera: Sequence[float], forward: Sequence[float],
               point: Sequence[float]) -> float:
    """Radians from where the camera looks to ``point``, positive to the right.

    ``pi`` is directly behind and ``-pi/2`` directly to the left, which is what
    a :class:`~OpenGLContext.ui.hudwidgets.DamageIndicator` reads.

    **Height is thrown away deliberately.**  What this answers is *which way do
    I turn*, and turning is about one axis: a shooter on a balcony to the right
    is to the right, and an indicator that put them somewhere between right and
    above would be harder to act on rather than more accurate.

    Zero — straight ahead — is the answer when there is no direction to give:
    a camera that is not looking anywhere, and a shooter standing exactly where
    the camera is.  Inventing a bearing for either would point a player at
    nothing.
    """
    facing = _flat(forward)
    to = _flat(np.asarray(point, dtype='d') - np.asarray(camera, dtype='d'))
    if facing is None or to is None:
        return 0.0
    # How far to the right of the facing direction the target lies: the dot
    # product with `forward x up`, which for two vectors already flattened
    # onto the ground plane is this pair of terms.
    across = float(facing[0] * to[2] - facing[2] * to[0])
    along = float(np.dot(facing, to))
    return float(np.arctan2(across, along))


def _flat(vector: Sequence[float]) -> Optional[np.ndarray]:
    """``vector`` with its height removed and normalised, or None if it had none."""
    flat = np.asarray(vector, dtype='d').copy()
    flat[1] = 0.0
    length = float(np.linalg.norm(flat))
    if length < 1e-9:
        return None
    return flat / length


class Presenter:
    """One match's events, answered on the player's screen.

    Built once for a match and driven twice a frame: :meth:`show` for the
    events that have just been drained, and :meth:`update` for the things that
    go on changing while nothing happens — a respawn counting down.
    """

    def __init__(self, match: Any, hud: Any = None, sounds: Any = None,
                 effects: Any = None) -> None:
        self.match = match
        self.hud = hud
        #: What the same events sound like, or None for a silent run.  A
        #: second reader of one stream rather than a second stream, which is
        #: what keeps a sound and a hit marker from ever disagreeing about
        #: what happened.
        self.sounds = sounds
        #: What the same events look like in the world — the bursts at each
        #: impact — or None where nothing is being drawn.
        self.effects = effects
        #: Whether the player was dead the last time the notice was written,
        #: so coming back can be noticed without the rules having to say so.
        self._dead = False
        #: What the death notice says under "you are dead".  Kept from the
        #: :class:`~twitchoglc.arena.Death` event, because by the time the
        #: notice is written the killer may have died themselves.
        self._cause = ''

    # -- what just happened ----------------------------------------------
    def show(self, events: Sequence[Any], camera: Sequence[float],
             forward: Sequence[float] = FORWARD, now: float = 0.0,
             platform: Any = None) -> None:
        """Answer everything in ``events``, then bring the standing state up to date.

        ``camera`` and ``forward`` are where the player is looking *now*, which
        is what a bearing is measured against — an event carries where a thing
        happened in the world and the screen is what has to be turned.

        ``platform`` is the view platform, which the sounds need because the
        camera is also the ear.
        """
        if self.sounds is not None:
            self.sounds.show(events, platform=platform)
        if self.effects is not None:
            self.effects.show(events)
        for event in events:
            if isinstance(event, arenamod.Damaged):
                self._damaged(event, camera, forward, now)
            elif isinstance(event, arenamod.Impact):
                self._impact(event, now)
            elif isinstance(event, arenamod.Death):
                self._death(event)
            elif isinstance(event, arenamod.PickedUp):
                self._pickedUp(event)
        self.update(now)

    def update(self, now: float = 0.0) -> None:
        """Bring the parts that change without an event up to date."""
        self._deathNotice(now)

    # -- one event at a time ---------------------------------------------
    def _damaged(self, event: arenamod.Damaged, camera: Sequence[float],
                 forward: Sequence[float], now: float) -> None:
        """Mark the screen in the direction the hit came from.

        Damage to anybody else is not shown: it is the player's own screen and
        a wash for every bullet in the level would be a strobe.
        """
        if self.hud is None or event.target != gamemod.PLAYER_ID:
            return
        self.hud.damage.hurt(bearing=self._bearing(event.by, camera, forward),
                             intensity=self._intensity(event.amount), now=now)

    def _impact(self, event: arenamod.Impact, now: float) -> None:
        """Mark the reticule when the *player's* shot landed on somebody.

        Only then: the mark means "you hit them", so a wall would make it a
        lie and another fight across the room would make it noise.
        """
        if self.hud is None or event.by != gamemod.PLAYER_ID:
            return
        if event.on_somebody:
            self.hud.hit(now)

    def _death(self, event: arenamod.Death) -> None:
        """Remember what killed the player, for the notice to say.

        Kept when the event arrives rather than looked up when the notice is
        written, because by then the killer may themselves have died and the
        scoreboard is no longer the record of what happened.
        """
        if event.target != gamemod.PLAYER_ID:
            return
        killer = self.match.combatant(event.by)
        self._cause = ('Fragged by %s' % (killer.name,)
                       if killer is not None and event.by != event.target
                       else 'You died')

    def _pickedUp(self, event: arenamod.PickedUp) -> None:
        """Say what the player just walked over.

        Only the player's own: the point of the line is *you now have this*,
        and a bot collecting a medikit across the level is not news.  Without
        it a pickup is invisible — the number in the corner goes up by
        twenty-five and nothing says why — which is indistinguishable from a
        bug, and is how items being missing read as the game being broken.
        """
        if self.hud is None or event.target != gamemod.PLAYER_ID:
            return
        self.hud.post('picked up %s' % (event.title or event.key,))

    def _bearing(self, shooter: str, camera: Sequence[float],
                 forward: Sequence[float]) -> float:
        """Which way a hit from ``shooter`` came from.

        Straight ahead when there is nobody to point at — the lava, a long
        fall — because the hit is still felt and the indicator would otherwise
        have to be suppressed for exactly the deaths a player most wants
        telling about.
        """
        one = self.match.combatant(shooter)
        if one is None:
            return 0.0
        return bearing_to(camera, forward, one.position)

    def _intensity(self, amount: int) -> float:
        """How hard a hit marks the screen, from how much of a life it took."""
        full = max(1.0, float(arenamod.STARTING_HEALTH) * FULL_MARK_DAMAGE)
        return min(1.0, float(amount) / full)

    # -- the state that is not an event ----------------------------------
    def _deathNotice(self, now: float) -> None:
        """Put the death notice up, count it down, and take it away again."""
        if self.hud is None:
            return
        me = self.match.combatant(gamemod.PLAYER_ID)
        dead = me is not None and not me.alive
        if dead:
            self.hud.died(self._cause, self._respawnIn(me))
        elif self._dead:
            # Coming back is a new body: the notice goes and so do the marks
            # the last one was still carrying.
            self.hud.revived()
        self._dead = dead

    def _respawnIn(self, me: Any) -> float:
        """Seconds until the player is allowed back, never below zero."""
        waited = 0.0 if me.dead_for is None else float(me.dead_for)
        return max(0.0, float(arenamod.RESPAWN_DELAY) - waited)
