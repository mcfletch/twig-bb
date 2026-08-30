#! /usr/bin/env python
"""Walk through a Quake 3 map.

Usage::

    twig-bb maps/oa_dm1.bsp
    twig-bb some-map.pk3
    twig-bb https://example.com/some-map.pk3
    twig-bb openarena:oa_dm1          # from a content pack
    twig-bb --list-packs              # what can be downloaded

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
    1 - 5                   choose a weapon; [ ] and the wheel step through them
    left mouse button       fire (held); ctrl does the same
    alt + f                 the developer overlay
    F2                      save a screenshot (alt + s does the same)
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
:mod:`twig_bb.jumppads`.  Water, slime and lava are volumes rather than
floors, so the avatar falls in and swims: see :mod:`twig_bb.liquids`.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

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
from omi_physics.character import CharacterCapabilities         # noqa: E402

from OpenGLContext.events import systemtime                     # noqa: E402
from OpenGLContext.events.mouseevents import WHEEL_DOWN, WHEEL_UP  # noqa: E402
from OpenGLContext.ui import bindings, dialogs, settings         # noqa: E402
from OpenGLContext.ui.overlay import OverlayMixin                # noqa: E402
from OpenGLContext.viewer.asyncscene import AsyncSceneMixin      # noqa: E402
from OpenGLContext.ui.panel import Panel                         # noqa: E402

from . import avatar                                            # noqa: E402
from . import blast, collision, combat, combatsound             # noqa: E402
from . import controls                                          # noqa: E402
from . import projectiles                                       # noqa: E402
from . import download                                          # noqa: E402
from . import effects, falling, feedback, fetcher, game         # noqa: E402
from . import arena                                             # noqa: E402
from . import characters                                        # noqa: E402
from . import deathcam                                          # noqa: E402
from . import items as itemsmod                                 # noqa: E402
from . import jumppads, liquids, mapnotice, maploader, menu, notices  # noqa: E402
from . import match                                             # noqa: E402
from . import rules                                             # noqa: E402
from . import underwater                                        # noqa: E402
from . import debug as twigdebug                              # noqa: E402
from . import telemetry as gamemarks                            # noqa: E402
from . import weapons as weapontable                            # noqa: E402
from .firstperson import WeaponHand, aim_at_camera, view_rig    # noqa: E402
from .frameclock import FrameClock                              # noqa: E402
from .hud import GameHUD, now as hudclock                       # noqa: E402
from .player import PlayerState                                 # noqa: E402
from .animator import SurfaceAnimator                           # noqa: E402
from .worldgeometry import SCENE_SCALE                          # noqa: E402

log = logging.getLogger(__name__)

BaseContext: Any = testingcontext.getInteractive()

#: Radians per second the turn keys sweep, and the look keys tilt.
TURN_RATE = 2.0
LOOK_RATE = 1.5

#: The character's proportions in map units.  Re-exported from
#: :mod:`twig_bb.avatar` rather than restated: the capsule the player walks
#: in and the capsule a shot meets have to be the same body, and when they
#: were declared in two places they were forty centimetres apart.
PLAYER_HEIGHT_UNITS = avatar.PLAYER_HEIGHT_UNITS
PLAYER_RADIUS_UNITS = avatar.PLAYER_RADIUS_UNITS
PLAYER_EYE_UNITS = avatar.PLAYER_EYE_UNITS

#: Movement speeds and the jump, in map units per second.  Not format facts:
#: this viewer's own feel, chosen so a 256-unit hop is reachable.
WALK_SPEED_UNITS = 300.0
RUN_SPEED_UNITS = 480.0
FLY_SPEED_UNITS = 900.0
#: Swimming is deliberately slow: water is what you push against, and a pool
#: crossed at walking pace does not read as water.
SWIM_SPEED_UNITS = 180.0
JUMP_HEIGHT_UNITS = 64.0
STEP_HEIGHT_UNITS = 18.0

#: How far above the *feet* a spawn point's origin sits, in map units: a map's
#: spawn origins are not at the floor.  One constant, in
#: :mod:`twig_bb.avatar`, because the eye a camera binds to and the feet a
#: body is published at both come from it — declared apart, they drifted by a
#: metre and left every bot standing inside the floor.
SPAWN_LIFT_UNITS = avatar.SPAWN_LIFT_UNITS

#: Near/far planes in metres.  A map is tens of thousands of units across, and
#: the default near plane is far too close at this scale.
NEAR_PLANE = 0.2
FAR_PLANE = 4000.0

#: The pack the in-window prompt offers when a Quake 3 map's textures are
#: missing.  Named here rather than looked up by role because it *is* a choice:
#: it is the community's freely-licensed replacement set, and offering it is
#: this viewer's decision rather than a fact about the map.
CORE_TEXTURE_PACK = 'quake3-core'

#: Scene time a capture pins the surface animation to, in seconds.  Not zero:
#: at zero every wave is at a zero crossing and a reference image would show a
#: still surface, which proves nothing about a feature whose whole point is
#: that it moves.  Any fixed value makes the image reproducible; this one puts
#: the common `sin` waves somewhere visible.
CAPTURE_TIME = 0.35

#: Seconds between looks at who is under the crosshair.
#:
#: The answer is a ray cast with every combatant staged into the world around
#: it -- the same work a shot does -- and it was being asked on every frame to
#: keep a name under a reticule.  A tenth of a second is well below the time a
#: player needs to read a name, and far below the reaction the name informs, so
#: nothing about aiming or shooting changes: the *shot* still traces when it is
#: fired.  What is rate-limited is the label.
TARGET_NAME_INTERVAL = 0.1


def build_parser(prog: str = 'twig-bb') -> argparse.ArgumentParser:
    """The viewer's command line."""
    parser = argparse.ArgumentParser(
        prog=prog, description=__doc__.split('Keys::')[0].strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('target', nargs='?',
                        help='a .bsp map, a .pk3/.zip archive, a http(s) URL, '
                             'or pack:mapname (see --list-packs).  With none, '
                             'the start screen offers what is installed')
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
    parser.add_argument('--bots', type=int, default=0, metavar='N',
                        help='how many opponents to play against (default 0)')
    parser.add_argument('--difficulty', default='medium',
                        choices=list(match.DIFFICULTIES),
                        help='how well they play (default medium)')
    parser.add_argument('--frag-limit', type=int, default=15, metavar='N',
                        help='frags that end the match; 0 for none')
    parser.add_argument('--time-limit', type=float, default=10.0,
                        metavar='MINUTES',
                        help='minutes that end the match; 0 for none')
    parser.add_argument('--hud', action=argparse.BooleanOptionalAction,
                        default=None,
                        help='draw the game HUD; on unless capturing, and '
                             '--hud forces it on for a capture too')
    parser.add_argument('--effects', default=effects.FULL,
                        choices=sorted(effects.INTENSITIES),
                        help='how much impact and blood to draw (default full).  '
                             'Presentation only: it cannot change what a shot '
                             'does, so two players may set it differently')
    parser.add_argument('--fullscreen', action=argparse.BooleanOptionalAction,
                        default=True,
                        help='fill the screen (default on; a capture always '
                             'renders at the window size it asked for)')
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
    parser.set_defaults(texture_packs=[CORE_TEXTURE_PACK])
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

    ``SwimMode`` is world-imposed, so it never appears in the walk/fly cycle:
    the map's liquid volumes feed ``platform.submerged`` through
    :func:`update_submerged` and the mode takes over from there.
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
            swimSpeed=SWIM_SPEED_UNITS * SCENE_SCALE,
            turnRate=TURN_RATE, lookRate=LOOK_RATE),
    ]


def update_submerged(nav: Any, volumes: Any) -> None:
    """Tell the navigator whether it is in a liquid.  ``SwimMode`` watches this.

    **A swim starts at the eye and ends at the feet**, and the two readings are
    what makes a pool something a player can get out of again.  Going in, the
    eye is right: the liquid closing over your head is what takes walking away
    from you, and reading the feet would put somebody paddling in the shallows
    into a swim.  Coming out, the eye is a trap: it reaches the surface a
    head's height before the feet do, so ending the swim there drops the body
    back into the water the moment it breaks through, and the feet can never
    rise past that depth.  A pool whose rim stands above its water -- which is
    the ordinary shape of one -- is then impossible to climb out of.

    So the swim holds until the body is clear of the liquid altogether, which
    leaves the swimmer able to lift themselves to the surface and step out over
    a rim.  What the *view* does is a separate question, read from the eye
    where it belongs: see :func:`twig_bb.underwater.update`.

    A platform with no body to ask about -- a plain camera -- is read by its
    eye alone.
    """
    if nav is None:
        return
    if volumes is None:
        nav.submerged = False
        return
    if volumes.contains(nav.camera_position()):
        nav.submerged = True
        return
    feet = getattr(nav, 'feet_position', None)
    nav.submerged = bool(getattr(nav, 'submerged', False)
                         and feet is not None and volumes.contains(feet()))


def apply_mode(nav: Any, mode: Any) -> None:
    """Tell the character controller what a mode change means for it.

    Whether the avatar falls, floats or swims is a property of the *body*
    rather than of the movement it is given, so a mode that only set a
    velocity would fly into the floor or swim through a wall.

    The mode answers rather than a table here, because which body state a mode
    needs is part of what the mode *is*: a list of names in this file would
    have to be kept in step with a set of nodes that a game is free to add to.
    """
    if nav is None or mode is None:
        return
    mode.applyTo(nav)


#: Set ``TWIG_BB_DEBUG_JUMP=1`` to have every jump press report what the capsule
#: thought at the time.  "Space did nothing" is unanswerable without it: the
#: press has to survive the event queue, reach the mode that owns the binding,
#: reach the character, and find the character on its feet, and any of the four
#: failing looks identical from the outside.
DEBUG_JUMP_ENV = 'TWIG_BB_DEBUG_JUMP'


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


def wants_fullscreen(options: argparse.Namespace) -> bool:
    """Whether this run should fill the screen.

    A capture is a picture of the scene at a stated size, so it keeps the
    window whatever the rest of the command line says: a frame read back at
    whatever the display happens to be is not comparable with one read back
    anywhere else.
    """
    return bool(options.fullscreen) and not options.capture


def context_definition(fullscreen: bool = True) -> ContextDefinition:
    """A context definition carrying this viewer's declared modes.

    Full-screen by default, because that is how the game is played; the
    settings screen offers the same field, so a player who wants a window can
    have one without restarting.
    """
    return ContextDefinition(movementModes=movement_modes(),
                             fullscreen=fullscreen)


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
        swimSpeed=SWIM_SPEED_UNITS * SCENE_SCALE,
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
        return avatar.eye_of(spawn.position), yaw_for_angle(spawn.angle)
    low, high = loaded.world.bounds
    centre = (np.asarray(low, dtype='d') + np.asarray(high, dtype='d')) * 0.5
    centre[1] = float(high[1]) - PLAYER_HEIGHT_UNITS * SCENE_SCALE
    return centre, 0.0


@dataclass
class LevelBundle:
    """A whole match built as data, ready to mount on the render thread.

    Decoding a map and staging the match in it touches no GL, so it is done off
    the render thread and its result crosses back as one of these: the map, the
    arena, the drawn figures and the rules, all plain objects. ``loaded`` is None
    for the map-less match the start screen shows before a level is chosen.
    """

    loaded: Any
    arena: Any
    player: Any
    cast: Any
    botGroup: Any
    botBodies: Any
    effects: Any
    flight: Any
    projectileGroup: Any
    projectileBodies: Any
    minds: Any
    rules: Any
    deathCamera: Any


def build_match(config: Any, weapons: Any, loaded: Any) -> LevelBundle:
    """Stage a match in ``loaded`` (map-less when None), touching no GL.

    The whole of what :meth:`TwigContext._buildMatch` used to do inline, lifted
    out so it runs on a worker thread and under test without a window. The player's
    own record *is* the arena's, rather than a second copy: the HUD reads one and
    the rules write one, and two of them would drift the first time a bot landed a
    shot.
    """
    arena = game.start_match(loaded, match.MatchSetup(
        bots=int(config.bots), difficulty=str(config.difficulty),
        fragLimit=int(config.frag_limit),
        timeLimit=float(config.time_limit)), weapons)
    me = arena.combatant(game.PLAYER_ID)
    if me is None:
        raise RuntimeError('the match was started without the player in it')
    # A drawn figure for each bot, made once for the match: a scenegraph rebuilt
    # whenever somebody spawns is one rebuilt during a fight. A figure that will
    # not load leaves that body a capsule and the match carries on.
    cast = characters.Cast([one.id for one in arena.bots()],
                           armoury=characters.Armoury(weapons))
    botGroup, botBodies = game.bot_bodies(arena, cast=cast)
    # Everything in the air, and one instanced model per kind to draw it with,
    # made once: a scenegraph edited every time a rocket is fired is one rebuilt
    # at the rate somebody holds the trigger down.
    flight = projectiles.Projectiles(projectiles.default_table())
    projectileGroup, projectileBodies = game.projectile_bodies(flight.table)
    # Given the same tables the player has, so a bot chooses between exactly the
    # weapons the player can carry and knows what each throws.
    minds = game.place_bots(arena, projectiles=flight.table)
    return LevelBundle(
        loaded=loaded, arena=arena, player=me.player, cast=cast,
        botGroup=botGroup, botBodies=botBodies,
        effects=effects.Effects(arena, intensity=str(config.effects)),
        flight=flight, projectileGroup=projectileGroup,
        projectileBodies=projectileBodies, minds=minds,
        rules=rules.Rules(arena, minds=minds, flight=flight,
                          capabilities=character_capabilities()),
        deathCamera=deathcam.DeathCamera())


def load_level(config: Any, weapons: Any, target: str) -> LevelBundle:
    """Decode the map ``target`` names and stage a match in it. Touches no GL."""
    return build_match(config, weapons, load_map(config, target))


class TwigContext(OverlayMixin, AsyncSceneMixin, BaseContext):
    """The viewer window: a loaded map, a walking camera, and jump pads.

    :class:`~OpenGLContext.ui.overlay.OverlayMixin` comes first so its event
    routing runs before the navigation mix-in's: while a modal panel is up the
    input sampler is not fed at all, which is what stops the player walking on
    while they answer a question.
    """

    config: Any = None
    #: What this game tells a session recording about itself; see
    #: :mod:`twig_bb.telemetry`.  :meth:`OnInit` replaces it with one bound to
    #: this window.  The class's own marks nowhere, so a context assembled
    #: without one -- which is how a match is played out under test -- can mark
    #: as freely as a running game does.
    marks: Any = gamemarks.GameMarks(None)
    _target: Optional[str] = None
    #: The map in play, or None while the start screen is up.
    loaded: Any = None
    #: Who made the map in play and under what terms; see
    #: :mod:`twig_bb.mapnotice`.  None while the start screen is up.
    notice: Optional[mapnotice.MapNotice] = None
    #: The start screen while it is up, so it can be taken down again.
    _menuPanel: Any = None
    #: A download in progress, or None.  Polled once a frame; see
    #: :meth:`_pollDownload`.
    _fetch: Any = None
    _fetchPanel: Any = None
    #: The map's :class:`~twig_bb.collision.MapCollision` once walking has
    #: begun, or None.  What a shot asks for the surface it met.
    _collision: Any = None
    #: The one reader of the match's event stream; see
    #: :class:`~twig_bb.feedback.Presenter`.
    _presenter: Any = None
    #: What plays a tick of the match; see :class:`~twig_bb.rules.Rules`.
    #: It owns the map's hazards, its pickups, the opponents' minds and what
    #: is in the air.
    rules: Any = None
    #: The pickups' bodies, and the group holding them.
    itemGroup: Any = None
    itemBodies: Any = ()
    itemRooms: Any = None
    #: Where the view goes while the player is dead; see
    #: :mod:`twig_bb.deathcam`.
    deathCamera: Any = None
    # Supplied by the interactive runtime base (event + navigation mixins),
    # which the minimal type-check-time Context alias does not expose.
    platform: Any
    movementManager: Any
    addEventHandler: Any
    triggerRedraw: Any
    sg: Any

    def OnInit(self) -> None:                   # pragma: no cover - needs a window
        """Open the window, and either load the named map or offer the menu.

        **A level is something this loads, not something it starts with.**
        Launching with no map is a reasonable thing to do and lands on the
        start screen; everything below that a map is needed for is deferred to
        :meth:`_loadLevel`, which the menu calls when a level is chosen.
        """
        disable_vsync()
        if self.config is None:
            self.config = build_parser().parse_args([self._target or ''])
        # The handover for loading a level off the render thread (see
        # :meth:`_loadLevel`); set up before any level can be chosen.
        self.setupAsyncScene()
        # What this game tells a session recording about itself; see
        # :mod:`twig_bb.telemetry`.  Built first, because everything below it
        # marks and a mark made before there is anything to mark on is the one
        # that would have said which map was being read when it went wrong.
        self.marks = gamemarks.GameMarks(self)
        self.loaded = None
        self._animator = SurfaceAnimator()
        self._started = systemtime.systemTime()
        self.platform.setFrustum(near=NEAR_PLANE, far=FAR_PLANE)
        # The event system holds callbacks weakly by design, so a binding built
        # from a bare closure is collected the moment the binding call returns
        # and the key silently stops working.  Every handler below is a bound
        # method of this long-lived context, which is what keeps them alive.
        self._walking = False
        self._free_manager = getattr(self, 'movementManager', None)
        self._nav: Optional[PhysicsViewPlatform] = None
        #: The unsighted field of view, in radians, read from the platform on
        #: the first frame; see :meth:`_sight`.
        self._fov: Optional[float] = None
        self._pushes: Optional[jumppads.PushSystem] = None
        self._liquids: Any = None
        self._clock = FrameClock()
        self._clock.reset(systemtime.systemTime())
        # The event system holds its callbacks weakly, so the wheel handlers
        # are kept here rather than being collected as soon as they are bound.
        self._wheelHandlers: List[Any] = []
        self._capture = None
        if self.config.capture:
            self._capture = SettleCapture(self.config.capture,
                                          delay=self.config.capture_delay,
                                          min_frames=self.config.frames)
        # Before the scene: the weapon in the player's hands is part of it, so
        # what is held has to be settled before the children are gathered.
        self._buildLoadout()
        # What the last launch chose, offered again first: it is what a
        # returning player wants, and a first launch simply gets the defaults.
        self.setup = match.recall()
        self.sg = SceneGraph(children=self._scene_children())
        # After the capture, because building the HUD asks for a redraw and a
        # frame drawn before the capture exists has nothing to report to.
        self._startGame()
        self.addEventHandler('keypress', name='g', function=self._toggle_walk)
        self.bindScreenKeys(self)
        if self._target:
            self._loadLevel(self._target)
        else:
            self.showMenu()

    def _loadLevel(self, target: str) -> None:  # pragma: no cover - needs a window
        """Load a map and start playing in it, off the render thread.

        Called from ``OnInit`` when a map was named on the command line, and from
        the start screen when one is chosen. Decoding the map and staging the
        match -- seconds of work on a big level, and touching no GL -- runs on a
        worker (:func:`load_level`) so the window keeps drawing; the result is
        mounted by :meth:`applyLoadedScene` on the render thread. A capture has no
        loop to keep alive and needs the very frame it is about to grab, so it
        loads in step instead.
        """
        self._target = target
        self.marks.loading(target)
        if self.config.capture:
            self._applyLevel(load_level(self.config, self.weapons, target))
            return
        self.requestScene(lambda: load_level(self.config, self.weapons, target),
                          label=target)

    def applyLoadedScene(self, bundle: LevelBundle) -> None:  # pragma: no cover - GL
        """Render thread: mount a level the worker finished decoding."""
        self._applyLevel(bundle)

    def applyFailedLoad(self, error: Optional[BaseException]) -> None:  # pragma: no cover - GL
        """Render thread: a level would not load.  Say so and stay on the menu."""
        log.error('could not load the level %s: %s', self._target, error)
        self.marks.failed(self._target or '', error)
        self.showMenu()

    def _applyLevel(self, bundle: LevelBundle) -> None:  # pragma: no cover - needs a window
        """Install a freshly built level and start playing in it.

        The render-thread half of :meth:`_loadLevel`: everything from here down
        builds the scenegraph or touches GL, so it runs where a worker cannot.
        """
        self.loaded = bundle.loaded
        # Established with the map rather than when the acknowledgements are
        # opened: it reads the content roots, and by then a reload for missing
        # textures may have added more of them.
        self.notice = mapnotice.for_map(self.loaded)
        # Rebuilt with the map: a surface has to be told it deforms before its
        # vertex buffers exist, since that is what decides whether its
        # texture-coordinate buffer is dynamic.
        self._animator = SurfaceAnimator()
        self._started = systemtime.systemTime()
        self._installMatch(bundle)
        # What the map left lying about.  Built with the *map* rather than with
        # the scene, so that reloading a map's textures -- which rebuilds the
        # scene -- does not put every collected item back on the floor, for the
        # same reason it does not restore the player's loadout.
        self.rules.pickups = itemsmod.Pickups(self.loaded.pickups())
        # Marked here rather than at the end of this method: everything below
        # is the level being *entered*, and a reader wants the line that says
        # which level it is above the ones that say what happened in it.
        self.marks.loaded(self.loaded, self.arena,
                          title=str(getattr(self.notice, 'title', '') or ''))
        self.sg = SceneGraph(children=self._scene_children())
        if self.config.physics:
            # Walk mode also decides where the camera starts, so a capture runs
            # it too: a map's spawn point is a far better view of it than the
            # scene origin, which is as likely as not to be inside a wall.
            self._set_walking(True)
        self._report()
        self._creditMap()
        if not self.config.capture:
            # A capture has nobody to answer, so it never asks.
            self._offer_core_textures()
        self.triggerRedraw(1)

    # -- scene -----------------------------------------------------------
    def _scene_children(self) -> List[Any]:     # pragma: no cover - needs a window
        children: List[Any] = [_backdrop()]
        if self.loaded is None:
            # No level yet: the backdrop and nothing else, which is what the
            # start screen is drawn over.  A menu over an empty world is a
            # menu; a menu over a half-built one is a bug waiting to be found.
            return children
        children.append(self.loaded.scene(self._animator))
        # The light the map baked for everything that is not the map: a
        # combatant, a pickup and a rocket all carry lightmap coordinates for
        # nothing, so without this they are black shapes in a lit room.  A node
        # in the scene rather than a call anywhere, because the render pass is
        # what samples it, once per object per frame.
        grid = self.loaded.lightGrid()
        if grid is not None:
            children.append(grid)
        # The map's own ambience.  Nothing has to drive it: the render pass
        # collects audible nodes while it gathers the frame and the camera is
        # the listener, so putting the emitters in the scene is the whole of
        # the wiring.  A map with no speakers, or one whose sounds were never
        # fetched, contributes an empty group and costs nothing.
        self.speakers = self.loaded.speakers()
        children.append(self.speakers)
        # One fog node, bound for the life of the map and switched on by its
        # own fields when the camera goes under.  In the scene rather than on
        # the context because that is what the render pass looks for, and it
        # means an authored map could carry its own.
        self.fog = underwater.liquid_fog()
        children.append(self.fog)
        # The opponents.  Capsules until §5's art lands, and deliberately so:
        # fighting had to be buildable before there was anything to look at.
        children.append(self.botGroup)
        # A body per pickup, in the order `rules.pickups` holds them: this is
        # gathered again whenever the scene is rebuilt, and what has been
        # *taken* is the rules' business rather than the scene's.
        self.itemGroup, self.itemBodies = game.item_bodies(self.rules.pickups)
        # Which room each pickup stands in, so the ones behind walls are not
        # drawn: the frustum cannot reject them, and the map already knows.
        self.itemRooms = game.ItemRooms(self.loaded.visibility(),
                                        self.rules.pickups)
        self.rules.visibility = self.loaded.visibility()
        children.append(self.itemGroup)
        # One emitter per kind of impact, never moved: the bursts arrive at
        # their own places through `burst_at`, so this group is built once and
        # a firefight edits nothing in the scene.
        children.append(self.effects.group)
        children.append(self.projectileGroup)
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
            # substitution does not happen and the map's own baked lighting --
            # the lightmaps on its surfaces, the grid on everything else --
            # stands alone.
            children.append(DirectionalLight(direction=(0, -1, 0), intensity=0.0))
        return children

    def viewpointAttachment(self) -> Any:       # pragma: no cover - needs a window
        """The transform everything held in the player's hands hangs from.

        Carries the weapon, and deliberately no light: a fill light riding the
        camera brightens the *map* more than the weapon, so the weapon carries
        a small emissive floor in its own material instead.  See
        :func:`twig_bb.firstperson.view_rig`.
        """
        if getattr(self, 'camera', None) is None:
            self.camera = view_rig(self.hand)
        return self.camera

    # -- the screens around the outside ----------------------------------
    def OnEscape(self, event: Any = None) -> None:
        """Escape puts the menu up rather than ending the match.

        It was bound straight to the context's forcible quit, so a key pressed
        to close a screen, dismiss a notice or back out of anything at all
        ended the session -- with no confirmation and nothing to undo it.  From
        here Resume and Quit are both one click away.
        """
        self.showMenu(event)

    def showMenu(self, event: Any = None) -> None:
        """Put the start screen up: Play, content, settings, credits, quit.

        Modal, so nothing reaches the world behind it.  **One at a time**: a
        second menu pushed over the first would leave two, and dismissing the
        top one would reveal a stale copy of itself.

        Mid-match it also offers Resume, and Escape leaves it, since there is
        then something behind it worth going back to.
        """
        self._closeMenu()
        playing = getattr(self, 'loaded', None) is not None
        self._menuPanel = menu.main_menu(
            on_play=self._playScreen, on_content=self._contentScreen,
            on_settings=lambda: self._settings(None),
            on_credits=self._creditsScreen, on_quit=self.OnQuit,
            on_resume=self._closeMenu if playing else None,
            subtitle=self._menuSubtitle())
        self.pushOverlay(self._menuPanel)
        self.marks.screen('start')

    def _closeMenu(self) -> None:               # pragma: no cover - GL
        """Take the start screen down, if it is up.

        Every screen the menu opens **replaces** it rather than stacking over
        it, and starting a match closes it outright.  Left up, it is a modal
        panel over a level that has loaded and is running: nothing reaches the
        world, and pressing Start looks like it did nothing at all.
        """
        panel = self._menuPanel
        self._menuPanel = None
        if panel is not None:
            panel.close(True)

    def _menuSubtitle(self) -> str:             # pragma: no cover - GL
        """A line under the title: what is loaded, or what is missing."""
        if self.loaded is not None:
            return 'Playing %s' % (self.loaded.name,)
        if not match.levels_available(self.config.cache_dir):
            return ('No levels are installed yet. Choose "Get content" to '
                    'download some.')
        return ''

    def _playScreen(self) -> None:              # pragma: no cover - GL
        """Choose a level, the opponents and the rules, then start."""
        self._closeMenu()
        self.pushOverlay(menu.play_screen(
            self.setup, match.levels_available(self.config.cache_dir),
            on_start=self._startChosen, on_cancel=self.showMenu))

    def _startChosen(self, setup: Any) -> None:  # pragma: no cover - GL
        """Begin the match the play screen settled on."""
        match.save(setup)
        self.config.bots = int(setup.bots)
        self.config.difficulty = str(setup.difficulty)
        self.config.frag_limit = int(setup.fragLimit)
        self.config.time_limit = float(setup.timeLimit)
        if not setup.level:
            # Nothing to play in.  Back to the menu rather than into a black
            # room: the subtitle there says what is missing.
            self.showMenu()
            return
        self._loadLevel(str(setup.level))

    def _contentScreen(self) -> None:           # pragma: no cover - GL
        """Offer the packs that are not yet on disk, with their size and terms."""
        self._closeMenu()
        wanted = [pack for pack in download.ASSET_PACKS
                  if download.pack_root(pack, self.config.cache_dir) is None]
        if not wanted:
            self.pushOverlay(dialogs.message(
                'Everything in the catalogue is already downloaded.',
                title='Content', on_close=lambda panel: self.showMenu()))
            return
        self.pushOverlay(menu.download_screen(
            wanted, on_start=lambda: self._startDownload(wanted),
            on_cancel=self.showMenu))

    def _startDownload(self, packs: Any) -> None:   # pragma: no cover - GL
        """Fetch the packs on a worker, and watch it from the frame loop."""
        self._fetch = fetcher.FetchJob(packs, cache_dir=self.config.cache_dir,
                                       on_progress=lambda: self.triggerRedraw(1))
        self._fetch.start()
        self.marks.downloading(packs)
        self._fetchPanel = menu.progress_screen(
            self._fetch, on_cancel=lambda: None)
        self.pushOverlay(self._fetchPanel)

    def _pollDownload(self) -> None:            # pragma: no cover - GL
        """Publish what the download has managed, once a frame.

        The only place the worker is read, which is what lets everything the
        screen touches be touched without a lock.
        """
        job = getattr(self, '_fetch', None)
        if job is None:
            return
        job.poll()
        menu.refresh_progress(getattr(self, '_fetchPanel', None), job)
        if not job.finished:
            return
        self._fetch = None
        self.marks.downloaded(job)
        self.config.content = (list(self.config.content)
                               + [root for pack_root in job.roots
                                  for root in download.content_roots(pack_root)])
        panel = getattr(self, '_fetchPanel', None)
        if panel is not None:
            panel.close(True)
        self._fetchPanel = None
        self.showMenu()

    def _creditsScreen(self) -> None:           # pragma: no cover - GL
        """What this is built from and what it is playing."""
        self._closeMenu()
        self.pushOverlay(notices.screen(on_close=lambda panel: self.showMenu(),
                                        current=self.notice))

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
        self._started = systemtime.systemTime()
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
        # The starting loadout: one weapon and what it holds.  Everything else
        # is picked up off the level, which is what makes a map a circuit
        # rather than a room -- see `twig_bb.items`.
        self.player = PlayerState.starting(self.weapons)
        self.weaponBindings = controls.WeaponBindings()
        self.hand = WeaponHand(self.weapons)
        self.hand.select(self.weapons.by_key(self.player.selected))
        self._buildMatch()

    def _buildMatch(self) -> None:              # pragma: no cover - GL
        """Build the match this launch is playing and install it.

        The building is :func:`build_match`, lifted out so it runs under test and
        off the render thread; installing it is :meth:`_installMatch`. Kept as one
        call because the map-less start-screen match is built here synchronously,
        where a worker would only add latency to a build that is already cheap.
        """
        self._installMatch(build_match(self.config, self.weapons, self.loaded))

    def _installMatch(self, bundle: LevelBundle) -> None:   # pragma: no cover - GL
        """Point the context at a freshly built match. Render thread only.

        Everything here has just replaced what came before, so the presenter is
        rebound **every time**: one left pointing at the previous build goes on
        drawing a match nobody is playing, into emitters no longer in the scene.
        The rules are given the map's spawns and hazards later, by
        :meth:`_start_physics`.
        """
        self.arena = bundle.arena
        self.player = bundle.player
        self.cast = bundle.cast
        self.botGroup, self.botBodies = bundle.botGroup, bundle.botBodies
        self.effects = bundle.effects
        self.flight = bundle.flight
        self.projectileGroup = bundle.projectileGroup
        self.projectileBodies = bundle.projectileBodies
        self.minds = bundle.minds
        self.rules = bundle.rules
        self.deathCamera = bundle.deathCamera
        self._bindPresenter()

    def _bindPresenter(self) -> None:           # pragma: no cover - GL
        """Point the one reader of the event stream at what is being played now.

        Called from :meth:`_buildMatch` and again from :meth:`_startGame`: the
        match is built before there is a HUD to draw it on -- the start screen
        needs one -- and built again when a level is chosen, so neither moment
        alone has all the pieces.  Rebinding is cheap and idempotent, and the
        alternative is the failure this exists to stop: a fight that emits
        perfectly into objects nothing is drawing.
        """
        self._presenter = feedback.Presenter(
            self.arena, hud=getattr(self, 'hud', None),
            sounds=combatsound.CombatSound(self.arena, weapons=self.weapons,
                                           engine=self._audioEngine),
            effects=self.effects)

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
        self._bindPresenter()
        wanted = self.config.hud
        self.hud.visible = (self.config.capture is None if wanted is None
                            else bool(wanted))
        self.addHUDLayer(self.hud)
        twigdebug.install(self)
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
        # The scoreboard, on a *held* key rather than a toggle: it covers the
        # middle of the screen, and a board somebody left up by accident is a
        # board they get shot behind.
        for state, handler in ((1, self._showScores), (0, self._hideScores)):
            self.addEventHandler('keyboard', name=SCOREBOARD_KEY, state=state,
                                 function=handler)

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

        **A corpse has no gun.**  While the player is dead the trigger is a
        request to come back, not a shot, so it never reaches the weapon
        accounting: routing it there made an empty rifle answer "OUT OF
        CARTRIDGES"
        and swallow the respawn, and a loaded one spend a round every frame the
        button was held waiting to return.  The dead-check that actually ends
        the death is :meth:`_shoot`; this only keeps the accounting from
        running ahead of it.
        """
        if firing:
            me = self.arena.combatant(game.PLAYER_ID)
            if me is not None and not me.alive:
                self.rules.ask_to_respawn(game.PLAYER_ID)
                self.marks.asked_to_respawn(game.PLAYER_ID)
                firing = False
        events = controls.apply_commands(commands, firing, self.player,
                                         self.weapons, hudclock())
        for event in events:
            if event.kind == 'fire':
                self._shoot()
            if event.text:
                self.hud.post(event.text)
        # After they have been applied, so the mark says what is in hand now
        # rather than what was in hand a moment ago.
        self.marks.commands(events, weapon=str(self.player.selected))
        self.triggerRedraw(1)

    def _aim(self) -> Tuple[np.ndarray, np.ndarray]:
        """Where a shot leaves from, and along what.

        **From the navigator**, because that is the only thing that knows
        where the player is looking.  The view platform the renderer draws
        from does not carry the look at all -- its quaternion stays where it
        started -- so a shot aimed from it goes the same way whichever way the
        player turns, which reads as the world spinning around a fixed gun:
        turn left and the impact pans right, look down and the shot goes up.

        The gaze rule is :func:`gaze`, whose agreement with ``_world_dir`` and
        so with the map-angle convention is a test.

        Before walking has begun there is no navigator and so no camera to aim
        from: the answer is the scene origin, looking straight ahead.  Nothing
        fires then -- a shot needs the physics world the navigator holds -- and
        the only other reader is the damage indicator, which has no fight to
        point at yet either.
        """
        nav = self._nav
        if nav is None:
            return (np.zeros(3), np.array([0.0, 0.0, -1.0]))
        return (np.asarray(nav.camera_position()[:3], dtype='d'), gaze(nav))

    def _shoot(self) -> None:                   # pragma: no cover - GL
        """Send the player's shot down the middle of the view.

        From the camera rather than from the weapon model's muzzle: what a
        player aims with is the reticule, and a trace that left the barrel
        would miss what the crosshair was on -- which reads as the game
        cheating rather than as realism.
        """
        world = self.physicsWorld()
        weapon = self.weapons.by_key(self.player.selected)
        me = self.arena.combatant(game.PLAYER_ID)
        if me is not None and not me.alive:
            # **The trigger is what ends a death.**  A countdown that brought
            # a player back while they were reading the scoreboard would put
            # them in a corridor they were not looking at, so the timer is
            # only the shortest a death may be.
            self.rules.ask_to_respawn(game.PLAYER_ID)
            self.marks.asked_to_respawn(game.PLAYER_ID)
            return
        if world is None or weapon is None or me is None:
            return
        origin, direction = self._aim()
        # What it landed on is not read here: the shot emits events, and the
        # one loop in `_presentMatch` answers them for the player's shots and
        # a bot's alike.  `shoot` rather than `combat.fire`, because whether
        # this weapon traces or throws is the weapon's business and not this
        # method's.
        game.shoot(world, self.arena, game.PLAYER_ID, weapon,
                   origin=origin, direction=direction,
                   spread=weapon.spread_at(
                       self.player.spread_fraction(hudclock())),
                   surfaces=self._collision, flight=self.flight)
        # The one piece of feedback that comes from the thing in the player's
        # hands rather than from the world, so it arrives even for a shot into
        # the sky that meets nothing at all.
        self.hand.fired(hudclock())

    def _creditMap(self) -> None:
        """Say which map this is, and under whose terms, as it starts.

        On the screen the player is looking at rather than only in the
        acknowledgements: the attribution these levels are fetched under asks
        to travel with the work, and a screen nobody opens does not carry it.
        Two lines at most, through the same queue as every other message, so
        it fades on its own clock and never becomes furniture.
        """
        notice = getattr(self, 'notice', None)
        if notice is None:
            return
        # Backwards, because the queue shows the newest line at the top: posted
        # in reading order the credit would arrive upside down.
        for line in reversed(notice.credit_lines()):
            self.hud.post(line)

    def _presentMatch(self, events: Any) -> None:  # pragma: no cover - GL
        """Turn what the match just said into what the player sees.

        The single loop §11 asks for: the rules emit and this consumes, so a
        bot's shot and the player's own reach the screen by the same road, and
        the messages, the hit mark, the damage indicator and the death notice
        are four readings of one stream rather than four places that reach
        into the rules.
        """
        for line in game.messages(events, self.arena):
            self.hud.post(line)
        camera, forward = self._aim()
        self._presenter.show(events, camera=camera, forward=forward,
                             now=hudclock(),
                             platform=self.getViewPlatform())

    def _audioEngine(self) -> Any:              # pragma: no cover - GL
        """This window's audio engine, opened on the first sound it makes.

        Asked for lazily rather than held, because asking is what opens a
        device and starts an audio thread: a capture run and a map walked
        through in silence should pay for neither.
        """
        from OpenGLContext.audio import scene as audioscene
        return audioscene.engine_for(self)

    def _sampleWeapons(self) -> None:           # pragma: no cover - GL
        """Read the weapon commands out of this frame's input."""
        state = self.getInputState()
        commands = self.weaponBindings.triggered(state)
        firing = self.weaponBindings.firing(state)
        if commands or firing:
            self._runCommands(commands, firing)
        self._sight(self.weaponBindings.zooming(state))

    def _sight(self, zooming: bool) -> None:    # pragma: no cover - GL
        """Set the frustum to whatever the player is looking through.

        Written every frame from what is *currently* in hand rather than when
        the button is pressed, so a weapon switch, a death and an empty
        magazine all give the wide view back without any of them having to
        know that a scope exists.  The frustum is the only thing that changes:
        a zoom that also slowed the mouse would be two settings pretending to
        be one, and the reticule follows on its own because it is drawn from
        the same field of view (see :func:`view_fov`).
        """
        platform = self.getViewPlatform()
        if platform is None:
            return
        if self._fov is None:
            # Whatever the view was built with, taken before anything here has
            # narrowed it, so a settings screen that widens the view later is
            # what a rifle comes back to.
            self._fov = view_fov(platform)
        wanted = weapontable.field_of_view(
            self.weapons.by_key(self.player.selected), zooming, self._fov)
        if abs(view_fov(platform) - wanted) > 1e-6:
            platform.setFrustum(fieldOfView=wanted)
            self.triggerRedraw(1)

    def physicsWorld(self) -> Any:
        """The physics world once walking has begun, else None.

        Through the navigator's **character**, which is what actually holds
        it: a view platform owns a capsule and the capsule owns the world.
        Asking the platform directly answers None, and nothing complains —
        every caller reads None as "walking has not started yet", so the bots
        never think, no shot is ever traced and the developer overlay quietly
        drops its Physics section.

        A method rather than an attribute because the world is replaced
        whenever a map is, and a provider holding the first would report on it
        for ever.
        """
        nav = self._nav
        if nav is None:
            return None
        character = getattr(nav, 'character', None)
        return getattr(character, 'world', None)

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

    #: When the crosshair's name was last looked up, and what it said.  See
    #: :data:`TARGET_NAME_INTERVAL`.
    _namedAt = -1e9
    _named = ''

    def renderShaderOverlay(self, pass_: Any) -> None:   # pragma: no cover - GL
        """Bring the HUD up to date, then let the layers draw themselves.

        Reading the player's state here rather than when it changes is what
        keeps the HUD honest about the things that move on their own -- the
        cone of fire closing, a message fading -- without anything having to
        remember to invalidate it.
        """
        self._updateHUD()
        super(TwigContext, self).renderShaderOverlay(pass_)

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
        # Posed from the same clock the HUD reads, and here rather than when
        # the shot was taken: a kick that decays has to be written every frame
        # or it stops wherever the last shot left it.
        hand.settle(hudclock())
        aim_at_camera(self.viewpointAttachment(), self.getViewPlatform())

    def _stepMatch(self, dt: float) -> None:    # pragma: no cover - GL
        """Advance the match one frame, and show what came of it.

        Two halves, and the line between them is [§11](../PROJECT-PLAN.md)'s
        seam: :class:`~twig_bb.rules.Rules` plays the tick and this shows
        it.  Everything above the seam is testable without a window, which is
        the whole reason it is not written out here -- nothing in this loop can
        be reached by a test, so a rule living in it is a rule only a person
        playing the game can check.

        The player's position is *published* rather than read by the rules,
        which is what keeps the arena free of the camera: everything else in
        it moves because a command said so.
        """
        world = self.physicsWorld()
        if world is None:
            return
        nav = self._nav
        if nav is not None:
            self.rules.publish(game.PLAYER_ID, nav.camera_position())
        tick = self.rules.advance(
            world, dt, self.weapons.by_key(self.player.selected),
            surfaces=self._collision)
        # The second reader of the stream: what the match did, as marks on a
        # session recording.  See :mod:`twig_bb.telemetry`.
        self.marks.events(tick.events)
        self.marks.respawned(tick.respawned)
        self.marks.minds(self.minds)
        self._cameBack(tick.respawned)
        self._watchDeath(tick.events, dt)
        self._shovePlayer()
        game.move_bodies(self.arena, self.botBodies, cast=self.cast,
                         walking=self.rules.walking, dt=dt, mode=self,
                         rooms=self.rules.rooms)
        game.move_items(self.rules.pickups, self.itemBodies, hudclock(),
                        near=self._nav.camera_position() if self._nav else None,
                        rooms=getattr(self, 'itemRooms', None))
        game.move_projectiles(self.flight, self.projectileBodies)
        flying = len(self.flight)
        self.effects.trail(self.flight.position[:flying], dt,
                           velocities=self.flight.velocity[:flying])
        self._presentMatch(tick.events)

    def _watchDeath(self, events: Any, dt: float) -> None:  # pragma: no cover - GL
        """Take the view away while the player is dead, and give it back.

        The camera is the piece of a death that had no owner: the view stayed
        exactly where it was killed, still steered by the mouse, which reads
        as the death *notice* being wrong rather than as a death.  See
        :mod:`twig_bb.deathcam`.
        """
        for event in events:
            if isinstance(event, arena.Death) and event.target == game.PLAYER_ID:
                me = self.arena.combatant(game.PLAYER_ID)
                killer = self.arena.combatant(event.by)
                nav = self._nav
                self.deathCamera.begin(
                    nav.camera_position() if nav is not None else np.zeros(3),
                    me.position if me is not None else np.zeros(3),
                    yaw=float(getattr(nav, 'yaw', 0.0)),
                    killer=None if killer is None or killer is me
                    else np.asarray(killer.position, dtype='d') + game.EYE_OFFSET)
        self.deathCamera.advance(dt)

    def _cameBack(self, respawned: Any) -> None:  # pragma: no cover - GL
        """Move the camera to wherever a respawn has just put the player.

        **The camera, not merely the record.**  The player's body is published
        from the camera every tick, so a respawn the camera is not told about
        is overwritten on the very next frame and puts them back exactly where
        they were killed -- which reads as being fragged doing nothing at all.
        """
        feet = respawned.get(game.PLAYER_ID)
        if feet is None:
            return
        self.deathCamera.end()
        if self._nav is not None:
            self._nav.bind_eye(tuple(feet + game.EYE_OFFSET))

    def _shovePlayer(self) -> None:
        """Give the player whatever a burst pushed them with.

        **Through the character controller's own impulse**, which is what a
        jump pad uses, so a rocket at the feet and a pad in the floor throw a
        player by the same machinery -- and a rocket jump is therefore as
        reliable as a jump pad is.

        Taken from the rules and spent here rather than applied by them: the
        arena says how hard somebody was shoved and knows nothing about a
        capsule, and this is the only thing in the game that owns one.
        """
        push = blast.spend(self.arena, game.PLAYER_ID)
        if push is not None and self._nav is not None:
            self._nav.apply_impulse(push)

    def _updateHUD(self) -> None:               # pragma: no cover - GL
        hud = getattr(self, 'hud', None)
        if hud is None or not hud.visible:
            return
        platform = self.getViewPlatform()
        hud.update(self.player, now=hudclock(), viewport=self.getViewPort(),
                   field_of_view=view_fov(platform))
        me = self.arena.combatant(game.PLAYER_ID)
        if me is not None:
            # From the match rather than from the player's own record: frags
            # are something the *arena* keeps, and a second copy on the player
            # would be a second answer to one question.
            hud.score(me.frags, limit=int(self.arena.fragLimit))
        if self.deathCamera is not None:
            hud.dying(self.deathCamera.wash())
        hud.looking_at(self._namedTarget())

    def _namedTarget(self) -> str:              # pragma: no cover - GL
        """Whoever is under the crosshair, looked up again only now and then.

        :meth:`_targetName` is the *answer* and is unchanged; this is how often
        it is asked.  It is a ray cast with the combatants staged into the world
        around it, which is the same work a shot does -- and it was being done
        on every frame to keep a name under a reticule.  A tenth of a second is
        far below what a player can read a name in, and the name still comes
        from the trace a shot would take rather than from a cheaper rule.
        """
        now = hudclock()
        if now - self._namedAt >= TARGET_NAME_INTERVAL:
            self._namedAt = now
            self._named = self._targetName()
        return self._named

    def _targetName(self) -> str:               # pragma: no cover - GL
        """Whoever is under the crosshair right now, or ''.

        Through the same trace a shot takes, so the name is the one a shot
        would give: a name over somebody a shot would miss is worse than no
        name at all, and it is a wall that answers nobody rather than this
        having a rule of its own about cover.
        """
        world = self.physicsWorld()
        me = self.arena.combatant(game.PLAYER_ID)
        if world is None or me is None or not me.alive:
            return ''
        origin, direction = self._aim()
        found = self.arena.combatant(
            combat.who_is_at(world, self.arena, game.PLAYER_ID,
                             origin, direction))
        return '' if found is None else str(found.name)

    def _showScores(self, event: Any = None) -> None:   # pragma: no cover - key
        """Put the whole board up while the key is held."""
        hud = getattr(self, 'hud', None)
        if hud is not None:
            hud.scoreboard(game.scoreboard_lines(self.arena))
            self.triggerRedraw(1)

    def _hideScores(self, event: Any = None) -> None:   # pragma: no cover - key
        """Take it down again when the key is let go."""
        hud = getattr(self, 'hud', None)
        if hud is not None:
            hud.hide_scoreboard()
            self.triggerRedraw(1)

    def _settings(self, event: Any) -> None:    # pragma: no cover - GL
        """Open the rendering settings over the map (F10).

        The screen is generated from ``ContextDefinition``'s own fields, so a
        map that runs badly can trade shadows or environment lighting away
        without a restart.
        """
        settings.open_settings(self)

    def _bindings(self, event: Any) -> None:    # pragma: no cover - GL
        """Open the key-binding page (F6): movement, and the weapon commands.

        One page for both, through :class:`~twig_bb.controls.Controls`,
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
        # The terms alongside the geometry, for a run with no window to read
        # and for whoever is checking what a recording may be published under.
        if self.notice is not None:
            sys.stdout.write('  %s\n' % (self.notice.summary,))
            if self.notice.licence:
                sys.stdout.write('  %s\n' % (self.notice.licence,))
        sys.stdout.write('  %s\n' % (jumppads.describe(loaded.push_volumes()),))
        unscripted = loaded.unscripted_surfaces()
        if unscripted:
            # Not an error: the name is used as a texture path and the surface
            # draws.  Said out loud because the *animation* the script
            # described goes with it, so a still pool of lava otherwise reads
            # as a broken animator rather than as content nobody has.
            sys.stdout.write(
                '  %d surfaces have no material script and so do not animate '
                '(e.g. %s)\n' % (len(unscripted), unscripted[0]))
        pickups = self.rules.pickups
        if pickups is not None:
            sys.stdout.write('  %d pickups placed\n' % (len(pickups),))
        missing = loaded.unplaceable_pickups()
        if missing:
            # Also not an error (`SPEC-Q3ENTITIES §3.2.4`: the classnames are
            # not a closed set).  Said out loud because a level whose whole
            # weapon circuit is content this game has nothing for plays
            # exactly like a reader that failed to find any.
            worst = max(missing.items(), key=lambda pair: pair[1])
            sys.stdout.write(
                '  %d pickups are of kinds this game has nothing for '
                '(e.g. %d x %s)\n'
                % (sum(missing.values()), worst[1], worst[0]))
        sys.stdout.write("  'g' toggles walk / free-fly, 'f' flies, 'm' cycles "
                         "movement mode, space jumps\n")
        sys.stdout.write("  1-5 choose a weapon, the left mouse button fires; alt+f shows the "
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
        self.marks.walking(walking, mode=str(getattr(
            getattr(self.contextDefinition, 'movementMode', None), 'name', '')))
        self.triggerRedraw(1)
        return True

    def _start_physics(self) -> bool:           # pragma: no cover - GL
        built = collision.from_map(self.loaded)
        if built is None:
            sys.stdout.write('no solid geometry to walk on; staying in free-fly\n')
            return False
        # Kept whole rather than unpacked: a shot asks it what the level is
        # made of where the trace landed, and the mesh and the surface index
        # that answers that must never be able to describe different maps.
        self._collision = built
        eye, yaw = choose_spawn(self.loaded, self.config.spawn)
        gravity = self.loaded.gravity * SCENE_SCALE
        self._nav = PhysicsViewPlatform(built.world, character_capabilities(),
                                        yaw=yaw, gravity=gravity)
        self._nav.bind_eye(tuple(eye))
        self._pushes = jumppads.PushSystem(self.loaded.push_volumes(gravity))
        self._liquids = self.loaded.liquid_volumes()
        # What only a loaded map can give the rules.  Slime and lava stop
        # being scenery here -- the volumes are the same ones the swimming
        # uses, so what you can swim in is what can kill you -- and so does
        # the space below the level, where a fall off the edge of a map now
        # ends in a death rather than in a camera that never stops.
        self.rules.spawns = [avatar.feet_of(spawn.position)
                             for spawn in self.loaded.spawn_points()]
        self.rules.harm = liquids.LiquidHarm(self._liquids)
        self.rules.floor = falling.KillFloor.under(self.loaded)
        self.rules.gravity = gravity
        if os.environ.get(DEBUG_JUMP_ENV):
            watch_jumps(self._nav)
        self._nav.apply(self)
        # A map load is seconds the player did not experience as a stall, so
        # the clock starts here rather than carrying that gap into the first
        # frame of play as a clamped step and a debt.
        self._clock.reset(systemtime.systemTime())
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
        self.marks.movement(wanted)

    def _cycle_mode(self, event: Any = None) -> None:   # pragma: no cover - key
        navigation = self.getNavigation()
        if navigation is not None:
            navigation.cycle()
            self.marks.movement(str(getattr(getattr(
                self.contextDefinition, 'movementMode', None), 'name', '')))

    # -- frame -----------------------------------------------------------
    def OnIdle(self, *args: Any) -> int:        # pragma: no cover - needs a window
        # A download runs on a worker and is *published* here, once a frame.
        self._pollDownload()
        # So does a level load: the worker decodes it, and this is where the
        # finished level crosses back to be mounted on the render thread.
        if self.pollPendingScene():
            return 1
        if self.loaded is None:
            # On the start screen: nothing to animate and nobody to walk, so
            # the loop should go quiet -- a static menu that redrew sixty times
            # a second would spin a laptop's fans for nothing.
            if getattr(self, '_fetch', None) is not None:
                return 1                        # a bar is moving
            if self._capture is not None:
                # A capture is settled by *drawn frames*, and with nothing
                # asking for one it would wait for ever.
                self.triggerRedraw(1)
                return 1
            return 0
        # Surfaces animate whether or not the player is walking: a conveyor belt
        # and a pool of lava do not stop because nobody is moving.
        with self.tracePhase('animate'):
            animated = self._animate()
        # Before the walking check: a weapon can be chosen from a free-flying
        # camera, and a player who cannot switch weapons until they land would
        # rightly call that a bug.
        with self.tracePhase('weapons'):
            self._sampleWeapons()
        if not self._walking or self._nav is None:
            if self._capture is not None:
                # A capture waits for a settled frame, and only a redraw makes
                # one; with nothing else driving the loop it would wait forever.
                self.triggerRedraw(1)
                return 1
            return 1 if animated else 0
        dt = self._clock.tick(systemtime.systemTime())
        # The game update is subdivided because it is *all* of `OnIdle`, and
        # `OnIdle` is where this game's frame time goes -- the loop trace can
        # only say "idle" until something in here says which part of it.  The
        # phases nest inside the backend's own, so they divide `idle` rather
        # than adding to it; see `OpenGLContext.looptrace`.
        with self.tracePhase('liquids'):
            update_submerged(self._nav, self._liquids)
            # Fog the view and muffle the mix to whatever the camera is inside.
            # Before the navigation update so the picture and the movement agree
            # about the same frame rather than being one apart.
            underwater.update(self, self._liquids, self._nav.camera_position())
        with self.tracePhase('navigation'):
            self.updateNavigation(dt)
            apply_mode(self._nav,
                       getattr(self.contextDefinition, 'movementMode', None))
        with self.tracePhase('character'):
            self._nav.update(dt)
            self._apply_pushes(dt)
        with self.tracePhase('match'):
            self._stepMatch(dt)
        if self.config.headlight:
            self.headlight.location = self._nav.camera_position()
        # **The death camera wins.**  While the player is dead the navigator
        # goes on being driven -- the keys still arrive, the capsule still
        # falls -- and what changes is who gets to say where the *view* is.
        # Letting the navigator write it anyway is what left a corpse steering
        # itself around the level.
        if self.deathCamera is not None and self.deathCamera.watching:
            self.deathCamera.apply(self.platform)
        else:
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
               else systemtime.systemTime() - self._started)
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

    def presentFrame(self) -> Any:              # pragma: no cover - needs a window
        """Present the frame, and take the capture from it before the swap."""
        if self._capture is not None and self._capture.tick():
            result = super(TwigContext, self).presentFrame()
            self.setCurrent()
            sys.stdout.write('captured %s\n' % (self.config.capture,))
            sys.stdout.flush()
            os._exit(0)
            return result
        return super(TwigContext, self).presentFrame()


def hud_default_fov() -> float:
    """The vertical field of view the reticule is projected through by default.

    The view platform's own frustum is what should answer this; it is read
    defensively because the platform is built after the first frame is asked
    for, and a reticule drawn one frame at the wrong width is better than a
    frame that fails.
    """
    return math.pi / 2.0


def view_fov(platform: Any) -> float:
    """The vertical field of view a platform is drawing with, in **radians**.

    The platform keeps its frustum as OpenGL wants it -- degrees, aspect,
    near, far -- and everything that reasons about what is on the screen wants
    the angle the projection was built from.  Chiefly the reticule: it is
    drawn at the radius a shot may actually land within
    (:func:`twig_bb.weapons.spread_pixels`), so a cone of fire in degrees
    becomes pixels through *this* angle, and a player sighting through a rifle
    sees the reticule open exactly as much as the view has narrowed.

    A platform that has not been built yet answers :func:`hud_default_fov`,
    for the reason that function gives.
    """
    frustum = getattr(platform, 'frustum', None)
    if not frustum:
        return hud_default_fov()
    return math.radians(float(frustum[0]))


#: Keys that open a screen, and the handler each runs.  Bound as ``keyboard``
#: key-downs; see ``TwigContext.bindScreenKeys``.  F2 is not here: every
#: OpenGLContext context binds it to a screenshot for itself.
#: The key that shows the whole scoreboard while it is held.  Tab, because
#: that is where every game in this genre puts it and a player will try it
#: before they read anything.
SCOREBOARD_KEY = '<tab>'

SCREEN_KEYS = (
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
    about — see :meth:`TwigContext._offer_core_textures`.  Asking here would
    block before the window is even open, and the overlay would never get a
    chance to draw.

    A map whose textures turn out to be missing is loaded a second time with
    the pack added, since the geometry, materials and atlas are built from the
    content available at load time and cannot be patched in afterwards.
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

    ``SPEC-Q3SHADER §2.2``: a sky surface is a hole the sky is shown through,
    and the geometry builder leaves those holes undrawn, so this is what fills
    them.
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
    logging.basicConfig(level=logging.DEBUG if options.verbose else logging.INFO)
    logging.getLogger('OpenGLContext.scenegraph.text').setLevel(logging.WARNING)
    apply_render_env(options)
    TwigContext.config = options
    TwigContext._target = options.target
    TwigContext.ContextMainLoop(
        definition=context_definition(fullscreen=wants_fullscreen(options)))


if __name__ == '__main__':
    main()
