"""One tick of a match, with nothing in it that draws.

[§11](../PROJECT-PLAN.md)'s seam as an object. Everything that *happens* in a
frame — the bots deciding, the projectiles flying, the map's hazards biting,
the respawns falling due — is here, and everything that *shows* it stays in the
viewer: bodies moved, effects emitted, the HUD written, sounds played.

It is a module rather than a run of lines in the frame loop because **a frame
loop cannot be tested**. A line inside `OnDraw` is reachable only by a person
playing the game, and a rule that is only ever checked by a person is a rule
that breaks quietly. What is here runs against a constructed world with no
window, no clock and no frames, so a whole match can be played out in a test.

Nothing here reads a wall clock: time arrives as ``dt``, which is what lets a
match replay from its inputs.
"""

from __future__ import annotations

import copy
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

import numpy as np
from omi_physics import character

from . import combat, game, walkers

log = logging.getLogger(__name__)

__all__ = ['Rules', 'Tick']


@dataclass
class Tick:
    """What one advance of the rules produced.

    ``events`` is the match's stream, drained: the one thing presentation
    reads.  ``respawned`` is separate because a respawn is the one outcome the
    *camera* has to answer — the player's body is published from where they
    are looking, so a respawn the camera was never told about is overwritten
    on the very next frame.  It is keyed by id and gives the **feet**, which
    is how the arena addresses everybody.
    """

    events: List[Any] = field(default_factory=list)
    respawned: Dict[str, np.ndarray] = field(default_factory=dict)


class Rules:
    """A match being played: the opponents, what is in the air, and the map's hazards.

    Built once per match and advanced once per frame.  It writes to the arena
    and reads the physics world; it holds no scenegraph, no HUD and no clock.
    """

    def __init__(self, arena: Any, minds: Dict[str, Any], flight: Any,
                 spawns: Sequence[Any] = (), harm: Any = None,
                 floor: Any = None, capabilities: Any = None,
                 gravity: float = 9.81, seed: Optional[int] = None) -> None:
        self.arena = arena
        #: One mind per bot, by id.  A dict rather than a list because a
        #: respawn has to find one to reset.
        self.minds = minds
        #: Everything in the air.
        self.flight = flight
        #: Where a respawn may put somebody, as **feet** — which is how the
        #: arena addresses everybody and where a capsule sits.
        self.spawns = [np.asarray(spawn, dtype='d') for spawn in spawns]
        #: What standing in slime or lava costs, or None for a map with none.
        self.harm = harm
        #: Where the world runs out, or None for a match with no map.
        self.floor = floor
        #: What the map left lying about, or None for a match with no map.
        #: See :mod:`twitchoglc.items`.
        self.pickups: Any = None
        #: The capsule everybody the rules move walks in, or None to take the
        #: controller's own defaults.  The player's, so a bot can go wherever
        #: a player can.
        self.capabilities = capabilities
        self.gravity = float(gravity)
        #: A body for each of them; made on the first tick, because a match is
        #: assembled before there is a world to stand anybody in.
        self.walking: Optional[walkers.Walkers] = None
        #: Who has to *ask* to come back rather than being returned on a
        #: timer.  The player, because a countdown that respawns you while you
        #: are reading the scoreboard puts you back in a corridor you were not
        #: looking at -- the timer is the shortest a death may be, and pulling
        #: the trigger is what ends it.  A bot asks for itself; see
        #: :meth:`respawn_due`.
        self.on_request = {game.PLAYER_ID}
        self._asked: Set[str] = set()
        #: What decides between several equally good spawn points.  Its own
        #: generator rather than the module's, so a match seeded the same way
        #: plays out the same way -- which is what a replay and, later, a
        #: server reconciling with a client both need.
        self.chance = random.Random(seed)

    def advance(self, world: Any, dt: float, weapon: Any, seed: int = 0,
                surfaces: Optional[Any] = None) -> Tick:
        """Play one tick; returns what happened.

        The order is the one the outcomes require rather than the one the
        pieces were written in.  Projectiles land **before** the respawns are
        counted, so somebody a rocket killed this tick starts waiting this
        tick rather than a frame late.  The respawns happen **before** the
        events are drained, so a death notice that has just stopped being true
        is taken down in the frame it stopped.
        """
        step = max(0.0, float(dt))
        if self.walking is None:
            self.walking = walkers.Walkers(world, self._capabilities(),
                                           gravity=self.gravity)
        if weapon is not None:
            game.step_bots(world, self.arena, self.minds, step, weapon,
                           seed=seed, surfaces=surfaces, flight=self.flight,
                           walking=self.walking)
        game.step_projectiles(world, self.arena, self.flight, step)
        # Before the hazards, so a medikit taken in the same tick as a bite of
        # lava is health the player had when it bit rather than health they
        # never got.
        if self.pickups is not None:
            self.pickups.advance(self.arena, step)
        if self.harm is not None:
            self.harm.advance(self.arena, step)
        if self.floor is not None:
            self.floor.advance(self.arena)
        self.arena.advance(step)
        back = self.respawn_due()
        return Tick(events=self.arena.drain(), respawned=back)

    def respawn_due(self) -> Dict[str, np.ndarray]:
        """Bring back everybody whose wait is over; returns where, by id.

        The **feet**, which is where a body stands and what a shot meets;
        whoever owns a camera adds the eye height to it.

        A bot's mind is reset here rather than by the arena: coming back is a
        rules event and forgetting what you were doing is part of it, and a
        bot that respawned across the level still hunting the target it last
        saw is a bot that walks into a wall.  Its *body* is replaced too, so a
        respawn arrives standing rather than still carrying the fall that
        killed it.
        """
        found: Dict[str, np.ndarray] = {}
        for id in self.arena.due_to_respawn():
            if id in self.on_request and id not in self._asked:
                continue
            self._asked.discard(id)
            one = self.arena.combatant(id)
            feet = game.spawn_for(self.spawns, self.arena, id,
                                  chooser=self.chance)
            if feet is None:
                # A match with no spawn points at all -- which a loaded map
                # never is.  Back where they fell: a poor place to arrive, and
                # much better than never arriving.
                feet = np.asarray(one.position, dtype='d')
            self.arena.respawn(id, position=feet)
            mind = self.minds.get(id)
            if mind is not None:
                mind.reset()
            if self.walking is not None and id in self.minds:
                # A fresh body at the new place, dug out of whatever it was
                # put in.  The player's is the camera's and is bound by
                # whoever owns that.
                self.walking.place(id, feet)
            found[id] = feet
        return found

    def ask_to_respawn(self, id: str) -> bool:
        """Say somebody wants to come back; False if they are not dead.

        Held rather than acted on, because the wait may not be over yet:
        pressing fire the instant you die should bring you back the moment it
        *is* over, not be swallowed for having been early.  That is the same
        courtesy the jump buffer does for a jump asked for just before
        landing, and for the same reason -- an input a game ignores without
        saying so is an input the player believes they did not make.
        """
        one = self.arena.combatant(id)
        if one is None or one.alive:
            return False
        self._asked.add(id)
        return True

    def waiting_to_come_back(self, id: str) -> bool:
        """Whether ``id`` is dead and has not asked to return."""
        one = self.arena.combatant(id)
        return (one is not None and not one.alive
                and id in self.on_request and id not in self._asked)

    def _capabilities(self) -> Any:
        """The capsule a walker gets: the player's, at a bot's own pace.

        A bot that moved exactly as fast as a player can would be impossible
        to escape and dull to chase, and that is the *only* difference: same
        size, same step height, same slopes, so anywhere a player can go a bot
        can follow.
        """
        caps = copy.copy(self.capabilities) if self.capabilities is not None \
            else character.CharacterCapabilities()
        caps.walkSpeed = game.BOT_SPEED
        return caps

    def publish(self, id: str, eye: Sequence[float]) -> bool:
        """Put a camera into the match as somebody's body; False while dead.

        The player is the one combatant the rules do not move: they move
        because a person did, and the arena hears about it here.  **Not while
        dead** — a corpse is not where the camera is, and publishing anyway
        puts a shootable target under a player who has no body and overwrites
        the position a respawn has just chosen.
        """
        one = self.arena.combatant(id)
        if one is None or not one.alive:
            return False
        one.position = (np.asarray(eye, dtype='d')[:3]
                        - np.array([0.0, combat.EYE_HEIGHT, 0.0]))
        return True

    def describe(self) -> Dict[str, Any]:
        """What is being played, as rows for the developer overlay."""
        found: Dict[str, Any] = {'spawn points': len(self.spawns),
                                 'minds': len(self.minds)}
        for part in (self.walking, self.pickups):
            if part is not None:
                found.update(part.describe())
        return found
