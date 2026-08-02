"""A body for everybody the rules move, so nobody walks through a wall.

Everyone in a match walks in **the player's own capsule**: the same
move-and-slide, the same step height, the same slopes, the same ground snap.
An opponent climbs a step because the controller does, slides along a wall it
meets at an angle because the controller does, and falls off a ledge because
the controller does — so anywhere a player can go one can follow, and the only
difference between them is the pace.

A capsule is what makes that true and a ray probe is not. A probe is a line and
a level is not: a line misses the corner, the thin brush and the riser it was
not aimed at, it says nothing about what is *under* a body, and something
pushing a body out of geometry while its heading pushes it back in resolves at
frame rate into a shudder. :meth:`Walkers.place` goes through
:meth:`~omi_physics.character.CharacterController.safe_bind`, so a body put
where a level's geometry is gets dug back out of it.

The player's own capsule is *not* one of these. It is driven by a person
through the navigation platform, and giving it a second owner here would be two
things writing one position. What this owns is everybody the rules move.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, Optional

import numpy as np
from numpy.typing import ArrayLike

from omi_physics.character import CharacterController

log = logging.getLogger(__name__)

__all__ = ['Walkers']

#: Which way is up, once.
UP = np.array([0.0, 1.0, 0.0])


class Walkers:
    """One character controller per combatant the rules move, by id.

    Made lazily: a bot gets a body the first time it is asked to move, seated
    out of whatever geometry it was placed in.  That is deliberate — a match is
    built before there is a physics world to put anybody in, and a table that
    had to be filled in at exactly the right moment is a table that will be
    empty at the wrong one.
    """

    def __init__(self, world: Any, capabilities: Any,
                 gravity: float = 9.81) -> None:
        self.world = world
        #: The proportions and speeds every walker shares.  The player's own,
        #: because a bot that could not go where the player can is a bot that
        #: reads as broken rather than as different.
        self.capabilities = capabilities
        self.gravity = float(gravity)
        self._walkers: Dict[str, CharacterController] = {}

    def __len__(self) -> int:
        return len(self._walkers)

    def __contains__(self, id: str) -> bool:
        return id in self._walkers

    def __iter__(self) -> Iterator[str]:
        return iter(self._walkers)

    def of(self, id: str) -> Optional[CharacterController]:
        """The controller walking as ``id``, or None if there is not one yet."""
        return self._walkers.get(id)

    def place(self, id: str, feet: ArrayLike) -> CharacterController:
        """Put ``id`` in the world standing at ``feet``, out of any geometry.

        Through ``safe_bind``, which depenetrates and then snaps onto the floor
        below: a spawn point that is a little inside a wall, or a little under
        the floor, is a level-authoring fact rather than an error, and this is
        the same thing that keeps the player's own camera out of the ground.

        **From a step height up, and dropped.**  Depenetration answers "which
        way is out" by how deep each contact is, and a capsule whose feet are
        under a thick floor is deepest through the *top*, so resolving it puts
        it under the level rather than on it.  Starting a little above and
        snapping down never has to make that choice: a spawn point is a place
        to *stand*, and standing means on top of the floor rather than in it.
        The lift is the step height because that is already this game's
        statement of how far a body may be off the ground and still be
        walking; anything buried deeper than that falls, which the kill floor
        turns into a respawn rather than into a body vibrating for ever.

        Replaces whatever was walking as ``id``, so a respawn is a fresh body
        rather than the old one teleported with its fall speed intact.
        """
        stood = np.asarray(feet, dtype='d')[:3]
        centre = stood + UP * (self.capabilities.standHeight * 0.5
                               + self.capabilities.stepHeight)
        walker = CharacterController(self.world, self.capabilities,
                                     position=centre, gravity=self.gravity)
        if not walker.safe_bind(centre):    # pragma: no cover - no map does it
            # Somewhere with no clear space at all, which no level presents:
            # depenetration walks a capsule out of anything a map is made of.
            # Said out loud rather than left silent, because the alternative
            # symptom is a bot that simply stands still for ever.
            log.warning('%s was placed with no clear space at %s', id, stood)
        self._walkers[id] = walker
        return walker

    def forget(self, id: str) -> None:
        """Take somebody's body out of the world.  A match ending, a bot removed."""
        self._walkers.pop(id, None)

    def walk(self, id: str, feet: ArrayLike,
             heading: Optional[ArrayLike], dt: float) -> np.ndarray:
        """Move ``id`` along ``heading`` for ``dt``; returns where they stand.

        ``heading`` of None is standing still, which is *not* the same as not
        being stepped: gravity, a slope and whatever a burst threw them with
        all still apply, and a bot standing at the top of a ramp should slide
        down it rather than hang there.
        """
        walker = self._walkers.get(id)
        if walker is None:
            walker = self.place(id, feet)
        walker.set_move(np.zeros(3) if heading is None
                        else np.asarray(heading, dtype='d'))
        walker.update(max(0.0, float(dt)))
        return walker.base()

    def shove(self, id: str, velocity: ArrayLike) -> bool:
        """Throw somebody, in metres per second; False if they have no body.

        The controller's own impulse, which is what a jump pad uses and what
        the player takes a rocket with — so a bot is blown off a ledge by the
        same machinery, in all three axes rather than only the horizontal.
        """
        walker = self._walkers.get(id)
        if walker is None:
            return False
        walker.apply_impulse(np.asarray(velocity, dtype='d'))
        return True

    def describe(self) -> Dict[str, Any]:
        """What this is holding, as rows for the developer overlay."""
        stuck = sum(1 for walker in self._walkers.values() if walker.stuck)
        return {'walkers': len(self._walkers), 'stuck': stuck}
