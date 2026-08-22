"""The half of §7 that only a real driver can settle: does any of it draw?

Everything about *what* a fight does is arithmetic and is tested without a
window.  What is left is what a player would notice were missing and no
headless test can see: a rocket appears and moves, an explosion draws, and an
impact effect lands where the shot did.  (The damage indicator is the fourth,
and is over in OpenGLContext's own HUD tests with the widget it belongs to.)

Deliberately shallow.  These are smoke tests: they assert that pixels changed
where pixels should have changed, and nothing about how anything *looks* — a
reference image of a particle system is a reference image of a random number
generator.
"""

from __future__ import annotations

import os

os.environ['OPENGLCONTEXT_PROFILE'] = 'core'
os.environ['OPENGLCONTEXT_BACKEND'] = 'glfw'
os.environ['OPENGLCONTEXT_DISABLE_FPS_DISPLAY'] = '1'
os.environ['OPENGLCONTEXT_SHADOWS'] = '0'
# **The renderer the game uses.**  A smoke test that drew through a different
# pass from the viewer would be a test that passes while the game shows
# nothing, which is exactly what happened: the effects reached the framebuffer
# under the default pass and were dropped under this one.
os.environ['OPENGLCONTEXT_RENDERER'] = 'pbr'

import numpy as np                                              # noqa: E402
import pytest                                                   # noqa: E402

glfw = pytest.importorskip('glfw')

from twig_bb import arena, effects, game, projectiles, weapons  # noqa: E402

pytestmark = [pytest.mark.gl]

#: How far in front of the camera the things under test are put, in metres.
#: The view platform is left exactly where it starts: a test that had to place
#: a camera as well would fail for two reasons and report only one of them.
AHEAD = -4.0

#: How far from the scene origin the "in a real level" cases are put.  Far
#: enough that a bound around the emitter's own node cannot reach the camera,
#: which is the whole of what those cases are about.
FAR_FROM_ORIGIN = 400.0

#: Frames drawn before the framebuffer is read.  Several, because the first
#: pass through a shader path compiles it, and a picture taken during that is
#: a picture of a program that was not ready.
FRAMES = 12


def match():
    made = arena.Arena(weapons=weapons.default_table())
    made.add(game.PLAYER_ID, position=(0.0, 0.0, 0.0), name='You')
    return made


@pytest.fixture
def render():
    """Factory: put children in a scene, draw it, and hand back the pixels.

    One window for the whole test and drawn again on each call, so a test can
    change what is in the scene and compare two frames — which is how "it
    moved" is asserted without a reference image.
    """
    from OpenGLContext import testingcontext
    from OpenGLContext.scenegraph import basenodes

    Base = testingcontext.getInteractive()
    made: dict = {}

    def build(children, camera):
        scene = basenodes.sceneGraph(children=list(children) + [
            basenodes.PointLight(location=(0.0, 3.0, 6.0), intensity=8.0,
                                 radius=60.0),
        ])

        class _Ctx(Base):
            def OnInit(self):
                self.sg = scene
                if camera is not None:
                    self.getViewPlatform().setPosition(camera)

        try:
            context = _Ctx()
        except Exception as error:      # pragma: no cover - a broken GL stack
            pytest.skip('no usable GL context: %r' % (error,))
        context.deferRedraw = True
        try:
            # A hidden window is never presented, so a swap that waits for a
            # vertical blank waits for one that never comes.
            glfw.swap_interval(0)
        except Exception:               # pragma: no cover - an older glfw
            pass
        made['context'] = context
        return context

    def run(children=None, frames=FRAMES, camera=None):
        context = made.get('context')
        if context is None:
            context = build(children or [], camera)
        for _frame in range(frames):
            glfw.poll_events()
            context.OnDraw(force=1)
        return _pixels(context)

    yield run
    # The pass that last rendered is a module global and outlives the window
    # it belongs to; left set, it hands the next test a shader program whose
    # GL context is gone.
    import gc

    from OpenGLContext.passes import renderpass

    renderpass.FLAT = None
    context = made.pop('context', None)
    window = getattr(context, 'window', None)
    del context
    gc.collect()                        # GL finalizers, while this window is current
    if window is not None:
        glfw.destroy_window(window)


def _pixels(context):
    """The framebuffer as (h, w, 3) ints."""
    from OpenGL.GL import GL_RGB, GL_UNSIGNED_BYTE, glReadPixels
    width, height = context.getViewPort()
    raw = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)
    return np.frombuffer(bytes(raw), dtype=np.uint8).reshape(
        height, width, 3).astype(int)


def _lit(pixels, threshold=12):
    """How many pixels are brighter than the near-black background."""
    return int((pixels.max(axis=2) > threshold).sum())


def _flight(at=(0.0, 0.0, AHEAD)):
    table = projectiles.default_table()
    made = projectiles.Projectiles(table, capacity=4)
    made.launch(table.by_key(projectiles.ROCKET), origin=at,
                direction=(1, 0, 0), owner=game.PLAYER_ID)
    return made


class TestARocket:
    """It has to appear, and it has to be somewhere else a moment later."""

    def test_a_rocket_in_flight_is_drawn(self, render):
        flight = _flight()
        group, bodies = game.projectile_bodies(flight.table)
        empty = render([group])
        game.move_projectiles(flight, bodies)
        assert _lit(render()) > _lit(empty)

    def test_it_is_drawn_somewhere_else_when_it_moves(self, render):
        flight = _flight(at=(-1.5, 0.0, AHEAD))
        group, bodies = game.projectile_bodies(flight.table)
        game.move_projectiles(flight, bodies)
        before = render([group])
        flight.position[0] = (1.5, 0.0, AHEAD)
        game.move_projectiles(flight, bodies)
        assert not np.array_equal(before, render())

    def test_nothing_in_the_air_draws_nothing(self, render):
        """The bodies are parked out of sight rather than left where they were."""
        flight = _flight()
        group, bodies = game.projectile_bodies(flight.table)
        game.move_projectiles(flight, bodies)
        lit = _lit(render([group]))
        assert lit > 0
        flight.clear()
        game.move_projectiles(flight, bodies)
        assert _lit(render()) == 0


class TestTheEffects:
    """Particles have to reach the framebuffer, whatever the arithmetic says."""

    def test_an_explosion_draws(self, render):
        found = match()
        shown = effects.Effects(found)
        empty = render([shown.group])
        found.detonated(point=(0.0, 0.0, AHEAD), kind=projectiles.ROCKET,
                        by=game.PLAYER_ID)
        shown.show(found.drain())
        assert _lit(render()) > _lit(empty)

    def test_an_impact_effect_appears_where_it_landed(self, render):
        """On the correct side of the screen, which is the part that matters."""
        found = match()
        shown = effects.Effects(found)
        render([shown.group])
        found.impact(point=(1.5, 0.0, AHEAD), normal=(0, 1, 0),
                     surface='stone')
        shown.show(found.drain())
        pixels = render()
        middle = pixels.shape[1] // 2
        assert _lit(pixels[:, middle:]) > _lit(pixels[:, :middle])

    def test_a_burst_far_from_the_emitter_node_still_draws(self, render):
        """The level case, and the one that was broken in the real game.

        The emitters never move: the styling stays on one node at the scene
        origin and the *place* arrives per burst.  A player is almost never
        standing at the scene origin, so if anything about the draw path is
        keyed to where the *node* is rather than where its particles are, every
        effect is born, never stepped and never drawn — which reads, from
        inside the game, as a weapon that does nothing at all.

        So the camera stands four hundred metres out, as it would in a level,
        and the burst happens in front of *it* while the node stays behind at
        the origin.
        """
        found = match()
        shown = effects.Effects(found)
        empty = render([shown.group],
                       camera=(FAR_FROM_ORIGIN, 0.0, 0.0))
        found.impact(point=(FAR_FROM_ORIGIN, 0.0, AHEAD), normal=(0, 1, 0),
                     surface='stone')
        shown.show(found.drain())
        assert _lit(render()) > _lit(empty)

    def test_the_intensity_setting_reaches_the_pixels(self, render):
        """Off is off all the way to the framebuffer, not merely in the rules."""
        found = match()
        shown = effects.Effects(found, intensity=effects.OFF)
        empty = render([shown.group])
        found.detonated(point=(0.0, 0.0, AHEAD), kind=projectiles.ROCKET,
                        by=game.PLAYER_ID)
        shown.show(found.drain())
        assert _lit(render()) == _lit(empty)
