#! /usr/bin/env python
"""A room, a weapon in your hands, and the whole HUD over it.

``twig-bb-hud`` -- the stand-in for the game twig-bb is on the way to being.
It exists because [§3](../PROJECT-PLAN.md) can be finished long before
[§5](../PROJECT-PLAN.md)'s characters and [§7](../PROJECT-PLAN.md)'s weapons
are, and a HUD that has only ever been asserted about in tests is a HUD nobody
has actually looked at.  So this draws it: over a real frame, with a real
first-person model in it, driven by the same modules the viewer uses.

Keys::

    1 - 5               choose a weapon (all but the first have to be
                        picked up: p gives you the next one)
    [ ] / mouse wheel   previous / next weapon held
    left mouse / ctrl   fire -- ammunition goes down, the reticule opens
    p                   pick the next weapon up, so the bar fills in
    h                   take damage, from a different side each time: the
                        meter flashes and reads low, and the screen edge the
                        hit came from washes red
    j / k               heal / take armour
    Alt + f             the developer overlay
    F6 / F10            key bindings / rendering settings
    F2                  screenshot
    w a s d, mouse      walk and look

The weapons are **this project's own**, modelled for it and credited in
[assets/weapons/CREDITS.md](assets/weapons/CREDITS.md).  Each is named by the
weapon table as data, so re-modelling one is a table edit; where it sits in the
hand is data too (`--weapon <key>` is how those numbers get dialled in).

**The weapon is held by nesting, not by arithmetic.**  One transform carries the
camera's pose and another carries the weapon's offset inside it, so "in the
player's hands" is expressed by the scenegraph rather than by multiplying
matrices in the frame loop -- and both halves can be checked without a window.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
from typing import Any, List, Sequence, Tuple

os.environ.setdefault('OPENGLCONTEXT_PROFILE', 'core')
os.environ.setdefault('OPENGLCONTEXT_BACKEND', 'glfw')
os.environ.setdefault('OPENGLCONTEXT_RENDERER', 'pbr')

from OpenGLContext import testingcontext                        # noqa: E402
from OpenGLContext.capture import SettleCapture                 # noqa: E402
from OpenGLContext.contextdefinition import ContextDefinition   # noqa: E402
from OpenGLContext.scenegraph.appearance import Appearance      # noqa: E402
from OpenGLContext.scenegraph.basenodes import (                # noqa: E402
    Box, Material, Shape, Transform,
)
from OpenGLContext.scenegraph.light import (                     # noqa: E402
    DirectionalLight, PointLight,
)
from OpenGLContext.scenegraph.scenegraph import SceneGraph      # noqa: E402
from OpenGLContext.ui import bindings, settings                 # noqa: E402
from OpenGLContext.ui.overlay import OverlayMixin               # noqa: E402

from . import controls, weapons as weapontable                  # noqa: E402
from . import debug as twigdebug                              # noqa: E402
from .firstperson import WeaponHand, aim_at_camera               # noqa: E402
from .hud import GameHUD, now as hudclock                       # noqa: E402
from .player import PlayerState                                 # noqa: E402

log = logging.getLogger(__name__)

BaseContext: Any = testingcontext.getInteractive()

#: The room: half-width in metres, and how tall.  Small enough to walk across in
#: a few seconds, because what is being looked at is the HUD.
ROOM = 8.0
ROOM_HEIGHT = 3.5

#: Radians the demo's hits walk round the player between one `h` and the next.
#: Not a whole turn divided evenly: a step that landed on the same four edges
#: for ever would never show the wash sliding between two of them, which is the
#: behaviour worth looking at.
HURT_STEP = 2.0 * math.pi / 7.0

#: Where the eye starts, and how close a thing may be and still be drawn.  The
#: near plane matters here: a weapon held at arm's length is *inside* the
#: default one, and would be clipped away by the very frustum that is fine for
#: a map.
EYE_HEIGHT = 1.7
NEAR_PLANE = 0.02
FAR_PLANE = 200.0


# -- the scene -------------------------------------------------------------
def build_room() -> List[Any]:
    """A floor, four walls and a few blocks, so the HUD has a world behind it.

    Blocks rather than an empty room: a crosshair over a flat wall says nothing
    about whether it is where the player is looking, and a health bar over one
    colour is not a fair test of whether it can be read.
    """
    grey = Appearance(material=Material(diffuseColor=(0.20, 0.21, 0.24),
                                        shininess=0.15))
    warm = Appearance(material=Material(diffuseColor=(0.55, 0.36, 0.24),
                                        shininess=0.2))
    cool = Appearance(material=Material(diffuseColor=(0.24, 0.42, 0.55),
                                        shininess=0.4))
    children: List[Any] = [
        Transform(translation=(0, -0.1, 0),
                  children=[Shape(geometry=Box(size=(ROOM * 2, 0.2, ROOM * 2)),
                                  appearance=grey)]),
    ]
    children.append(Transform(
        translation=(0, ROOM_HEIGHT, 0),
        children=[Shape(geometry=Box(size=(ROOM * 2, 0.2, ROOM * 2)),
                        appearance=grey)]))
    for x, z in ((ROOM, 0), (-ROOM, 0), (0, ROOM), (0, -ROOM)):
        size = ((0.2, ROOM_HEIGHT, ROOM * 2) if x else (ROOM * 2, ROOM_HEIGHT, 0.2))
        children.append(Transform(
            translation=(x, ROOM_HEIGHT / 2.0, z),
            children=[Shape(geometry=Box(size=size), appearance=grey)]))
    for x, z, height, look in ((-3.0, -4.0, 1.2, warm), (2.5, -5.5, 2.0, cool),
                               (4.0, 1.5, 0.8, warm), (-4.5, 2.5, 1.6, cool)):
        children.append(Transform(
            translation=(x, height / 2.0, z),
            children=[Shape(geometry=Box(size=(1.0, height, 1.0)),
                            appearance=look)]))
    children.extend([
        DirectionalLight(direction=(-0.4, -1.0, -0.3), intensity=0.6,
                         color=(1.0, 0.97, 0.92)),
        PointLight(location=(0, ROOM_HEIGHT - 0.6, 0), intensity=5.0,
                   color=(0.95, 0.93, 0.85), radius=14.0),
        PointLight(location=(-4.0, 1.8, -4.0), intensity=4.0,
                   color=(0.6, 0.75, 1.0), radius=10.0),
    ])
    return children


# -- the window ------------------------------------------------------------
class HUDSampleContext(OverlayMixin, BaseContext):      # pragma: no cover - GL
    """The demo window: a room, a weapon in hand, and the HUD over both."""

    config: Any = None
    platform: Any
    addEventHandler: Any
    triggerRedraw: Any
    sg: Any
    #: Which way the next demo hit comes from; see :data:`HURT_STEP`.
    _bearing: float = 0.0

    def OnInit(self) -> None:
        # This demo asks for a frame every idle -- the reticule closes and
        # messages fade on their own -- and a vsynced swap blocks on a
        # compositor frame callback that a window nobody is watching never
        # gets, so a capture would draw one frame and then wait forever.
        from .viewer import disable_vsync
        disable_vsync()
        self.weapons = weapontable.default_table()
        # Carrying everything: this demo is *for* looking at the weapons, and
        # a number key that refuses because nothing has handed you the weapon
        # reads as a broken key.
        self.player = PlayerState.carrying(self.weapons)
        wanted = getattr(self.config, 'weapon', None)
        if wanted:
            self.player.select(wanted)
        self.weaponBindings = controls.WeaponBindings()
        self.hand = WeaponHand(self.weapons)
        self.hand.select(self.weapons.by_key(self.player.selected))
        self.camera = Transform(children=[self.hand.group])
        self.sg = SceneGraph(children=build_room() + [self.camera])
        self.platform.setFrustum(near=NEAR_PLANE, far=FAR_PLANE)
        self.platform.setPosition((0.0, EYE_HEIGHT, 5.0))

        # Before anything asks for a frame: adding a HUD layer triggers a
        # redraw, and a frame drawn before the capture exists has nothing to
        # report itself to.
        self._capture = None
        if self.config is not None and self.config.capture:
            self._capture = SettleCapture(self.config.capture,
                                          delay=self.config.capture_delay,
                                          min_frames=self.config.frames)

        self.hud = GameHUD(self.weapons)
        self.addHUDLayer(self.hud)
        twigdebug.install(self)
        self.debugOverlay.register('Demo', self._demoRows, order=45)
        if self.config is not None and self.config.debug_overlay:
            self.debugOverlay.visible = True
        self._handlers: List[Any] = []
        self._bindKeys()
        self.hud.post('WELCOME -- the mouse fires, p picks up, 1-5 chooses')
        self._report()

    # -- input ------------------------------------------------------------
    def _bindKeys(self) -> None:
        for binding in self.weaponBindings.bindings:
            for key in binding.keys:
                for state in (1, 0):
                    self.addEventHandler('keyboard', name=str(key),
                                         state=state, function=self._wake)
        for name, method in (('p', self._pickup), ('h', self._hurt),
                             ('j', self._heal), ('k', self._armour)):
            self.addEventHandler('keypress', name=name, function=method)
        self.addEventHandler('keyboard', name='<F6>', state=1,
                             function=self._bindingsScreen)
        self.addEventHandler('keyboard', name='<F10>', state=1,
                             function=self._settingsScreen)
        from OpenGLContext.events.mouseevents import WHEEL_DOWN, WHEEL_UP
        for button, step in ((WHEEL_UP, 1), (WHEEL_DOWN, -1)):
            self.addEventHandler('mousebutton', button=button, state=1,
                                 function=self._wheel(step))

    def _wake(self, event: Any = None) -> None:
        self.triggerRedraw(1)

    def _wheel(self, step: int) -> Any:
        def turn(event: Any = None) -> None:
            self._run([controls.NEXT_WEAPON if step > 0
                       else controls.PREVIOUS_WEAPON], firing=False)
        self._handlers.append(turn)     # the event system holds callbacks weakly
        return turn

    def _pickup(self, event: Any = None) -> None:
        """Give the player the next weapon they do not have."""
        for weapon in self.weapons.weapons:
            key = str(weapon.key)
            if self.player.give(key):
                self.player.give_ammo(str(weapon.ammoType), 40)
                self.hud.post('PICKED UP A %s' % (str(weapon.title),))
                self.triggerRedraw(1)
                return
        self.hud.post('YOU HAVE EVERYTHING')
        self.triggerRedraw(1)

    def _hurt(self, event: Any = None) -> None:
        """Take a hit from somewhere new each time.

        From a *direction*, because the directional wash is the part of being
        shot that a player acts on and a demo that always hit from the front
        would never show it moving.
        """
        taken = self.player.take_damage(25)
        self._bearing = (self._bearing + HURT_STEP) % (2.0 * math.pi)
        self.hud.damage.hurt(bearing=self._bearing - math.pi,
                             intensity=taken / 34.0, now=hudclock())
        if not self.player.alive:
            self.hud.died('Killed by the demo', respawn_in=0.0)
        self.triggerRedraw(1)

    def _heal(self, event: Any = None) -> None:
        was_dead = not self.player.alive
        self.player.heal(25)
        if was_dead and self.player.alive:
            self.hud.revived()
        self.triggerRedraw(1)

    def _armour(self, event: Any = None) -> None:
        self.player.give_armour(25)
        self.triggerRedraw(1)

    def _bindingsScreen(self, event: Any = None) -> None:
        bindings.open_bindings(self, navigation=controls.Controls(
            self.getNavigation(), self.weaponBindings))

    def _settingsScreen(self, event: Any = None) -> None:
        settings.open_settings(self)

    def _run(self, commands: Sequence[str], firing: bool) -> None:
        for event in controls.apply_commands(commands, firing, self.player,
                                             self.weapons, hudclock()):
            if event.text:
                self.hud.post(event.text)
        self.triggerRedraw(1)

    # -- the frame --------------------------------------------------------
    def OnIdle(self, *args: Any) -> int:
        state = self.getInputState()
        commands = self.weaponBindings.triggered(state)
        firing = self.weaponBindings.firing(state)
        if commands or firing:
            self._run(commands, firing)
        # The reticule closes and messages fade on their own, so the demo asks
        # for frames continuously rather than only when something is pressed.
        self.triggerRedraw(1)
        return 1

    def placeViewAttachments(self, pass_: Any = None) -> None:
        """Pin the weapon to the view for the frame about to be drawn.

        The render pass calls this once the camera is settled and before any
        geometry is gathered.  Posed anywhere earlier the weapon is written
        from the previous frame's camera and swims about the screen as the
        player moves.
        """
        if self.hand.select(self.weapons.by_key(self.player.selected)):
            self.triggerRedraw(1)
        aim_at_camera(self.camera, self.getViewPlatform())

    def renderShaderOverlay(self, pass_: Any) -> None:
        platform = self.getViewPlatform()
        self.hud.update(self.player, now=hudclock(),
                        viewport=self.getViewPort(),
                        field_of_view=math.radians(
                            float(getattr(platform, 'frustum', (90,))[0])))
        super(HUDSampleContext, self).renderShaderOverlay(pass_)

    def presentFrame(self) -> Any:
        """Present the frame, and take the capture from it before the swap."""
        if self._capture is not None and self._capture.tick():
            result = super(HUDSampleContext, self).presentFrame()
            self.setCurrent()
            sys.stdout.write('captured %s\n' % (self.config.capture,))
            sys.stdout.flush()
            os._exit(0)
            return result
        return super(HUDSampleContext, self).presentFrame()

    # -- reporting --------------------------------------------------------
    def _demoRows(self) -> List[Tuple[str, Any]]:
        weapon = self.weapons.by_key(self.player.selected)
        return [
            ('model', str(weapon.model) if weapon is not None else '-'),
            ('held', len(self.player.weapons)),
            ('spread', self.player.spread_fraction(hudclock())),
        ]

    def _report(self) -> None:
        sys.stdout.write(__doc__.split('Keys::')[1].split('The weapon is')[0])
        sys.stdout.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='the twig-bb HUD, over a room, with a weapon in hand')
    parser.add_argument('--capture', metavar='PATH', default=None,
                        help='render, save a PNG and exit')
    parser.add_argument('--capture-delay', type=float, default=0.5,
                        metavar='SECONDS',
                        help='settle time before a capture (default 0.5)')
    parser.add_argument('--frames', type=int, default=10, metavar='N',
                        help='frames to draw before a capture (default 10)')
    parser.add_argument('--weapon', metavar='KEY', default=None,
                        help='start holding this weapon (see the table in '
                             'twig_bb/weapons.py); handy for a screenshot '
                             'of each')
    parser.add_argument('--debug-overlay', action='store_true',
                        help='start with the developer overlay up, and keep '
                             'it up during a capture')
    parser.add_argument('--verbose', action='store_true',
                        help='log the details')
    return parser


def main() -> int:                              # pragma: no cover - needs a window
    options = build_parser().parse_args()
    logging.basicConfig(level=logging.INFO if options.verbose
                        else logging.WARNING)
    if options.capture:
        os.environ['OPENGLCONTEXT_DISABLE_FPS_DISPLAY'] = '1'
    HUDSampleContext.config = options
    definition = ContextDefinition(title='twig-bb HUD sample', size=(1280, 720),
                                   vsync=False)
    HUDSampleContext.ContextMainLoop(definition=definition)
    return 0


if __name__ == '__main__':                      # pragma: no cover
    sys.exit(main())
