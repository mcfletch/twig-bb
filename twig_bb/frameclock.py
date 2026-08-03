"""How much time the simulation is given each frame, and how much it is denied.

A frame that took a second must not be handed to the physics as a second: a
character moved that far in a single step passes straight through the floor it
should have landed on.  So the step is clamped, and clamping is the right answer
to that question.

It is also, on its own, an unreadable failure.  The world advances by the clamp
while the wall clock advances by the whole frame, so a game that hitches does
not freeze -- it runs in **slow motion**, at the ratio between the two -- while
the frame rate goes on reporting whatever the renderer managed.  A player
describes that as the controls having gone soft, and nothing on the screen
agrees with them.

:class:`FrameClock` owns the clamp and keeps the accounting the clamp destroys:
the frame's real duration, the world time discarded, the debt accumulated since
the map loaded, and the :attr:`pace` those imply.  It is the number that turns
"movement feels wrong" into "the world is running at a twentieth of speed
because frames are taking a second", which is a different bug entirely.

See :mod:`OpenGLContext.looptrace` for where that second went.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

__all__ = ['FrameClock']


class FrameClock:
    """The clamped simulation timestep, and what the clamp costs.

    Driven once per frame::

        dt = clock.tick(time.time())

    and read by the developer overlay through
    :func:`twig_bb.debug.player_provider`.
    """

    #: The longest step the physics is ever given, in seconds.  Twenty frames a
    #: second: far enough for a slow frame to stay continuous, short enough
    #: that a character never crosses a wall inside one step.
    MAX_STEP = 0.05

    def __init__(self, maximum: float = MAX_STEP) -> None:
        self.maximum = maximum
        self._last: Optional[float] = None
        #: The frame's real duration in seconds, before clamping.
        self.real = 0.0
        #: What the simulation was actually given.
        self.dt = 0.0
        #: World time this frame discarded, in seconds.
        self.lost = 0.0
        #: World time discarded since the last :meth:`reset`, in seconds.
        self.debt = 0.0

    def reset(self, now: float) -> None:
        """Start measuring from ``now``, forgetting any gap before it.

        Called when a map finishes loading.  A level load takes seconds that
        the player did not experience as a stall, and counting it as one would
        open every session with a debt it never has a way to explain.
        """
        self._last = now
        self.real = self.dt = self.lost = 0.0
        self.debt = 0.0

    def tick(self, now: float) -> float:
        """Advance to ``now`` and answer the step the simulation should take.

        A clock nobody has :meth:`reset` starts itself here and reports no
        elapsed time, because a first frame has no previous frame to be a
        duration from.
        """
        last, self._last = self._last, now
        if last is None:
            self.real = self.dt = self.lost = 0.0
            return 0.0
        self.real = now - last
        self.dt = min(self.real, self.maximum)
        self.lost = self.real - self.dt
        self.debt += self.lost
        return self.dt

    @property
    def pace(self) -> float:
        """Simulated seconds per real second this frame: 1.0 is real time.

        The number the player is feeling.  0.05 is a world running at a
        twentieth of speed, which is what a one-second frame does to a
        50-millisecond clamp.
        """
        if self.real <= 0.0:
            return 1.0
        return self.dt / self.real

    def describe(self) -> Dict[str, Any]:
        """Rows for the developer overlay, quiet when there is nothing wrong.

        ``behind`` appears only on a frame the clamp actually bit, because on a
        healthy frame it says the same thing as ``dt ms`` and a panel has
        better uses for the line.
        """
        found: Dict[str, Any] = {'dt ms': self.dt * 1000.0}
        if self.lost > 0.0:
            found['real ms'] = self.real * 1000.0
            found['behind'] = '%d%% speed, %.1fs lost' % (
                round(self.pace * 100.0), self.debt)
        return found
