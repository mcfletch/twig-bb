#! /usr/bin/env python
"""``twig-bb-bots`` -- a bot's animation, played out of the game, as pictures.

A combatant is a hard thing to look at while it is being shot at. What it is
doing is decided by :mod:`twig_bb.characters` from what the rules know, drawn
by :func:`twig_bb.game.move_bodies`, and only ever seen for a frame at a time
from wherever the fight happens to be. So this takes that whole path -- the
same arena, the same cast, the same `move_bodies` -- puts one bot in front of a
camera, scripts what the rules say it is doing, and lays the frames out::

    twig-bb-bots --out sheets/
    twig-bb-bots --out sheets/ --takes run-forward,strafe --seconds 2
    twig-bb-bots --out sheets/ --build female_character --weapon pistol

One sheet per take: a row for each view, a column for each moment of it. What
that is *for* is the things a still cannot show and a fight will not hold
still for -- a figure running forwards while it moves backwards, an arm through
a ribcage, a wrist folded the wrong way, a weapon held at the belt.

Nothing here is a special path: the bot is moved by the same call the match
makes, so what lands on the sheet is what a player sees.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

os.environ.setdefault('OPENGLCONTEXT_BACKEND', 'glfw')
os.environ.setdefault('OPENGLCONTEXT_RENDERER', 'pbr')
os.environ.setdefault('OPENGLCONTEXT_SHADOWS', '0')
os.environ.setdefault('OPENGLCONTEXT_DISABLE_FPS_DISPLAY', '1')
os.environ.setdefault('OPENGLCONTEXT_HIDDEN', '1')

import numpy as np                                              # noqa: E402

from twig_bb import arena as arenamod                           # noqa: E402
from twig_bb import characters, game                            # noqa: E402
from twig_bb import weapons as weapontable                      # noqa: E402

__all__ = ['TAKES', 'VIEWS', 'Take', 'Script', 'Review', 'main']

#: Where the bot stands, and where the camera looks from.  Far enough back that
#: a whole figure is in frame with room to move, near enough that a wrist is
#: still several pixels.
STAGE = (0.0, 0.0, 0.0)
CAMERA = (0.0, 1.05, 2.9)

#: How big one frame is on the sheet.
CELL = (200, 300)

#: The ways round a figure worth watching it from, as a camera yaw in degrees.
VIEWS: Tuple[Tuple[str, float], ...] = (
    ('front', 0.0),
    ('three-quarter', 35.0),
    ('side', 90.0),
)


class Take:
    """One thing to watch a bot do, as what the rules would say about it.

    ``motion`` answers ``(velocity, facing, state)`` for a moment in the take:
    a world-space velocity in metres a second, a world-space direction the bot
    is looking, and whatever else the rules would be reporting -- firing,
    aiming, dead.  All three are what a real tick hands
    :func:`twig_bb.game.move_bodies`, which is what makes this a rehearsal
    rather than a mime.
    """

    def __init__(self, name: str, motion: Any, seconds: float = 1.6,
                 weapon: Optional[str] = None, note: str = '') -> None:
        self.name = name
        self.motion = motion
        self.seconds = float(seconds)
        #: The weapon for this take, or None for whatever the run carries.
        self.weapon = weapon
        self.note = note

    def at(self, when: float) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        velocity, facing, state = self.motion(when)
        return (np.asarray(velocity, dtype='d'),
                np.asarray(facing, dtype='d'), dict(state))


def _still(velocity=(0, 0, 0), facing=(0, 0, 1), **state):
    """A take that says the same thing at every moment of itself."""
    def motion(_when, velocity=velocity, facing=facing, state=state):
        return (velocity, facing, state)
    return motion


def _walking(speed, heading=(0, 0, -1), facing=(0, 0, 1), **state):
    """Moving along ``heading`` at ``speed`` while looking at ``facing``."""
    unit = np.asarray(heading, dtype='d')
    unit = unit / max(float(np.linalg.norm(unit)), 1e-9)
    return _still(velocity=unit * float(speed), facing=facing, **state)


def _jump(when):
    """Up, over and down: the arc a jump pad or a hop puts a body through."""
    rising = when < 0.45
    return ((0.0, 3.0 if rising else -3.0, 2.0), (0, 0, 1),
            {'grounded': when > 0.9, 'rising': rising})


def _dying(when):
    return ((0.0, 0.0, 0.0), (0, 0, 1), {'dead': when > 0.12})


def _firing(when):
    """Standing and shooting: the trigger comes down twice."""
    return ((0.0, 0.0, 0.0), (0, 0, 1),
            {'firing': (when % 0.7) < 0.18, 'aiming': True})


def _turning_to_shoot(when):
    """Somebody walks past and the bot turns to face them and fires."""
    angle = math.radians(-90.0 + 150.0 * min(1.0, when / 1.1))
    return ((0.0, 0.0, 0.0), (math.sin(angle), 0.0, math.cos(angle)),
            {'firing': when > 1.1, 'aiming': True})


#: What is worth watching, and why each one is here.
TAKES: Tuple[Take, ...] = (
    Take('idle', _still(), note='standing, breathing, weapon carried'),
    Take('walk-forward', _walking(2.4, heading=(0, 0, 1)), note='walking at the camera'),
    Take('run-forward', _walking(6.0, heading=(0, 0, 1)), note='running at the camera'),
    Take('walk-backward', _walking(2.4, heading=(0, 0, -1)),
         note='backing off while still facing the camera'),
    Take('strafe-left', _walking(3.2, heading=(-1, 0, 0)),
         note='sidestepping left, still facing the camera'),
    Take('strafe-right', _walking(3.2, heading=(1, 0, 0)),
         note='sidestepping right, still facing the camera'),
    Take('run-across', _walking(6.0, heading=(1, 0, 0.4)),
         note='running across the view, looking where it is going'),
    Take('turn-and-shoot', _turning_to_shoot, seconds=1.8,
         note='turning onto a target and firing'),
    Take('firing', _firing, seconds=2.0, note='standing and shooting'),
    Take('jump', _jump, seconds=1.4, note='the arc of a hop'),
    Take('dying', _dying, seconds=2.6, note='shot, and what is left on the floor'),
)


class Script:
    """The walkers the review pretends to have, one per bot.

    :func:`twig_bb.game.move_bodies` asks a walker how fast somebody is going
    and whether the floor is under them; this answers out of the take rather
    than out of a physics world, which is the whole of what isolating the bot
    means.
    """

    class Walker:
        def __init__(self) -> None:
            self.velocity = np.zeros(3)
            self.grounded = True
            self.position = np.zeros(3)

        def base(self) -> np.ndarray:
            return self.position

    def __init__(self, ids: Sequence[str]) -> None:
        self.walkers = {id: Script.Walker() for id in ids}

    def of(self, id: str) -> Any:
        return self.walkers.get(id)


class Review:
    """What to draw: one build, the takes to watch it in, and where they go."""

    #: Frames drawn and thrown away before the first is kept: the adaptive sky
    #: lighting converges over several, and a first frame lit differently from
    #: the rest cannot be compared with them.
    WARMUP = 8

    def __init__(self, out: str, build: str = characters.BUILDS[0],
                 weapon: str = 'rifle', takes: Sequence[Take] = TAKES,
                 views: Sequence[Tuple[str, float]] = VIEWS,
                 frames: int = 8, fps: float = 30.0) -> None:
        self.out = out
        self.build = build
        self.weapon = weapon
        self.takes = list(takes)
        self.views = list(views)
        #: How many moments of each take land on the sheet.
        self.frames = max(2, int(frames))
        #: How finely the state machine is stepped between them.  A clip
        #: chosen at eight moments a second would miss a landing; the machine
        #: is run at a game's rate and only *sampled* at the frames.
        self.fps = float(fps)

    def steps(self, take: Take) -> List[Tuple[float, bool]]:
        """``(dt, keep)`` for each tick of one take, in order."""
        ticks = max(self.frames, int(round(take.seconds * self.fps)))
        dt = take.seconds / ticks
        wanted = {int(round(index * (ticks - 1) / (self.frames - 1)))
                  for index in range(self.frames)}
        return [(dt, tick in wanted) for tick in range(ticks)]


def _floor(size: float = 12.0, grid: int = 12) -> Any:
    """A chequered floor, because half of what a review is looking for is feet.

    A body sinking into the ground, a foot that never lands and a death that
    ends underneath the world are all invisible over a void and obvious over a
    surface with a scale on it.
    """
    from OpenGLContext.scenegraph import basenodes
    step = size / grid
    tiles = []
    for row in range(grid):
        for column in range(grid):
            if (row + column) % 2:
                continue
            x = -size / 2 + column * step
            z = -size / 2 + row * step
            tiles.append(basenodes.Transform(
                translation=(x + step / 2, 0.0, z + step / 2),
                children=[basenodes.Shape(
                    appearance=basenodes.Appearance(
                        material=basenodes.Material(diffuseColor=(.20, .21, .24))),
                    geometry=basenodes.Box(size=(step, 0.02, step)))]))
    return basenodes.Transform(translation=(0.0, -0.01, 0.0), children=[
        basenodes.Shape(
            appearance=basenodes.Appearance(
                material=basenodes.Material(diffuseColor=(.13, .14, .16))),
            geometry=basenodes.Box(size=(size, 0.02, size))),
    ] + tiles)


class Stage:
    """One bot, its cast and the scene it is watched in.

    Built once for a whole run: a figure reloaded per take is most of the cost
    of the tool, and the state a take leaves behind is cleared rather than
    thrown away with the model (:meth:`ready`).
    """

    ID = 'bot0'

    def __init__(self, review: Review) -> None:
        from OpenGLContext.scenegraph import basenodes
        self.review = review
        self.table = weapontable.default_table()
        self.match = arenamod.Arena(weapons=self.table)
        self.match.add(self.ID, position=np.asarray(STAGE, dtype='d'),
                       bot=True, name='Bot')
        self.cast = characters.Cast([self.ID], builds=[review.build],
                                    armoury=characters.Armoury(self.table))
        self.figure = self.cast.of(self.ID)
        self.group, self.bodies = game.bot_bodies(self.match, cast=self.cast)
        self.script = Script([self.ID])
        #: What the view yaw is written on, so a take is watched from several
        #: sides without the bot's own facing being touched.
        self.turntable = basenodes.Transform(children=[self.group])
        self.scene = basenodes.sceneGraph(children=[
            self.turntable, _floor(),
            basenodes.PointLight(location=(2.0, 4.0, 4.0), intensity=14.0,
                                 radius=40.0),
            basenodes.PointLight(location=(-3.0, 2.5, -2.0), intensity=6.0,
                                 radius=40.0),
        ])

    def combatant(self) -> Any:
        """The bot, which this module put in the arena itself."""
        return self.match.combatant(self.ID)

    def ready(self, take: Take) -> None:
        """Put the bot back to standing and alive, before a take starts."""
        one = self.combatant()
        one.player.health = one.player.max_health
        one.dead_for = None
        one.position = np.asarray(STAGE, dtype='d')
        held = take.weapon or self.review.weapon
        one.player.give(held)
        one.player.selected = held
        one.facing = np.zeros(3)
        one.firing = 0.0
        walker = self.script.of(self.ID)
        walker.velocity = np.zeros(3)
        walker.grounded = True
        walker.position = np.asarray(STAGE, dtype='d')
        if self.figure is not None:
            self.figure.reset()

    def tick(self, take: Take, when: float, dt: float) -> None:
        """Advance the rules and the drawing by one tick of ``take``."""
        velocity, facing, state = take.at(when)
        one = self.combatant()
        walker = self.script.of(self.ID)
        walker.velocity = velocity
        walker.grounded = bool(state.get('grounded', True))
        # A treadmill on the flat: the rules are told the body is travelling
        # and it is not moved, because what a review is looking at is the
        # cycle and a figure that walks out of frame cannot be looked at.
        # **Height is not the same question.** Whether a jump leaves the
        # ground at all is one of the things being watched for, so the
        # vertical does move, and the floor is there to measure it against.
        rise = float(velocity[1]) * dt
        if rise:
            one.position = np.asarray(one.position, dtype='d') + (0.0, rise, 0.0)
            one.position[1] = max(0.0, float(one.position[1]))
        walker.position = one.position
        one.facing = facing
        if state.get('dead'):
            one.player.health = 0
        if state.get('firing'):
            one.firing = game.SHOT_SHOWN
        game.move_bodies(self.match, self.bodies, cast=self.cast,
                         walking=self.script, dt=dt)


class ReviewContext:
    """Draws every take from every view and lays the frames out.

    One GL context and one figure for the whole run. The state machine is
    stepped at a game's rate and only *sampled* at the frames that land on the
    sheet, because a machine driven at eight ticks a second would miss a
    landing, a shot and half of everything else it is being watched for.
    """

    def __init__(self, review: Review) -> None:
        self.review = review
        self.stage: Any = None
        self.context: Any = None

    def build(self) -> None:
        from OpenGLContext import testingcontext
        base: Any = testingcontext.getInteractive()
        self.stage = Stage(self.review)
        scene = self.stage.scene
        camera = CAMERA

        class _Context(base):
            def OnInit(self) -> None:
                self.sg = scene
                self.getViewPlatform().setPosition(camera)

        try:
            self.context = _Context()
        except Exception as error:                      # pragma: no cover - GL
            raise SystemExit('no usable GL context: %r' % (error,)) from error
        self.context.deferRedraw = True
        try:
            import glfw
            glfw.swap_interval(0)
        except Exception:                               # pragma: no cover
            pass

    def frame(self) -> Any:
        """Draw once and hand back what landed in the framebuffer."""
        from OpenGLContext.capture import read_back_buffer
        try:
            import glfw
            glfw.poll_events()
        except Exception:                               # pragma: no cover
            pass
        # Twice: `OnDraw` swaps, so a single draw leaves the frame just made
        # in the *front* buffer and the one before it in the back, and every
        # capture would be one tick behind what it is labelled.
        self.context.OnDraw(force=1)
        self.context.OnDraw(force=1)
        return read_back_buffer(0)[0]

    def run(self) -> List[str]:
        """Draw every take and write the sheets; returns what it wrote."""
        from OpenGLContext import contactsheet
        review, stage = self.review, self.stage
        os.makedirs(review.out, exist_ok=True)
        for _ in range(review.WARMUP):
            self.frame()
        written = []
        for take in review.takes:
            rows = []
            for name, yaw in review.views:
                stage.turntable.rotation = (0.0, 1.0, 0.0, math.radians(yaw))
                stage.ready(take)
                frames, when = [], 0.0
                for dt, keep in review.steps(take):
                    stage.tick(take, when, dt)
                    when += dt
                    if keep:
                        frames.append(self.frame())
                rows.append((name, frames))
            path = os.path.join(review.out, '%s-%s.png' % (review.build, take.name))
            columns = ['%.2fs' % (index * take.seconds / (review.frames - 1))
                       for index in range(review.frames)]
            contactsheet.tile(path, '%s -- %s%s' % (
                review.build, take.name,
                ' (%s)' % take.note if take.note else ''), rows, columns)
            written.append(path)
            sys.stdout.write('wrote %s\n' % path)
        page = contactsheet.index(
            review.out, title='%s -- bots, out of the game' % review.build,
            caption='One sheet per take: a row for each view, a column for each '
                    'moment. Every frame is drawn through the same '
                    '`move_bodies` the match calls, so what is here is what a '
                    'player sees.')
        sys.stdout.write('wrote %s\n' % page)
        return written


def build_parser(prog: str = 'twig-bb-bots') -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description=__doc__.splitlines()[0])
    parser.add_argument('--out', default='bot-sheets', metavar='DIR',
                        help='where the sheets go (default: bot-sheets)')
    parser.add_argument('--build', default=characters.BUILDS[0],
                        help='which figure to watch (default: %(default)s)')
    parser.add_argument('--weapon', default='rifle',
                        help='what it carries (default: %(default)s)')
    parser.add_argument('--takes', default=None, metavar='A,B',
                        help='only these takes, comma separated')
    parser.add_argument('--frames', type=int, default=8, metavar='N',
                        help='moments of each take on the sheet (default: 8)')
    parser.add_argument('--seconds', type=float, default=None, metavar='S',
                        help='override how long every take runs for')
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    options = build_parser().parse_args(argv)
    takes = list(TAKES)
    if options.takes:
        wanted = options.takes.split(',')
        takes = [take for take in TAKES if take.name in wanted]
        if not takes:
            raise SystemExit('--takes matched none of: %s'
                             % ', '.join(take.name for take in TAKES))
    if options.seconds:
        takes = [Take(take.name, take.motion, options.seconds, take.weapon,
                      take.note) for take in takes]
    review = Review(options.out, build=options.build, weapon=options.weapon,
                    takes=takes, frames=options.frames)
    drawing = ReviewContext(review)
    drawing.build()
    drawing.run()


if __name__ == '__main__':
    main()
