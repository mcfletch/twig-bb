"""What a fight looks like: a burst where each shot landed, chosen by what it met.

The other reader of the match's event stream (:mod:`twig_bb.feedback` runs
both), and the visible half of the answer to "did that shot do anything".

**Stylised rather than realistic, on purpose.**  What this feedback is *for* is
letting a player read a confirmed hit across a room while both of them are
moving, so the bursts are bright, brief and unlike each other: stone puffs, metal
sparks, and a person is neither.

**One emitter per kind, bursting in many places.**  A firefight asks for a dozen
effects a second and a shotgun for eight in one frame, so a scenegraph node per
impact would mean editing the scene at that rate.  Instead each kind of effect is
a single :class:`~OpenGLContext.scenegraph.particles.ParticleEmitter` that is
never moved: the styling lives on the node and the *place* arrives per burst
through ``burst_at``.  Its particles are world-space, so a burst stays where it
was thrown when the next one happens somewhere else.

**Which effect a surface gets is our own reading of its name**, in
:data:`SURFACE_WORDS` — the texture path is the whole of what a map tells us
about what a wall is made of, and there is no format fact to look up.  Anything
unclassified gets the dust puff, because a plain effect is honest and *no*
effect reads as a shot that missed.

**The intensity setting filters presentation and cannot change play.**  It scales
the particle counts and nothing else; the events it reads are emitted by the
simulation whether anybody is drawing them or not, which is what makes it safe to
offer and safe for two players to set differently.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Sequence

import numpy as np

from OpenGLContext.scenegraph.group import Group
from OpenGLContext.scenegraph.particles import ParticleEmitter, preset

from . import arena as arenamod

log = logging.getLogger(__name__)

__all__ = [
    'Effects', 'BLOOD', 'DUST', 'GIBS', 'SPARKS', 'FULL', 'REDUCED', 'OFF',
    'INTENSITIES', 'SURFACE_WORDS', 'surface_kind', 'default_emitters',
]

#: The kinds of burst this game draws.
DUST = 'dust'
SPARKS = 'sparks'
BLOOD = 'blood'
GIBS = 'gibs'
BURST = 'burst'
TRAIL = 'trail'

#: Particles a projectile leaves behind per second of flight, when nothing has
#: said how fast it is going.  A trail is what makes an incoming rocket
#: readable *before* it arrives, which is the whole of what makes one
#: survivable.
TRAIL_RATE = 90.0

#: How far a projectile flies between one puff of smoke and the next, in
#: metres.  **A trail is laid along a path, not emitted over time**: at a rate
#: per second a rocket doing 26 m/s strings its smoke out in dots a third of a
#: metre apart -- a dotted line rather than a trail -- while a grenade rolling
#: to a stop piles it up in one place.  Spacing by distance makes the trail
#: read the same behind anything, at any speed, and stops when the thing does.
#:
#: It is set together with the trail emitter's ``size``, and the pair is the
#: whole of whether this looks like smoke: a puff has a soft edge, so it has to
#: be appreciably *wider* than this to close the gap to the next one.  Widen
#: the spacing without widening the puffs and the trail beads into dots.
TRAIL_SPACING = 0.4

#: How far behind a projectile's middle its smoke is left, in metres.  A rocket
#: trails from its nozzle, and the nozzle is a place on the model: it is
#: therefore a fixed distance back along the heading and **not** a function of
#: speed, which would have a fast rocket smoking from further and further
#: behind itself.  Half the drawn length of the rocket, so it starts at the
#: tail rather than out of the middle of the warhead.
TRAIL_SETBACK = 0.16

#: How much of the presentation to show.  Play is identical at all three.
FULL, REDUCED, OFF = 'full', 'reduced', 'off'

#: What each setting multiplies a burst's particle count by.  ``REDUCED`` is a
#: third rather than a half because the point of it is a machine that cannot
#: afford the full thing, and halving is not much of a saving.
INTENSITIES: Dict[str, float] = {FULL: 1.0, REDUCED: 0.34, OFF: 0.0}

#: Words in a texture path that say what a surface is made of, and the effect
#: that follows.  **Ours, not a format fact**: a map states a texture path and
#: nothing else about its material, so this is a reading rather than a lookup,
#: and it is a table so that a content pack full of unusual names can be
#: accommodated by editing data.
SURFACE_WORDS: Dict[str, str] = {
    'metal': SPARKS,
    'steel': SPARKS,
    'grate': SPARKS,
    'grill': SPARKS,
    'iron': SPARKS,
    'pipe': SPARKS,
    'trim': SPARKS,
    'panel': SPARKS,
    'tech': SPARKS,
}

#: What a surface nobody has classified gets.  A puff of dust, because a plain
#: effect reads as "that hit the wall" and no effect reads as a miss.
DEFAULT_SURFACE_KIND = DUST


def _backwards(velocity: Any) -> Optional[np.ndarray]:
    """The unit vector opposite ``velocity``, or None for something stationary."""
    heading = np.asarray(velocity, dtype=float)[:3]
    length = float(np.linalg.norm(heading))
    return None if length == 0.0 else -heading / length


def surface_kind(surface: str) -> str:
    """Which burst a level surface gets, from its texture path.

    **Anywhere in the path, not as a whole word.**  Real content spells the
    same material as ``metalfloor``, ``e7bmetal``, ``basemetal`` and
    ``metal01``, and a rule that demanded a separator either side would miss
    three of those four.  The cost is that a word merely containing one of
    these is read as it — which is a puff of the wrong colour, and cheaper
    than most map surfaces having no effect at all.

    The longest match wins, so a table gaining a more specific word later
    outranks the general one it sits inside without anything being reordered.
    """
    path = str(surface).lower()
    for word in sorted(SURFACE_WORDS, key=len, reverse=True):
        if word in path:
            return SURFACE_WORDS[word]
    return DEFAULT_SURFACE_KIND


def default_emitters() -> Dict[str, ParticleEmitter]:
    """One emitter per kind, styled for what it says.

    Started from §8's shipped presets and then tuned, because what these have
    to do is different from what a torch or a rocket trail has to do: they are
    read at a glance during a fight and then must be gone before the next one.

    **None of them goes off on its own.**  Every one exists to be fired at a
    place an event names, and an emitter that released its first burst when the
    scene was drawn would put one stray puff of each at the middle of the world
    every time a level loaded.

    A function rather than a constant: every field is writable, and one match
    retuning its blood should not retune every other match in the process.
    """
    return {
        # Off-white and gritty, thrown out of the wall and pulled down again.
        DUST: preset('impact', burstOnStart=False, burst=22,
                     maxParticles=320, lifetime=0.4, speed=2.6, spread=0.9,
                     size=0.11, endSize=0.03, blending='alpha', alpha=0.7,
                     color=(0.78, 0.74, 0.66), endColor=(0.35, 0.33, 0.30)),
        # Bright, fast and short: metal reads as a shower rather than a cloud.
        SPARKS: preset('sparks', burstOnStart=False, burst=26,
                       maxParticles=320, lifetime=0.35, speed=5.5, spread=0.8,
                       size=0.055, endSize=0.01),
        # The one that must be legible across a room at speed, so it is the
        # brightest and the only red thing a fight produces.
        BLOOD: preset('impact', burstOnStart=False, burst=30,
                      maxParticles=384, lifetime=0.5, speed=3.4, spread=1.1,
                      size=0.15, endSize=0.02,
                      color=(1.0, 0.22, 0.2), endColor=(0.4, 0.0, 0.0)),
        # A death is bigger and slower than a hit, so the two are never
        # confused at the moment one becomes the other.
        GIBS: preset('impact', burstOnStart=False, burst=64,
                     maxParticles=512, lifetime=0.9, speed=5.0, spread=np.pi,
                     size=0.2, endSize=0.03,
                     color=(1.0, 0.25, 0.22), endColor=(0.3, 0.0, 0.0)),
        # A detonation: the biggest thing the game draws, and the only one
        # that has to be read from across the level rather than at a glance.
        BURST: preset('explosion', burstOnStart=False, burst=120,
                      maxParticles=768, lifetime=0.8, speed=8.5,
                      size=0.7, endSize=0.05),
        # Smoke out of the back of a rocket, from §8's smoke preset: slow,
        # alpha-blended and long-lived, which is what makes an incoming one
        # readable before it arrives -- and that is what makes a rocket
        # survivable rather than merely fatal.  Rate zero: this one is driven
        # from the projectiles' positions by `trail`, because an emitter with a
        # rate emits where *it* is and a trail has to come from wherever each
        # rocket has got to.  The cone stays well inside a right angle so that
        # smoke thrown backwards cannot overtake the rocket it came out of.
        # Few, large and soft rather than many and small: a puff wider than
        # `TRAIL_SPACING` joins up into smoke, and one narrower than it beads
        # into a dotted line however many are spent.  A budget of 900 is about
        # ten rockets in the air at once trailing fully, which is more than a
        # match puts up; past that the pool runs out, which is a pool working.
        TRAIL: preset('smoke', burstOnStart=False, rate=0.0, burst=1,
                      maxParticles=900, lifetime=1.4, lifetimeVariation=0.35,
                      speed=0.8, speedVariation=0.4, spread=0.6,
                      gravity=(0.0, 0.5, 0.0), drag=1.4,
                      size=0.90, endSize=2.2, sizeVariation=0.35, alpha=0.55,
                      color=(0.72, 0.70, 0.68), endColor=(0.26, 0.25, 0.26)),
    }


class Effects:
    """One match's events, drawn as bursts of particles.

    Put :attr:`group` in the scene once; everything after that is
    :meth:`show`, and the emitters are never moved or replaced.
    """

    def __init__(self, match: Any, emitters: Optional[Dict[str, Any]] = None,
                 intensity: str = FULL) -> None:
        self.match = match
        #: The emitters, by kind.  Readable so a settings screen can present
        #: their fields: each is a declared node like every other.
        self.emitters = default_emitters() if emitters is None else emitters
        #: One of :data:`INTENSITIES`.  Writable while playing, because that is
        #: what a settings screen does with it.
        self.intensity = intensity
        #: What goes in the scene.  One group, made once.
        self.group = Group(children=list(self.emitters.values()))
        #: Fractional trail particles carried between frames, so a trail is
        #: the same length whatever the frame rate.
        #: Particles owed to the trail, when it is being driven at a rate.
        self._owed = 0.0
        #: Metres each projectile slot has flown since it last left a puff.
        #: Per slot rather than one number, because two projectiles going
        #: different speeds owe different amounts of smoke.
        self._flown = np.zeros(0, dtype=float)

    @property
    def scale(self) -> float:
        """What this intensity multiplies a burst by.

        An unknown setting is read as full rather than as nothing: a typo in a
        configuration file should leave a game visible, not silently strip its
        feedback out.
        """
        return INTENSITIES.get(str(self.intensity), 1.0)

    def show(self, events: Sequence[Any]) -> int:
        """Draw what ``events`` look like; returns how many particles were born."""
        scale = self.scale
        if scale <= 0.0:
            return 0
        born = 0
        for event in events:
            born += self._draw(event, scale)
        return born

    def _draw(self, event: Any, scale: float) -> int:
        """One event's burst, or nothing for an event that has no picture.

        Firing draws nothing here on purpose: a muzzle flash belongs to the
        weapon in the player's hands and to the first-person rig that holds
        it, not to a burst in the world at the shooter's feet.
        """
        if isinstance(event, arenamod.Impact):
            kind = (BLOOD if event.on_somebody
                    else surface_kind(event.surface))
            return self._burst(kind, event.point, event.normal, scale)
        if isinstance(event, arenamod.Detonated):
            return self._burst(BURST, event.point, (0.0, 1.0, 0.0), scale)
        if isinstance(event, arenamod.Death):
            where = self._where(event.target)
            return 0 if where is None else self._burst(GIBS, where,
                                                       (0.0, 1.0, 0.0), scale)
        return 0

    def trail(self, points: Any, dt: float,
              velocities: Optional[Any] = None) -> int:
        """Leave smoke behind everything in flight; returns particles born.

        Driven from the *positions* each frame rather than from an emitter per
        projectile, because there is one trail emitter and hundreds of things
        that may be flying: what varies is where, and ``burst_at`` is exactly
        the shape of that.

        Given ``velocities`` as well, each projectile smokes from
        :data:`TRAIL_SETBACK` behind itself, throws its smoke backwards, and
        lays a puff down every :data:`TRAIL_SPACING` metres it flies -- which
        is what a rocket does, and what stops the trail coming out of the
        middle of the warhead in a dotted line.  Without them the smoke is left
        where the projectile is at a rate per second, because a position on its
        own says neither which way round the thing is nor how far it has come.

        Either way the remainder is carried between frames, so a projectile
        leaves the same trail at any frame rate rather than a denser one on a
        faster machine.
        """
        scale = self.scale
        emitter = self.emitters.get(TRAIL)
        if scale <= 0.0 or emitter is None or not len(points):
            return 0
        if velocities is not None:
            return self._trailAlong(points, velocities,
                                    max(0.0, float(dt)), scale, emitter)
        self._owed += TRAIL_RATE * max(0.0, float(dt)) * scale
        each = int(self._owed)
        if each <= 0:
            return 0
        self._owed -= each
        return sum(emitter.burst_at(point, count=each) for point in points)

    def _trailAlong(self, points: Any, velocities: Any, dt: float,
                    scale: float, emitter: Any) -> int:
        """A puff every :data:`TRAIL_SPACING` metres, per projectile.

        The metres each one has flown without smoking yet are kept per slot: at
        a hundred frames a second a rocket covers less than one spacing in a
        frame, and a count rounded off every frame would be zero every frame.
        """
        speeds = np.linalg.norm(np.asarray(velocities, dtype=float)[:, :3], axis=1)
        if self._flown.shape[0] < speeds.shape[0]:
            grown = np.zeros(speeds.shape[0], dtype=float)
            grown[:self._flown.shape[0]] = self._flown
            self._flown = grown
        flown = self._flown[:speeds.shape[0]]
        flown += speeds * dt * scale
        counts = np.floor_divide(flown, TRAIL_SPACING).astype(int)
        flown -= counts * TRAIL_SPACING

        born = 0
        for index, count in enumerate(counts):
            if count <= 0:
                continue
            back = _backwards(velocities[index])
            where = points[index] if back is None else (
                np.asarray(points[index], dtype=float)[:3] + back * TRAIL_SETBACK)
            born += emitter.burst_at(where, direction=back, count=int(count))
        return born

    def _burst(self, kind: str, point: Sequence[float],
               normal: Sequence[float], scale: float) -> int:
        """Release one kind of burst at a point, scaled by the setting.

        At least one particle whenever the setting is not off: a reduced
        setting that rounded a small burst away would leave *some* impacts
        with no effect at all, which reads as a shot that missed rather than
        as a setting.
        """
        emitter = self.emitters.get(kind)
        if emitter is None:
            return 0
        count = max(1, int(round(float(emitter.burst) * scale)))
        return emitter.burst_at(point, direction=normal, count=count)

    def _where(self, id: str) -> Optional[Sequence[float]]:
        """Where a combatant is, or None if they have left the match."""
        one = self.match.combatant(id)
        if one is None:
            return None
        return tuple(float(value) for value in one.position)
