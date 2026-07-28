#! /usr/bin/env python
"""Walk through a Quake 2 / Quake 3 map.

Usage::

    twitch-viewer arena/maps/ctf-curvy.bsp
    twitch-viewer some-map.pk3
    twitch-viewer https://example.com/some-map.pk3
    twitch-viewer openarena:oa_dm1          # from a content pack
    twitch-viewer --list-packs              # what can be downloaded

Keys::

    w a s d / arrows        walk (strafe with a/d)
    q / e                   turn left / right
    ctrl + up / down        look up / down
    shift                   run, while held
    space                   jump; rise, while flying
    c                       sink, while flying
    f                       fly (noclip) on/off
    m                       cycle movement mode: walk, fly, mouse-look
    g                       walk (physics) / free-fly camera
    1 2 3                   choose a weapon; [ ] and the wheel step through them
    ctrl                    fire (held)
    alt + f                 the developer overlay
    F2                      save a screenshot
    F6 / F10                key bindings / rendering settings

The keys are not fixed here: each way of moving is a declared ``MovementMode``
node carrying its own speeds and bindings (see :func:`movement_modes`), which is
what lets a settings screen present them and a game retune them.

The map lights itself: both families bake their lighting into lightmaps, which
the PBR pass reads linearly.  ``--lightmap`` scales that exposure; a map bakes
absolute radiosity and every engine scales it at render time, so the default is
the viewer's own choice rather than a property of the file.

Walking is the character controller from ``OpenGLContext.move``, and jump pads
drive its ``apply_impulse`` from the physics trigger system — see
:mod:`twitchoglc.jumppads`.  Water, slime and lava are volumes rather than
floors, so the avatar falls in and swims: see :mod:`twitchoglc.liquids`.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time
from typing import Any, Callable, List, Optional, Tuple

os.environ.setdefault('OPENGLCONTEXT_PROFILE', 'core')
os.environ.setdefault('OPENGLCONTEXT_BACKEND', 'glfw')
os.environ.setdefault('OPENGLCONTEXT_RENDERER', 'pbr')
# A map's own baked lighting is the point; a full-strength analytic sky washes
# it out, so the environment probe is dimmed rather than switched off (metals
# still need something to reflect).
os.environ.setdefault('OPENGLCONTEXT_IBL_INTENSITY', '0.15')

import numpy as np                                              # noqa: E402

from OpenGLContext import testingcontext                        # noqa: E402
from OpenGLContext.capture import SettleCapture                 # noqa: E402
from OpenGLContext.contextdefinition import ContextDefinition   # noqa: E402
from OpenGLContext.move import modes as movemodes                # noqa: E402
from OpenGLContext.move.physicsplatform import PhysicsViewPlatform  # noqa: E402
from OpenGLContext.scenegraph.background import Background      # noqa: E402
from OpenGLContext.scenegraph.light import (                     # noqa: E402
    DirectionalLight, PointLight,
)
from OpenGLContext.scenegraph.scenegraph import SceneGraph      # noqa: E402
from omi_physics import model                                   # noqa: E402
from omi_physics.character import CharacterCapabilities         # noqa: E402
from omi_physics.world import PhysicsWorld                      # noqa: E402

from OpenGLContext.events.mouseevents import WHEEL_DOWN, WHEEL_UP  # noqa: E402
from OpenGLContext.ui import bindings, dialogs, settings         # noqa: E402
from OpenGLContext.ui.overlay import OverlayMixin                # noqa: E402
from OpenGLContext.ui.panel import Panel                         # noqa: E402

from . import controls, download, jumppads, maploader           # noqa: E402
from . import debug as twitchdebug                              # noqa: E402
from . import weapons as weapontable                            # noqa: E402
from .firstperson import WeaponHand, aim_at_camera, view_rig    # noqa: E402
from .hud import GameHUD                                        # noqa: E402
from .player import PlayerState                                 # noqa: E402
from .animator import SurfaceAnimator                           # noqa: E402
from .worldgeometry import SCENE_SCALE                          # noqa: E402

log = logging.getLogger(__name__)

BaseContext: Any = testingcontext.getInteractive()

#: Radians per second the turn keys sweep, and the look keys tilt.
TURN_RATE = 2.0
LOOK_RATE = 1.5

#: The character's proportions in map units, converted to metres.  ``SPEC-BSP38
#: §3.2`` gives the standing player as 56 units tall on a 32 x 32 footprint.
PLAYER_HEIGHT_UNITS = 56.0
PLAYER_RADIUS_UNITS = 16.0
PLAYER_EYE_UNITS = 46.0

#: Movement speeds and the jump, in map units per second.  Not format facts:
#: this viewer's own feel, chosen so a 256-unit hop is reachable.
WALK_SPEED_UNITS = 300.0
RUN_SPEED_UNITS = 480.0
FLY_SPEED_UNITS = 900.0
JUMP_HEIGHT_UNITS = 64.0
STEP_HEIGHT_UNITS = 18.0

#: How far above a spawn point's origin the eye starts.  Map spawn origins sit
#: at the player's centre, not at their feet.
SPAWN_LIFT_UNITS = 24.0

#: Near/far planes in metres.  A map is tens of thousands of units across, and
#: the default near plane is far too close at this scale.
NEAR_PLANE = 0.2
FAR_PLANE = 4000.0

#: Scene time a capture pins the surface animation to, in seconds.  Not zero:
#: at zero every wave is at a zero crossing and a reference image would show a
#: still surface, which proves nothing about a feature whose whole point is
#: that it moves.  Any fixed value makes the image reproducible; this one puts
#: the common `sin` waves somewhere visible.
CAPTURE_TIME = 0.35


def build_parser(prog: str = 'twitch-viewer') -> argparse.ArgumentParser:
    """The viewer's command line."""
    parser = argparse.ArgumentParser(
        prog=prog, description=__doc__.split('Keys::')[0].strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('target', nargs='?',
                        help='a .bsp map, a .pk3/.zip archive, a http(s) URL, '
                             'or pack:mapname (see --list-packs)')
    parser.add_argument('--list-packs', action='store_true',
                        help='list the downloadable content packs and exit')
    parser.add_argument('--fetch', metavar='PACK', default=None,
                        help='download a content pack by key and exit')
    parser.add_argument('--map', dest='map_name', default=None,
                        help='which map to load when an archive holds several')
    parser.add_argument('--lightmap', dest='lightmap_strength', type=float,
                        default=None, metavar='SCALE',
                        help='baked-lighting exposure (default %g, the engine\'s own)'
                             % (maploader.DEFAULT_LIGHTMAP_STRENGTH,))
    parser.add_argument('--subdivisions', type=int, default=None, metavar='N',
                        help='samples per Bezier patch edge on Quake 3 maps')
    parser.add_argument('--content', action='append', default=[], metavar='DIR',
                        help='an extra content directory to resolve textures against')
    parser.add_argument('--core-textures', choices=('ask', 'always', 'never'),
                        default='ask',
                        help='when a map is missing core textures, offer to '
                             'download the replacement pack (default: ask)')
    parser.add_argument('--physics', action=argparse.BooleanOptionalAction,
                        default=True,
                        help='walk with gravity and collision (default on)')
    parser.add_argument('--hud', action=argparse.BooleanOptionalAction,
                        default=None,
                        help='draw the game HUD; on unless capturing, and '
                             '--hud forces it on for a capture too')
    parser.add_argument('--headlight', action='store_true',
                        help='add a lamp at the camera, for maps with no lightmaps')
    parser.add_argument('--shadows', action=argparse.BooleanOptionalAction,
                        default=False,
                        help='real-time shadows (off: the maps bake their own)')
    parser.add_argument('--capture', metavar='PATH', default=None,
                        help='render, save a PNG to PATH, and exit')
    parser.add_argument('--capture-delay', type=float, default=0.5,
                        metavar='SECONDS', help='settle time before capturing')
    parser.add_argument('--frames', type=int, default=10, metavar='N',
                        help='minimum frames to render before capturing')
    parser.add_argument('--spawn', type=int, default=0, metavar='INDEX',
                        help='which spawn point to start at')
    parser.add_argument('--cache-dir', default=None,
                        help='where to cache downloads and unpacked archives')
    parser.add_argument('--verbose', action='store_true', help='log the details')
    #: Which packs the in-window prompt offers when textures are missing.  A
    #: map from a content pack wants that pack's own content; Quake 3's
    #: replacement set names Quake 3's textures and would help it not at all.
    parser.set_defaults(texture_packs=[download.QUAKE3_CORE.key])
    return parser


def list_packs() -> None:
    """Print what may be downloaded, with its size and its terms."""
    for pack in download.ASSET_PACKS:
        print('%-16s %s' % (pack.key, pack.title))
        print('%-16s %s, %s' % ('', download.human_size(pack.approximate_bytes),
                                pack.copyright))
        print('%-16s %s' % ('', pack.url))
    print()
    print('Name a map inside a pack as pack:mapname, e.g. openarena:oa_dm1.')


def resolve_map_target(options: argparse.Namespace,
                       target: Optional[str] = None) -> str:
    """Turn what the user typed into a map file on disk.

    ``pack:mapname`` fetches the pack if it is not already unpacked and adds it
    as a content root, since the map's textures live in the pack rather than
    beside the `.bsp`.  Typing that form is itself the consent to download: the
    pack has to be on disk before there is a window to ask in, and the user has
    asked for it by name.
    """
    asked = target or options.target
    named = download.parse_pack_target(asked)
    if named is None:
        return download.resolve_target(asked, cache_dir=options.cache_dir,
                                       map_name=options.map_name)
    pack, name = named
    root = download.fetch_pack(pack, options.cache_dir)
    path = download.find_map(root, name)
    if path is None:
        raise download.NoMapFound(
            '%s holds no map named %r; it holds %s'
            % (pack.key, name, ', '.join(download.list_maps(root)) or 'nothing'))
    roots = list(download.content_roots(root))
    missing: List[str] = []
    for key in pack.companions:
        companion = download.pack_for_key(key)
        if companion is None:
            continue
        # A companion is *offered*, never fetched behind the user's back: the
        # art pack is an order of magnitude larger than the maps.
        unpacked = download.pack_root(companion, options.cache_dir)
        if unpacked is not None:
            roots.extend(download.content_roots(unpacked))
        else:
            missing.append(companion.key)
            log.warning('%s renders untextured until its content is '
                        'downloaded: %s (%s)', pack.key, companion.key,
                        download.human_size(companion.approximate_bytes))
    if missing:
        options.texture_packs = missing
    options.content = list(options.content) + roots
    return path


def apply_render_env(options: argparse.Namespace) -> None:
    """Translate the render-affecting options into the env vars the pass reads."""
    os.environ['OPENGLCONTEXT_SHADOWS'] = '1' if options.shadows else '0'
    if options.capture:
        # A capture wants a clean, reproducible frame.
        os.environ['OPENGLCONTEXT_DISABLE_FPS_DISPLAY'] = '1'
        os.environ.setdefault('OPENGLCONTEXT_SHADOW_CASCADES', '3')


def yaw_for_angle(degrees: float) -> float:
    """The view platform's yaw for a map's `angle` key, in radians.

    ``SPEC-BSP38 §3.3``: a map's yaw is measured counter-clockwise about +Z
    with 0 along +X.  The view platform's angles rotate the *world*, so its
    forward is ``(sin yaw, 0, -cos yaw)`` — a rising yaw turns the camera
    right, the opposite of the map's convention.  The offset and the sign flip
    together are this expression; the test that pins it measures the resulting
    direction rather than the number, because asserting on the number would
    only restate whatever this line says.
    """
    return math.pi / 2.0 - math.radians(degrees)


def gaze(nav: Any) -> np.ndarray:
    """The world-space direction the camera looks.

    The camera's orientation applied to the viewing axis.  Used to check where
    a look really points, which is the only meaningful way to test pitch: the
    view platform's angles rotate the world rather than the camera, so the sign
    of ``nav.pitch`` says nothing on its own.
    """
    matrix = np.asarray(nav.camera_orientation().matrix())[:3, :3]
    return matrix @ np.array([0.0, 0.0, -1.0])


def movement_modes() -> List[Any]:
    """The ways of moving this viewer offers, as declared nodes.

    Declared rather than hand-rolled: a settings screen can enumerate them and
    their bindings with no knowledge of this viewer, and a game embedding the
    same modes can retune them by setting fields.  The speeds are the map-unit
    figures above converted to scene metres (``SPEC-BSP38 §3.2``), since a mode
    ships with speeds suited to a metric scene.

    ``FPSMode`` walks exactly as ``WalkMode`` does and differs only in taking
    the pointer to steer with, which is what makes an arena playable rather
    than merely walkable.  **It is declared first, so it is the mode the viewer
    starts in** -- the navigation manager takes the first selectable mode, and
    an arena map is played with the mouse.  Walking with `q`/`e` stays one `m`
    away for anyone who would rather not have the pointer taken.

    ``SwimMode`` is declared even though nothing yet reports being submerged:
    it is world-imposed, so it never appears in the walk/fly cycle, and it
    starts working the moment liquid volumes feed ``platform.submerged``.
    """
    return [
        movemodes.FPSMode(
            name='fps',
            walkSpeed=WALK_SPEED_UNITS * SCENE_SCALE,
            runSpeed=RUN_SPEED_UNITS * SCENE_SCALE,
            turnRate=TURN_RATE, lookRate=LOOK_RATE),
        movemodes.WalkMode(
            name='walk',
            walkSpeed=WALK_SPEED_UNITS * SCENE_SCALE,
            runSpeed=RUN_SPEED_UNITS * SCENE_SCALE,
            turnRate=TURN_RATE, lookRate=LOOK_RATE),
        movemodes.FlyMode(
            name='fly',
            flySpeed=FLY_SPEED_UNITS * SCENE_SCALE,
            turnRate=TURN_RATE, lookRate=LOOK_RATE),
        movemodes.SwimMode(
            name='swim',
            swimSpeed=WALK_SPEED_UNITS * 0.6 * SCENE_SCALE,
            turnRate=TURN_RATE, lookRate=LOOK_RATE),
    ]


#: Modes whose movement is free of gravity, so the character has to be taken
#: out of the falling solver when one of them takes over.  Swimming is one of
#: them: a swimmer still pulled down by gravity ends up on the bottom of every
#: pool.  Buoyancy proper -- a fraction of gravity, as ``SwimMode.buoyancy``
#: describes -- would need the character controller to carry it, and this is
#: the neutral version of the same idea.
FLYING_MODES = ('fly', 'swim')


def update_submerged(nav: Any, volumes: Any) -> None:
    """Tell the navigator whether the camera is under a liquid surface.

    The eye rather than the capsule centre: what decides whether a player is
    swimming is where they are looking from, and it is the reading that matches
    what the view shows.  ``SwimMode`` watches this and imposes itself, so
    nothing here selects a mode.
    """
    if nav is None:
        return
    nav.submerged = bool(volumes is not None
                         and volumes.contains(nav.camera_position()))


def apply_mode(nav: Any, mode: Any) -> None:
    """Tell the character controller what a mode change means for it.

    Flying is a property of the character rather than of the movement it is
    given, so a mode that only sets a velocity would fly into the floor.
    """
    if nav is None or mode is None:
        return
    nav.set_fly(mode.name in FLYING_MODES)


#: Set ``TWITCH_DEBUG_JUMP=1`` to have every jump press report what the capsule
#: thought at the time.  "Space did nothing" is unanswerable without it: the
#: press has to survive the event queue, reach the mode that owns the binding,
#: reach the character, and find the character on its feet, and any of the four
#: failing looks identical from the outside.
DEBUG_JUMP_ENV = 'TWITCH_DEBUG_JUMP'


def watch_jumps(nav: Any, report: Optional[Callable[[str], None]] = None) -> Any:
    """Wrap a navigator's ``jump`` so each attempt says what happened.

    Returns the navigator.  Wrapping is idempotent: asking twice leaves one
    report per press rather than two.
    """
    if getattr(nav, '_jumpWatched', False):
        return nav
    inner = nav.jump
    say = report if report is not None else _print_line

    def watched() -> Any:
        character = getattr(nav, 'character', None)
        fired = inner()
        say('jump %s: grounded=%s crouching=%s flying=%s vy=%.2f'
            % ('jumped' if fired else 'refused',
               getattr(character, 'grounded', '?'),
               getattr(character, 'crouching', '?'),
               getattr(character, 'flying', '?'),
               float(getattr(character, 'vy', 0.0) or 0.0)))
        return fired

    nav.jump = watched
    nav._jumpWatched = True
    return nav


def _print_line(line: str) -> None:   # pragma: no cover - console output
    sys.stdout.write(line + '\n')
    sys.stdout.flush()


def context_definition() -> ContextDefinition:
    """A context definition carrying this viewer's declared modes."""
    return ContextDefinition(movementModes=movement_modes())


def character_capabilities() -> CharacterCapabilities:
    """The avatar's proportions and speeds, in scene units."""
    return CharacterCapabilities(
        radius=PLAYER_RADIUS_UNITS * SCENE_SCALE,
        standHeight=PLAYER_HEIGHT_UNITS * SCENE_SCALE,
        crouchHeight=PLAYER_HEIGHT_UNITS * 0.5 * SCENE_SCALE,
        eyeHeight=PLAYER_EYE_UNITS * SCENE_SCALE,
        stepHeight=STEP_HEIGHT_UNITS * SCENE_SCALE,
        jumpHeight=JUMP_HEIGHT_UNITS * SCENE_SCALE,
        walkSpeed=WALK_SPEED_UNITS * SCENE_SCALE,
        runSpeed=RUN_SPEED_UNITS * SCENE_SCALE,
        flySpeed=FLY_SPEED_UNITS * SCENE_SCALE,
    )


def choose_spawn(loaded: maploader.LoadedMap,
                 index: int = 0) -> Tuple[np.ndarray, float]:
    """``(eye position, platform yaw)`` for a map's spawn point.

    A map with no spawn entity still has to be enterable, so the fallback is
    the centre of its bounds, a little above the floor.
    """
    spawns = loaded.spawn_points()
    if spawns:
        spawn = spawns[index % len(spawns)]
        eye = np.asarray(spawn.position, dtype='d').copy()
        eye[1] += SPAWN_LIFT_UNITS * SCENE_SCALE
        return eye, yaw_for_angle(spawn.angle)
    low, high = loaded.world.bounds
    centre = (np.asarray(low, dtype='d') + np.asarray(high, dtype='d')) * 0.5
    centre[1] = float(high[1]) - PLAYER_HEIGHT_UNITS * SCENE_SCALE
    return centre, 0.0


def collision_world(loaded: maploader.LoadedMap) -> Optional[PhysicsWorld]:
    """A physics world holding the map as one static trimesh, or None."""
    mesh = loaded.collision_mesh()
    if mesh is None:
        return None
    points, triangles = mesh
    world = PhysicsWorld(gravity=model.Gravity(gravity=9.81, direction=(0, -1, 0)))
    shape = world.add_shape(model.Shape.trimesh(points, triangles))
    world.add_body(model.Motion(type=model.STATIC), model.Collider(shape=shape))
    return world


class TwitchContext(OverlayMixin, BaseContext):
    """The viewer window: a loaded map, a walking camera, and jump pads.

    :class:`~OpenGLContext.ui.overlay.OverlayMixin` comes first so its event
    routing runs before the navigation mix-in's: while a modal panel is up the
    input sampler is not fed at all, which is what stops the player walking on
    while they answer a question.
    """

    config: Any = None
    _target: Optional[str] = None
    # Supplied by the interactive runtime base (event + navigation mixins),
    # which the minimal type-check-time Context alias does not expose.
    platform: Any
    movementManager: Any
    addEventHandler: Any
    triggerRedraw: Any
    sg: Any

    def OnInit(self) -> None:                   # pragma: no cover - needs a window
        disable_vsync()
        if self.config is None:
            self.config = build_parser().parse_args([self._target or ''])
        self.loaded = load_map(self.config, self._target)
        # Built before the scene, because a surface has to be told it deforms
        # before its vertex buffers exist -- that is what decides whether its
        # texture-coordinate buffer is dynamic.
        self._animator = SurfaceAnimator()
        self._started = time.time()
        # Before the scene: the weapon in the player's hands is part of it, so
        # what is held has to be settled before the children are gathered.
        self._buildLoadout()
        self.sg = SceneGraph(children=self._scene_children())
        self.platform.setFrustum(near=NEAR_PLANE, far=FAR_PLANE)
        # The event system holds callbacks weakly by design, so a binding built
        # from a bare closure is collected the moment the binding call returns
        # and the key silently stops working.  Every handler below is a bound
        # method of this long-lived context, which is what keeps them alive.
        self._walking = False
        self._free_manager = getattr(self, 'movementManager', None)
        self._nav: Optional[PhysicsViewPlatform] = None
        self._pushes: Optional[jumppads.PushSystem] = None
        self._liquids: Any = None
        self._last = time.time()
        # The event system holds its callbacks weakly, so the wheel handlers
        # are kept here rather than being collected as soon as they are bound.
        self._wheelHandlers: List[Any] = []
        self._capture = None
        if self.config.capture:
            self._capture = SettleCapture(self.config.capture,
                                          delay=self.config.capture_delay,
                                          min_frames=self.config.frames)
        # After the capture, because building the HUD asks for a redraw and a
        # frame drawn before the capture exists has nothing to report to.
        self._startGame()
        self.addEventHandler('keypress', name='g', function=self._toggle_walk)
        self.bindScreenKeys(self)
        if self.config.physics:
            # Walk mode also decides where the camera starts, so a capture runs
            # it too: a map's spawn point is a far better view of it than the
            # scene origin, which is as likely as not to be inside a wall.
            self._set_walking(True)
        self._report()
        if not self.config.capture:
            # A capture has nobody to answer, so it never asks.
            self._offer_core_textures()

    # -- scene -----------------------------------------------------------
    def _scene_children(self) -> List[Any]:     # pragma: no cover - needs a window
        children: List[Any] = [_backdrop(), self.loaded.scene(self._animator)]
        # The weapon rides a transform that is put where the camera is each
        # frame, so it is part of the scene rather than something drawn after
        # it: it takes the map's lighting, and it is occluded by geometry the
        # way anything else in the world is.
        children.append(self.viewpointAttachment())
        if self.config.headlight:
            self.headlight = PointLight(location=(0, 0, 0), color=(1, 0.96, 0.9),
                                        intensity=2.0, radius=60.0)
            children.append(self.headlight)
        else:
            # A scene with no lights at all gets the pass's default headlight,
            # which for a map is a second, unwanted lighting model on top of the
            # baked one.  A light of zero intensity is still a light, so the
            # substitution does not happen and the lightmaps stand alone.
            children.append(DirectionalLight(direction=(0, -1, 0), intensity=0.0))
        return children

    def viewpointAttachment(self) -> Any:       # pragma: no cover - needs a window
        """The transform everything held in the player's hands hangs from.

        Carries the weapon *and* the light that shows it -- a map places no
        dynamic lights, so a weapon lit only by the map is a silhouette.
        """
        if getattr(self, 'camera', None) is None:
            self.camera = view_rig(self.hand)
        return self.camera

    # -- the in-window prompt --------------------------------------------
    def _offer_core_textures(self) -> None:     # pragma: no cover - GL
        """Put the download question on screen rather than in the terminal.

        By the time a map is drawn the terminal is behind the window, so the
        console prompt was asking somewhere the user is not looking.
        """
        if not texture_pack_offer(self.loaded, self.config):
            return
        self.pushOverlay(build_texture_prompt(self.loaded, self.config,
                                              self._core_textures_answered))

    def _core_textures_answered(self, yes: bool) -> None:   # pragma: no cover - GL
        if not yes:
            sys.stdout.write('not downloading; run with --content to point at '
                             'content you already have\n')
            sys.stdout.flush()
            return
        for pack in texture_pack_offer(self.loaded, self.config):
            try:
                root = download.fetch_pack(pack, self.config.cache_dir)
            except Exception as error:          # noqa: BLE001 - never fail a frame
                log.warning('could not fetch %s: %s', pack.key, error)
                continue
            self.config.content = (list(self.config.content)
                                   + download.content_roots(root))
        self.loaded = load_map(self.config, self._target)
        # Built before the scene, because a surface has to be told it deforms
        # before its vertex buffers exist -- that is what decides whether its
        # texture-coordinate buffer is dynamic.
        self._animator = SurfaceAnimator()
        self._started = time.time()
        # The loadout is *not* rebuilt: this reloads the map's textures, and a
        # player who loses their health and their weapon for accepting a
        # download would rightly call that a bug.  The weapon's transform is
        # reused, so it rejoins the new scene as it was.
        self.sg = SceneGraph(children=self._scene_children())
        self.triggerRedraw(1)

    def _buildLoadout(self) -> None:            # pragma: no cover - GL
        """What the player is carrying, and the weapon their hands hold.

        Separate from :meth:`_startGame` and run earlier, because the held
        weapon is a child of the scene: it has to exist before the scenegraph
        is gathered, while the HUD must wait until the capture does.
        """
        self.weapons = weapontable.default_table()
        # Carrying everything, because nothing in a map hands a player a weapon
        # yet -- item entities are §6.  See PlayerState.carrying.
        self.player = PlayerState.carrying(self.weapons)
        self.weaponBindings = controls.WeaponBindings()
        self.hand = WeaponHand(self.weapons)
        self.hand.select(self.weapons.by_key(self.player.selected))

    def _startGame(self) -> None:               # pragma: no cover - GL
        """Put the HUD on screen and register the overlay's sections.

        A capture run gets no HUD *unless it asks for one*: a reference image
        is of the map, and a health bar over one turns every visual-regression
        comparison into a comparison of the health bar.  Someone capturing a
        picture of the game rather than of the map passes ``--hud``.  The
        developer overlay is already answered by
        ``OPENGLCONTEXT_DISABLE_FPS_DISPLAY``.
        """
        self.hud = GameHUD(self.weapons)
        wanted = self.config.hud
        self.hud.visible = (self.config.capture is None if wanted is None
                            else bool(wanted))
        self.addHUDLayer(self.hud)
        twitchdebug.install(self)
        self._bindWeaponKeys()

    def _bindWeaponKeys(self) -> None:          # pragma: no cover - GL
        """Arrange for the weapon keys and the wheel to reach the frame loop.

        The keys are *sampled* from the declared bindings, like movement, so
        this only has to make sure the events arrive; the wheel is a mouse
        button rather than a key and the sampler does not see one, so it is
        handled directly.
        """
        for binding in self.weaponBindings.bindings:
            for key in binding.keys:
                for state in (1, 0):
                    self.addEventHandler('keyboard', name=str(key),
                                         state=state, function=self._on_input)
        for button, step in ((WHEEL_UP, 1), (WHEEL_DOWN, -1)):
            self.addEventHandler('mousebutton', button=button, state=1,
                                 function=self._wheelWeapon(step))

    def _wheelWeapon(self, step: int) -> Any:   # pragma: no cover - GL
        def turn(event: Any = None) -> None:
            command = (controls.NEXT_WEAPON if step > 0
                       else controls.PREVIOUS_WEAPON)
            self._runCommands([command], firing=False)
        # Held on the context, because the event system keeps its callbacks
        # weakly and a bare closure would be collected the moment this returns.
        self._wheelHandlers.append(turn)
        return turn

    def _runCommands(self, commands: Any, firing: bool) -> None:
        """Apply this frame's weapon commands and answer what they emitted.

        The rules return events and this decides what to do with them, which is
        the seam §11 asks for: the HUD reads events and never writes state.
        """
        for event in controls.apply_commands(commands, firing, self.player,
                                             self.weapons, time.time()):
            if event.text:
                self.hud.post(event.text)
        self.triggerRedraw(1)

    def _sampleWeapons(self) -> None:           # pragma: no cover - GL
        """Read the weapon commands out of this frame's input."""
        state = self.getInputState()
        commands = self.weaponBindings.triggered(state)
        firing = self.weaponBindings.firing(state)
        if commands or firing:
            self._runCommands(commands, firing)

    def physicsWorld(self) -> Any:
        """The physics world once walking has begun, else None.

        A method rather than an attribute because the developer overlay's
        physics section asks for it every frame, and the world is replaced
        whenever a map is.
        """
        nav = self._nav
        return getattr(nav, 'world', None) if nav is not None else None

    def bindScreenKeys(self, context: Any = None) -> None:
        """Bind the function keys that open a screen or take a shot.

        On ``keyboard`` rather than ``keypress``, and on the key going *down*:
        a function key produces no character, so GLFW never raises a keypress
        for one, and a keypress binding for one is accepted and then never
        fires.

        ``context`` is what to bind on, defaulting to this one, so a test can
        hand in a recorder instead of standing up a window.
        """
        context = context if context is not None else self
        for name, attribute in SCREEN_KEYS:
            context.addEventHandler('keyboard', name=name, state=1,
                                    function=getattr(self, attribute))

    def renderShaderOverlay(self, pass_: Any) -> None:   # pragma: no cover - GL
        """Bring the HUD up to date, then let the layers draw themselves.

        Reading the player's state here rather than when it changes is what
        keeps the HUD honest about the things that move on their own -- the
        cone of fire closing, a message fading -- without anything having to
        remember to invalidate it.
        """
        self._updateHUD()
        super(TwitchContext, self).renderShaderOverlay(pass_)

    def placeViewAttachments(self, pass_: Any = None) -> None:
        """Pin the weapon to the view for the frame that is about to be drawn.

        Called by the render pass once the camera is settled and before any
        geometry is gathered, which is the only moment this can be done
        correctly: posed from ``OnIdle`` it is written *before* the frame's
        movement, so the weapon hangs back and then slides forward as the
        player walks -- and a first-person model that swims is unusable however
        good it looks standing still.

        Because it is written from the same camera pose the frame is drawn
        with, the two cancel exactly in the modelview and the weapon is fixed
        in view space rather than chasing the camera through the world.
        """
        hand = getattr(self, 'hand', None)
        if hand is None:
            return
        if hand.select(self.weapons.by_key(self.player.selected)):
            self.triggerRedraw(1)
        aim_at_camera(self.viewpointAttachment(), self.getViewPlatform())

    def _updateHUD(self) -> None:               # pragma: no cover - GL
        hud = getattr(self, 'hud', None)
        if hud is None or not hud.visible:
            return
        platform = self.getViewPlatform()
        hud.update(self.player, now=time.time(), viewport=self.getViewPort(),
                   field_of_view=getattr(platform, 'fieldOfView',
                                         hud_default_fov()))

    def _settings(self, event: Any) -> None:    # pragma: no cover - GL
        """Open the rendering settings over the map (F10).

        The screen is generated from ``ContextDefinition``'s own fields, so a
        map that runs badly can trade shadows or environment lighting away
        without a restart.
        """
        settings.open_settings(self)

    def _bindings(self, event: Any) -> None:    # pragma: no cover - GL
        """Open the key-binding page (F6): movement, and the weapon commands.

        One page for both, through :class:`~twitchoglc.controls.Controls`,
        because a player rebinding their keys is rebinding *their keys* and
        should not have to find two screens to do it.
        """
        bindings.open_bindings(self, navigation=controls.Controls(
            self.getNavigation(), self.weaponBindings))

    def _report(self) -> None:                  # pragma: no cover - console output
        loaded = self.loaded
        sys.stdout.write(
            '%s: %s map, %d triangles in %d batches, %d lightmap pages\n'
            % (loaded.name, loaded.family, loaded.world.triangle_count,
               len(loaded.world.batches), len(loaded.atlas.pages)))
        sys.stdout.write('  %s\n' % (jumppads.describe(loaded.push_volumes()),))
        sys.stdout.write("  'g' toggles walk / free-fly, 'f' flies, 'm' cycles "
                         "movement mode, space jumps\n")
        sys.stdout.write("  1/2/3 choose a weapon and ctrl fires; alt+f shows "
                         "the developer overlay, F6/F10 the key and rendering "
                         "settings\n")
        sys.stdout.write("  1/2/3 choose a weapon, ctrl fires; alt+f shows the "
                         "developer overlay, F6/F10 the key and render "
                         "settings\n")
        sys.stdout.flush()

    # -- walk / free-fly -------------------------------------------------
    def _toggle_walk(self, event: Any = None) -> None:  # pragma: no cover - key
        self._set_walking(not self._walking)

    def _set_walking(self, walking: bool) -> bool:      # pragma: no cover - GL
        """Hand the camera and the movement keys to one navigator or the other.

        Two navigators writing ``context.platform`` fight: while a built-in key
        is held its interpolator glides the camera, then on release the physics
        pose snaps it back.  So the free-fly manager is unbound while walking,
        and rebound on the way out — and the unbind is undone if the camera
        placement below fails, or the window is left with no navigator at all.
        """
        if walking:
            if self._nav is None and not self._start_physics():
                return False
            if self.movementManager is not None and self._free_manager is not None:
                self._free_manager.unbind(self)
                self.movementManager = None
            self._bind_movement_keys()
        else:
            if self.movementManager is None and self._free_manager is not None:
                self._free_manager.bind(self)
                self.movementManager = self._free_manager
        self._walking = walking
        self.triggerRedraw(1)
        return True

    def _start_physics(self) -> bool:           # pragma: no cover - GL
        world = collision_world(self.loaded)
        if world is None:
            sys.stdout.write('no solid geometry to walk on; staying in free-fly\n')
            return False
        eye, yaw = choose_spawn(self.loaded, self.config.spawn)
        gravity = self.loaded.gravity * SCENE_SCALE
        self._nav = PhysicsViewPlatform(world, character_capabilities(), yaw=yaw,
                                        gravity=gravity)
        self._nav.bind_eye(tuple(eye))
        self._pushes = jumppads.PushSystem(self.loaded.push_volumes(gravity))
        self._liquids = self.loaded.liquid_volumes()
        if os.environ.get(DEBUG_JUMP_ENV):
            watch_jumps(self._nav)
        self._nav.apply(self)
        self._last = time.time()
        return True

    def getNavigationPlatform(self) -> Any:     # pragma: no cover - GL
        """What the declared movement modes drive.

        The physics navigator once walking has begun, so a mode moves the
        character controller and the camera follows it.  Before that the
        free-fly manager still owns the camera and the modes stay out of it.
        """
        if self._walking and self._nav is not None:
            return self._nav
        return self.getViewPlatform()

    def _bind_movement_keys(self) -> None:      # pragma: no cover - GL
        """Bind the keys the declared modes name, plus the mode switches.

        The modes decide what each key *means*; this only arranges for the
        events to arrive, since the sampler is fed from event dispatch.
        """
        for _name, binding in self.getNavigation().binding_table():
            for key in binding.keys:
                self.addEventHandler('keyboard', name=key, state=1,
                                     function=self._on_input)
                self.addEventHandler('keyboard', name=key, state=0,
                                     function=self._on_input)
        self.addEventHandler('keypress', name='f', function=self._toggle_fly)
        self.addEventHandler('keypress', name='m', function=self._cycle_mode)

    def _on_input(self, event: Any) -> None:    # pragma: no cover - key
        """Wake the frame loop; the sampler is fed by event dispatch itself."""
        self.triggerRedraw(1)

    def _toggle_fly(self, event: Any = None) -> None:   # pragma: no cover - key
        navigation = self.getNavigation()
        if navigation is None:
            return
        current = getattr(self.contextDefinition, 'movementMode', None)
        wanted = 'walk' if current is not None and current.name == 'fly' else 'fly'
        navigation.select(wanted)

    def _cycle_mode(self, event: Any = None) -> None:   # pragma: no cover - key
        navigation = self.getNavigation()
        if navigation is not None:
            navigation.cycle()

    def _screenshot(self, event: Any = None) -> None:   # pragma: no cover - key
        from OpenGLContext.capture import capture_to_png
        name = time.strftime('twitch-%Y%m%d-%H%M%S.png')
        if capture_to_png(name):
            sys.stdout.write('saved %s\n' % (name,))
            sys.stdout.flush()

    # -- frame -----------------------------------------------------------
    def OnIdle(self, *args: Any) -> int:        # pragma: no cover - needs a window
        # Surfaces animate whether or not the player is walking: a conveyor belt
        # and a pool of lava do not stop because nobody is moving.
        animated = self._animate()
        # Before the walking check: a weapon can be chosen from a free-flying
        # camera, and a player who cannot switch weapons until they land would
        # rightly call that a bug.
        self._sampleWeapons()
        if not self._walking or self._nav is None:
            if self._capture is not None:
                # A capture waits for a settled frame, and only a redraw makes
                # one; with nothing else driving the loop it would wait forever.
                self.triggerRedraw(1)
                return 1
            return 1 if animated else 0
        now = time.time()
        dt = min(now - self._last, 0.05)
        self._last = now
        update_submerged(self._nav, self._liquids)
        self.updateNavigation(dt)
        apply_mode(self._nav, getattr(self.contextDefinition, 'movementMode', None))
        self._nav.update(dt)
        self._apply_pushes(dt)
        if self.config.headlight:
            self.headlight.location = self._nav.camera_position()
        self._nav.apply(self)
        self.triggerRedraw(1)
        return 1

    def _animate(self) -> bool:                 # pragma: no cover - needs a window
        """Move the map's animated surfaces to the current scene time.

        Returns whether anything moved, which is also whether the loop has to
        keep asking for frames: a map with nothing animated must not be redrawn
        continuously just because it *could* be.

        A capture pins the clock (:data:`CAPTURE_TIME`) rather than reading it.
        A reference image of a scrolling surface taken at a wall-clock instant
        is a different image every run, which makes the whole visual-regression
        gate useless for exactly the maps this feature is for.
        """
        animator = getattr(self, '_animator', None)
        if not animator:
            return False
        now = (CAPTURE_TIME if self._capture is not None
               else time.time() - self._started)
        animator.update(now)
        self.triggerRedraw(1)
        return True

    def _apply_pushes(self, dt: float) -> None:  # pragma: no cover - GL
        """Fire any push volume the player is standing in.

        ``SPEC-TRIGGER-PUSH §7.6``: contacts are evaluated after the frame's
        movement, so this runs after ``nav.update``.  ``§7.8``: a noclip player
        generates none.
        """
        nav, pushes = self._nav, self._pushes
        if nav is None or pushes is None:
            return
        velocity = pushes.update(dt, nav.character.position,
                                 noclip=nav.character.flying)
        if velocity is not None:
            nav.apply_impulse(velocity)

    def SwapBuffers(self, *args: Any) -> Any:   # pragma: no cover - needs a window
        if self._capture is not None and self._capture.tick():
            result = super(TwitchContext, self).SwapBuffers(*args)
            self.setCurrent()
            sys.stdout.write('captured %s\n' % (self.config.capture,))
            sys.stdout.flush()
            os._exit(0)
            return result
        return super(TwitchContext, self).SwapBuffers(*args)


def hud_default_fov() -> float:
    """The vertical field of view the reticule is projected through by default.

    The view platform's own frustum is what should answer this; it is read
    defensively because the platform is built after the first frame is asked
    for, and a reticule drawn one frame at the wrong width is better than a
    frame that fails.
    """
    return math.pi / 2.0


#: Keys that open a screen or take a screenshot, and the handler each runs.
#: Bound as ``keyboard`` key-downs; see ``TwitchContext.bindScreenKeys``.
SCREEN_KEYS = (
    ('<F2>', '_screenshot'),
    ('<F6>', '_bindings'),
    ('<F10>', '_settings'),
)

#: How many missing texture names to name before saying "and N more".
MISSING_TEXTURES_LISTED = 4


def texture_pack_offer(loaded: Any, options: argparse.Namespace
                       ) -> List[download.AssetPack]:
    """The packs worth offering for a map's missing textures.

    Empty when nothing is missing, when the user has said ``never``, or when
    every pack is already unpacked — a pack on disk is used rather than asked
    about, which makes the download once per user rather than once per run.

    A release may split what one map needs across several packs, so this is a
    list and the prompt asks about all of them at once: a question that has to
    be answered again on the next launch to get the rest is a worse question.
    """
    if not loaded.missing_textures() or options.core_textures == 'never':
        return []
    packs = [download.pack_for_key(key) for key in options.texture_packs]
    return [pack for pack in packs
            if pack is not None
            and download.pack_root(pack, options.cache_dir) is None]


def build_texture_prompt(loaded: Any, options: argparse.Namespace,
                         on_answer: Optional[Any]) -> Panel:
    """The question asked over the frame about a missing-texture download.

    Size and licence are on it because they are what the answer turns on.  It
    is a modal panel, so nothing reaches the world while it is unanswered, and
    Download is its primary action and so its Enter default.
    """
    missing = loaded.missing_textures()
    packs = texture_pack_offer(loaded, options)
    total = sum(pack.approximate_bytes for pack in packs)
    question = ('This map is missing %d textures: %s.  Download %s?  About %s '
                'in total.'
                % (len(missing),
                   _missing_summary(missing).split(': ', 1)[-1],
                   ' and '.join(pack.title for pack in packs),
                   download.human_size(total)))
    detail = '\n'.join('%s -- %s' % (pack.copyright, pack.url)
                       for pack in packs)
    return dialogs.confirm(question, detail=detail, on_answer=on_answer,
                           yes='Download', no='Not now',
                           yes_keys=('y',), no_keys=('n',))


def available_textures(loaded: Any,
                       options: argparse.Namespace) -> List[str]:
    """The pack roots that can be used without asking.

    Packs already unpacked on disk — which is what makes the download once per
    user rather than once per run — and, for ``always``, freshly fetched ones.
    It never prompts: ``ask`` is answered in the window.
    """
    if options.core_textures == 'never' or not loaded.missing_textures():
        return []
    roots = []
    for key in options.texture_packs:
        pack = download.pack_for_key(key)
        if pack is None:
            continue
        existing = download.pack_root(pack, options.cache_dir)
        if existing is not None:
            roots.append(existing)
        elif options.core_textures == 'always':
            try:
                roots.append(download.fetch_pack(pack, options.cache_dir))
            except Exception as error:          # noqa: BLE001 - never fail a load
                log.warning('could not fetch %s: %s', pack.key, error)
    return roots


def _missing_summary(missing: List[str]) -> str:
    """A one-line account of what a map could not find."""
    shown = ', '.join(missing[:MISSING_TEXTURES_LISTED])
    if len(missing) > MISSING_TEXTURES_LISTED:
        shown += ' and %d more' % (len(missing) - MISSING_TEXTURES_LISTED,)
    return 'This map is missing %d textures: %s' % (len(missing), shown)


def load_map(options: argparse.Namespace,
             target: Optional[str] = None) -> maploader.LoadedMap:
    """Resolve what the user asked for and load the map it names.

    Loading never *asks* anything.  A pack already on disk is used silently,
    and ``--core-textures always`` fetches one for an automated run, but the
    question of whether to download belongs in the window, over the map it is
    about — see :meth:`TwitchContext._offer_core_textures`.  Asking here would
    block before the window is even open, and the overlay would never get a
    chance to draw.

    A map whose textures turn out to be missing is loaded a second time with
    the pack added, since the texture sizes feed the version 38 UV projection
    (``SPEC-BSP38 §6.2``) and so cannot be patched in afterwards.
    """
    path = resolve_map_target(options, target)
    loaded = _load(options, path)
    roots = available_textures(loaded, options)
    if roots:
        for root in roots:
            options.content = list(options.content) + download.content_roots(root)
        loaded = _load(options, path)
    return loaded


def _load(options: argparse.Namespace, path: str) -> maploader.LoadedMap:
    return maploader.load(path,
                          lightmap_strength=options.lightmap_strength,
                          extra_roots=options.content,
                          subdivisions=options.subdivisions)


def _backdrop() -> Background:
    """What shows through a map's sky surfaces.

    ``SPEC-BSP38 §8.1``: a sky surface is a hole the sky is shown through, and
    the geometry builder leaves those holes undrawn, so this is what fills them.
    A dim sky rather than a bright one: these are mostly interiors lit by their
    own baked lighting, and a bright backdrop reads as a hole in the wall.
    """
    return Background(
        skyColor=[(0.06, 0.07, 0.10), (0.12, 0.14, 0.18), (0.20, 0.22, 0.26)],
        skyAngle=[1.05, 1.5708],
        groundColor=[(0.05, 0.05, 0.06)],
        groundAngle=[1.5708],
    )


def disable_vsync() -> None:                    # pragma: no cover - needs GLFW
    """Uncap the frame rate.

    A forced redraw every frame blocks on the buffer swap when no compositor is
    presenting frames, which is exactly the headless capture case: without this
    a probe renders one frame and then hangs.  Public because every one of this
    project's windows redraws that way and needs it.
    """
    try:
        import glfw
        glfw.swap_interval(0)
    except Exception:
        pass


def main(argv: Optional[List[str]] = None) -> None:
    """Run the viewer."""
    options = build_parser().parse_args(argv)
    if options.list_packs:
        list_packs()
        raise SystemExit(0)
    if options.fetch:
        pack = download.pack_for_key(options.fetch)
        if pack is None:
            build_parser().error(
                'no pack named %r; --list-packs shows them' % (options.fetch,))
        else:
            print(download.fetch_pack(pack, options.cache_dir))
        raise SystemExit(0)
    if not options.target:
        build_parser().error('name a map to view, or --list-packs')
    logging.basicConfig(level=logging.DEBUG if options.verbose else logging.INFO)
    logging.getLogger('OpenGLContext.scenegraph.text').setLevel(logging.WARNING)
    apply_render_env(options)
    TwitchContext.config = options
    TwitchContext._target = options.target
    TwitchContext.ContextMainLoop(definition=context_definition())


if __name__ == '__main__':
    main()
