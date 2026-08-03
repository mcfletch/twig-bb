"""Where the view goes while the player is dead.

Being killed used to leave the camera exactly where it stood, still steered by
the mouse and still walked about by the keys, with a line of text saying it had
happened. That reads as the *message* being wrong rather than as a death:
nothing about the world changed, and the one thing a player is certain of is
what they can see.

So death takes the camera away. It drops to near the floor, where a body would
be, and looks at whoever did it — which is the only piece of information a
player wants in that second and the one they cannot get any other way. The
world goes on being drawn behind a red wash, because watching the fight
continue without you is most of what a death *is*.

**And it ends when the player says so.** A countdown that respawns you while
you are reading the scoreboard is a countdown that puts you back in a corridor
you were not looking at. The timer becomes a floor rather than a trigger: it is
the shortest a death can be, and pulling the trigger is what ends it.

Nothing here reads a clock and nothing here draws: it is given seconds and
answers with a position and an orientation, so where the camera goes when you
die is a test rather than something somebody has to go and get killed to see.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional, Sequence, Tuple

import numpy as np
from OpenGLContext import quaternion

log = logging.getLogger(__name__)

__all__ = ['DeathCamera', 'DROP_SECONDS', 'EYE_HEIGHT', 'WASH', 'WASH_COLOUR']

#: How far above the feet the death camera settles, in metres.  Low, because
#: what makes the shot read as a body on the floor is being *under* everything
#: that is still standing.
EYE_HEIGHT = 0.4

#: Seconds the view takes to fall from where it was killed to that height.  A
#: fall rather than a cut: a cut at the moment of death is indistinguishable
#: from the game having reloaded, and it is the movement that says *you*.
DROP_SECONDS = 0.55

#: How red the world goes, and how solid.  Solid enough to be unmistakable and
#: well short of a curtain: the fight going on without you is the point of
#: leaving the world drawn at all, and a wash that hid it would leave a red
#: rectangle with a countdown on it.
WASH_COLOUR = (0.65, 0.04, 0.04)
WASH = 0.42


class DeathCamera:
    """The view while the player is dead: where it is and which way it faces.

    Made once and reused.  :meth:`begin` starts a death, :meth:`advance` moves
    it on by ``dt`` and :meth:`end` puts the view back in the living player's
    hands.  It holds no window, no platform and no clock.
    """

    def __init__(self, eye_height: float = EYE_HEIGHT,
                 drop: float = DROP_SECONDS) -> None:
        self.eye_height = float(eye_height)
        self.drop = max(1e-6, float(drop))
        #: Whether the player is dead right now.
        self.watching = False
        #: Seconds since the death.
        self.elapsed = 0.0
        self._from = np.zeros(3)
        self._to = np.zeros(3)
        self._yaw = 0.0
        self._pitch = 0.0

    # -- the death --------------------------------------------------------
    def begin(self, eye: Sequence[float], feet: Sequence[float],
              yaw: float = 0.0,
              killer: Optional[Sequence[float]] = None) -> None:
        """Take the view, from ``eye``, for a body standing at ``feet``.

        ``killer`` is where whoever did it is standing, and turns the shot
        towards them.  Without one — the lava, a long fall, a fight nobody
        won — the view keeps the heading it was killed on, which is honest:
        there is nothing to look at.
        """
        self.watching = True
        self.elapsed = 0.0
        self._from = np.asarray(eye, dtype='d')[:3].copy()
        self._to = (np.asarray(feet, dtype='d')[:3]
                    + np.array([0.0, self.eye_height, 0.0]))
        self._yaw, self._pitch = float(yaw), 0.0
        if killer is not None:
            self._yaw, self._pitch = self._look_at(np.asarray(killer,
                                                              dtype='d')[:3])

    def advance(self, dt: float) -> None:
        """Move the death on by ``dt`` seconds."""
        if self.watching:
            self.elapsed += max(0.0, float(dt))

    def end(self) -> None:
        """Give the view back.  Idempotent: two respawns are one respawn."""
        self.watching = False
        self.elapsed = 0.0

    # -- what the camera does ---------------------------------------------
    def position(self) -> np.ndarray:
        """Where the camera is now: falling, then settled.

        Eased rather than linear, so the fall arrives rather than stopping —
        a constant-speed drop that halts dead at the floor reads as a bug in
        the interpolation, which is the last thing a death should look like.
        """
        share = min(1.0, self.elapsed / self.drop)
        eased = 1.0 - (1.0 - share) ** 3
        return self._from + (self._to - self._from) * eased

    def orientation(self) -> Any:
        """Which way it faces, in the platform's own terms.

        The same pitch-then-yaw composition
        :meth:`~OpenGLContext.move.physicsplatform.PhysicsViewPlatform.camera_orientation`
        uses, so a death camera and a living one mean the same thing by an
        angle and the view does not snap when one hands over to the other.
        """
        return (quaternion.fromXYZR(1, 0, 0, self._pitch)
                * quaternion.fromXYZR(0, 1, 0, self._yaw))

    def apply(self, platform: Any) -> None:
        """Put this frame's view onto a platform."""
        platform.setPosition(tuple(self.position()))
        platform.setOrientation(self.orientation())

    def wash(self) -> float:
        """How strong the red is, 0 to 1.

        It comes up with the fall rather than snapping on, for the same reason
        the drop is eased: the two are one movement and a wash that arrived
        first would read as a screen effect rather than as dying.
        """
        if not self.watching:
            return 0.0
        return WASH * min(1.0, self.elapsed / self.drop)

    # -- pointing at whoever did it ---------------------------------------
    def _look_at(self, target: np.ndarray) -> Tuple[float, float]:
        """The yaw and pitch that face ``target`` from where this settles."""
        to = target - self._to
        flat = math.hypot(float(to[0]), float(to[2]))
        if flat < 1e-6 and abs(float(to[1])) < 1e-6:
            return (self._yaw, 0.0)
        # The same basis `PhysicsViewPlatform._world_dir` derives its forward
        # from: at a yaw of zero the camera looks down -Z.  The pitch is
        # *negated* because that is what the platform's own composition means
        # by one -- a positive pitch looks down -- and the two have to agree,
        # or the view flips the moment a respawn hands it back.
        yaw = math.atan2(float(to[0]), -float(to[2]))
        return (yaw, -math.atan2(float(to[1]), flat))
