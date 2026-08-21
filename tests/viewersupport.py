"""What the viewer's tests hand it: a map, a platform, and a context with no window.

Every test of the viewer needs some of the same made-up world -- a small `IBSP`
file on disk, a platform standing in it, and enough of a context for the input
path to run without a GL surface. None of that is what any of the tests is
about, so it is made up here and asked for by name.

Importing this reaches :mod:`twig_bb.viewer`, which needs a GL backend to build
its context classes, so the modules that use it are the ones
``tests/conftest.py`` declines to collect where the viewer will not import.
"""

from __future__ import annotations

from OpenGLContext.move import viewplatform
from OpenGLContext.move.viewplatformmixin import ViewPlatformMixin

import bspbuilder
from twig_bb import collision, maploader, viewer


def synthetic_map(tmp_path, lumps=None, name='ctf-test.bsp'):
    maps = tmp_path / 'maps'
    maps.mkdir(parents=True, exist_ok=True)
    path = maps / name
    path.write_bytes(bspbuilder.build(46, lumps or bspbuilder.v46_quad(size=512.0)))
    return str(path)


def walking_platform(tmp_path):
    from OpenGLContext.move.physicsplatform import PhysicsViewPlatform
    loaded = maploader.load(synthetic_map(tmp_path))
    return PhysicsViewPlatform(collision.from_map(loaded).world,
                               viewer.character_capabilities(), position=(0, 1, 0))


class NullInput:
    """Nobody touching anything: the input a mode is driven with by default."""

    def held(self, *names):
        return False

    def pressed(self, *names):
        return False

    def modifiers(self, name):
        return (0, 0, 0)

    def mouse_delta(self):
        return (0.0, 0.0)


class LookInput:
    """Ctrl held with an arrow: what the look bindings are declared against."""

    def __init__(self, key):
        self.key = key

    def held(self, *names):
        return self.key in names

    def pressed(self, *names):
        return False

    def modifiers(self, name):
        return (0, 1, 0) if name == self.key else (0, 0, 0)

    def mouse_delta(self):
        return (0.0, 0.0)


def walk_mode():
    return [mode for mode in viewer.movement_modes() if mode.name == 'walk'][0]


def look_once(nav, key, dt=0.1):
    """Drive the walk mode for one frame with a look key held."""
    walk_mode().update(dt, LookInput(key), nav)


class NavStub:
    def __init__(self):
        self.flying = False
        self.swimming = False
        self.buoyancy = None

    def set_fly(self, flying):
        self.flying = flying

    def set_swim(self, swimming, buoyancy=0.9):
        self.swimming = swimming
        self.buoyancy = buoyancy


class HeadlessContext(ViewPlatformMixin):
    """The context's input path with no window: dispatch, sampler, modes."""

    drawing = False
    #: As on the real context before a level is walked in; a shot resolved
    #: without one still lands, it just cannot name the surface it met.
    _collision = None
    #: Nothing in the air.  A hitscan weapon needs no batch at all.
    flight = None
    #: What the game tells a session recording; the real context's own default
    #: until :meth:`~twig_bb.viewer.TwigContext.OnInit` binds one to a window.
    #: Nothing is recording here, so every mark made below goes nowhere.
    marks = viewer.TwigContext.marks

    def __init__(self, nav):
        self.contextDefinition = viewer.context_definition()
        #: The platform the renderer draws from, which on the real context is
        #: **not** the navigator: it is driven by the navigator each frame and
        #: its orientation does not carry the look.  Kept distinct here so a
        #: test can tell the two apart, which is the whole of what the aim
        #: tests are about.
        self.platform = viewplatform.ViewPlatform()
        self._nav = nav

    def getNavigationPlatform(self):
        return self._nav

    def getViewPort(self):
        return (800, 600)

    physicsWorld = viewer.TwigContext.physicsWorld

    def getEventManager(self, kind):
        return None

    def ProcessEvent(self, event):
        return None

    def triggerRedraw(self, value=1):
        pass


class KeyEvent:
    type = 'keyboard'

    def __init__(self, name, state):
        self.name, self.state = name, state

    def getModifiers(self):
        return (0, 0, 0)


class BindingRecorder:
    """Records what a context would bind, without needing a window."""

    #: The real context's own default marker, so ``__getattr__``'s stand-in
    #: handler does not answer for it.  Nothing is recording here, so what the
    #: game marks goes nowhere.
    marks = viewer.TwigContext.marks

    def __init__(self):
        self.bindings = []

    def addEventHandler(self, kind, **named):
        self.bindings.append((kind, named.get('name'), named.get('state')))

    def __getattr__(self, name):
        return lambda event=None: None      # stands in for the handlers
