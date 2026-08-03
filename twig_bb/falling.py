"""Where the level runs out, and what happens to anybody who leaves it.

A map bounds its geometry and nothing else. Step off the edge of one built as
an island — or be blown off it, or walk through a wall a probe missed — and
there is nothing below to land on and nothing above to come back to: the fall
never ends, the camera never stops, and no message is ever printed. To a
player that reads as the game having hung rather than as a mistake they made,
which is the worst way for a game to answer anything.

:class:`KillFloor` is the answer: a height below which the world is over. It is
placed from the map's *own* bounds rather than being a constant, because a
level a hundred metres tall and one ten metres tall do not share a bottom, and
it kills with a named cause so the line a player reads says what happened.

It applies to bots as well, which also bounds what a bot walking into geometry
can do to itself: one that has sunk through the floor is now a frag rather than
a body vibrating under the level for the rest of the match.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

__all__ = ['FALL_MARGIN', 'FELL', 'KillFloor']

#: How far below a map's own bounds the floor of the world sits, in metres.
#: Far enough that it cannot be reached from inside the level — the bounds
#: already contain every surface the map has, so anything this far under them
#: has left — and near enough that the fall is over in about four seconds
#: rather than being its own kind of hang.
FALL_MARGIN = 100.0

#: What the death is called.  Named rather than left blank, so
#: :data:`twig_bb.game.DEATH_CAUSES` can phrase it and nothing has to guess
#: at it from a death with no killer.
FELL = 'fall'


class KillFloor:
    """A height below which nothing survives.

    Ticked with the match, like the liquids are, and — like them — it reads
    positions and writes damage and knows nothing about cameras or capsules.
    Nothing here reads a clock: falling past the floor is not a thing that
    takes time.
    """

    def __init__(self, height: float) -> None:
        #: The scene-space height, in metres, below which the world is over.
        self.height = float(height)

    @classmethod
    def under(cls, loaded: Any,
              margin: float = FALL_MARGIN) -> Optional['KillFloor']:
        """The floor for a loaded map, or None when there is no map.

        ``margin`` is a *distance* below the map, so its sign is not a way to
        put the floor above one: a level whose players all died on spawning
        would be a stranger bug than the one this fixes.
        """
        if loaded is None:
            return None
        low, _high = loaded.world.bounds
        return cls(float(low[1]) - abs(float(margin)))

    def advance(self, arena: Any) -> int:
        """Kill everybody who has fallen past the floor; returns how many.

        No ``dt``: the other per-tick rules take one because what they do
        depends on how long it has been, and this one does not.  A signature
        that took a number it ignored would be an invitation to believe the
        floor could be tuned by the frame rate.
        """
        killed = 0
        for id in arena.ids():
            one = arena.combatant(id)
            if one is None or not one.alive:
                continue
            if float(one.position[1]) > self.height:
                continue
            # Killed rather than damaged: armour is for being shot, and the
            # bottom of the world is not a hit.
            killed += int(arena.kill(id, cause=FELL))
        return killed

    def describe(self) -> Dict[str, Any]:
        """What this is watching, as rows for the developer overlay."""
        return {'kill floor (m)': self.height}
