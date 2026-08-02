"""What this game tells the developer overlay about itself.

The overlay, its registry and its drawing are OpenGLContext's
(:mod:`OpenGLContext.ui.debugoverlay`); the engine already registers the frame
rate, the renderer's state and the camera.  What is here is the half only twitch
can answer: which map is loaded, how much of it there is, which movement mode is
in force, where the player is in **map** coordinates as well as scene ones, and
what the physics world is carrying.

**Every provider reads defensively**, because the overlay is most wanted exactly
when the thing it reports on is half built: a viewer between maps has no
``loaded``, a free-flying camera has no character controller, and the physics
world does not exist until the player first walks.  A section with nothing to
say is left out; none of them is ever a reason for a frame to fail.

This is also where the old top-left movement-mode label went.  A player does not
want to be told the name of the camera mode, and a developer wants that plus a
dozen things it never showed.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from OpenGLContext.ui.debugoverlay import physics_provider

from .worldgeometry import SCENE_SCALE

__all__ = ['combat_provider', 'install', 'map_provider',
           'player_provider']


def install(context: Any) -> None:
    """Register twitch's sections on a context's developer overlay.

    Called once, when the viewer starts.  Registration is by title, so calling
    it again replaces the sections rather than growing a second set.
    """
    overlay = context.debugOverlay
    overlay.register('Map', map_provider(context), order=40)
    overlay.register('Player', player_provider(context), order=50)
    overlay.register('Combat', combat_provider(context), order=55)
    overlay.register('Physics',
                     physics_provider(lambda: _physics_world(context)),
                     order=60)


def map_provider(context: Any) -> Any:
    """What is loaded, and how much of it there is."""
    def rows() -> List[Tuple[str, Any]]:
        loaded = getattr(context, 'loaded', None)
        if loaded is None:
            return []
        found: List[Tuple[str, Any]] = [
            ('name', loaded.name),
            ('family', loaded.family),
            ('triangles', loaded.world.triangle_count),
            ('batches', len(loaded.world.batches)),
            ('lightmaps', len(loaded.atlas.pages)),
        ]
        missing = loaded.missing_textures()
        if missing:
            found.append(('missing textures', len(missing)))
        # Surfaces the map names and no script defines.  Reported because
        # everything the script would have said is gone with it -- most
        # visibly the animation, so a still pool of lava reads as a broken
        # animator rather than as base content nobody has.
        unscripted = loaded.unscripted_surfaces()
        if unscripted:
            found.append(('unscripted surfaces', len(unscripted)))
        # How many of the map's speakers actually found a sound, which is the
        # number worth seeing: the engine's own Audio section says whether
        # anything is playing, and this says whether there was anything to
        # play.  A map that names sounds from content nobody fetched reports
        # its speakers as zero, which is the answer to "why is it silent".
        speakers = getattr(context, 'speakers', None)
        if speakers is not None:
            found.append(('speakers', len(speakers.children)))
        # What the map itself can kill you with.  Both are invisible from
        # inside the game when they are missing: a map whose liquid brushes
        # named a material nobody has reports no volumes and its lava is
        # scenery, and a level with no floor under it is a fall that never
        # ends.  Each hazard says what it is watching.
        played = getattr(context, 'rules', None)
        # Pickups this game has nothing to give for.  A map whose weapon
        # circuit is all content nobody has plays like a map with no weapons
        # in it, which is indistinguishable from a broken reader.
        unplaceable = loaded.unplaceable_pickups()
        if unplaceable:
            found.append(('pickups not answered', sum(unplaceable.values())))
        for hazard in ('harm', 'floor', 'pickups'):
            watching = getattr(played, hazard, None)
            if watching is not None:
                found.extend(sorted(watching.describe().items()))
        return found
    return rows


def player_provider(context: Any) -> Any:
    """Where the player is, what they are doing, and what they are carrying.

    The position is in **map units**, which is the one form the engine's own
    ``View`` section does not give: it reports scene metres, and map units are
    what the entity lump is written in, so a spawn point, a jump pad or a
    speaker that is in the wrong place is compared against the number in the
    file rather than against a conversion done by eye.  Repeating the metres
    here as well would be two rows saying the same thing on a panel that is
    short of room.
    """
    def rows() -> List[Tuple[str, Any]]:
        found: List[Tuple[str, Any]] = []
        # A NULL SFNode is falsy, and is what a context with no declared
        # modes carries; an empty row would be a mode called nothing.
        mode = getattr(getattr(context, 'contextDefinition', None),
                       'movementMode', None)
        if mode:
            found.append(('mode', str(getattr(mode, 'name', '') or '-')))
        found.append(('navigation',
                      'walking' if getattr(context, '_walking', False)
                      else 'free-fly'))
        # What the simulation is actually being given each frame, and what the
        # clamp on it is costing.  The one place a stall becomes legible as the
        # thing the player is feeling: a world running at a fraction of speed
        # is not a movement bug, and without this row it is indistinguishable
        # from one.  See `twitchoglc.frameclock`.
        clock = getattr(context, '_clock', None)
        if clock is not None:
            found.extend(clock.describe().items())
        scene = _camera_position(context)
        if scene is not None:
            found.append(('map units', _to_map(scene)))
        nav = getattr(context, '_nav', None)
        if nav is not None:
            # Which liquid rather than merely whether: the three do different
            # things to the view, the mix and the player's health,
            # and "submerged: True" cannot tell a wrong one from a right one.
            found.append(('submerged', _submerged(context, nav)))
            if hasattr(nav, 'grounded'):
                found.append(('grounded', bool(nav.grounded)))
        player = getattr(context, 'player', None)
        if player is not None:
            found.extend([
                ('health', player.health),
                ('armour', player.armour),
                ('weapon', player.selected or '-'),
            ])
        return found
    return rows


def combat_provider(context: Any) -> Any:
    """The match, and what a fight has put into the air and onto the screen.

    Three numbers that cannot be seen any other way while playing: how much of
    the projectile budget is in use, how many particles the effects are
    holding, and whether the effects setting is doing what the player asked.
    A rocket that never arrives and a budget that is full look identical from
    inside the game.
    """
    def rows() -> List[Tuple[str, Any]]:
        found: List[Tuple[str, Any]] = []
        match = getattr(context, 'arena', None)
        if match is not None:
            found.extend(sorted(match.describe().items()))
        flight = getattr(context, 'flight', None)
        if flight is not None:
            found.append(('in flight', '%d / %d' % (len(flight),
                                                    flight.capacity)))
        shown = getattr(context, 'effects', None)
        if shown is not None:
            found.append(('effects', str(shown.intensity)))
            found.append(('particles',
                          sum(emitter.particleCount
                              for emitter in shown.emitters.values())))
        return found
    return rows


def _submerged(context: Any, nav: Any) -> Any:
    """Which liquid the camera is in, or False for none.

    False rather than an empty string, because the row's usual answer is a
    plain no and a blank value reads as a provider that failed.
    """
    if not getattr(nav, 'submerged', False):
        return False
    volumes = getattr(context, '_liquids', None)
    if volumes is None:
        return True
    return volumes.kind_at(nav.camera_position()) or True


def _camera_position(context: Any) -> Optional[Tuple[float, float, float]]:
    """The camera in scene metres, or None when there is no platform yet."""
    getter = getattr(context, 'getViewPlatform', None)
    platform = getter() if getter is not None else None
    position = getattr(platform, 'position', None)
    if position is None:
        return None
    x, y, z = (float(value) for value in position[:3])
    return (x, y, z)


def _to_map(scene: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Scene metres back to map units, the inverse of ``to_scene_points``.

    Scene space is +Y up in metres and map space is +Z up in units, so this
    undoes both the rotation and the scale.
    """
    x, y, z = scene
    return (x / SCENE_SCALE, -z / SCENE_SCALE, y / SCENE_SCALE)


def _physics_world(context: Any) -> Any:
    """The physics world if the viewer has built one, else None.

    Through a method on the context rather than a stored reference, because the
    world is replaced whenever a map is (re)loaded and a provider holding the
    first would report on it forever.
    """
    getter = getattr(context, 'physicsWorld', None)
    return getter() if getter is not None else None
