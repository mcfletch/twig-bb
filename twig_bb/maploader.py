"""Load a map by sniffing its version and reading it.

This is the seam the rest of the viewer sits behind: a caller hands over a path
and gets a :class:`LoadedMap`, whose geometry, materials, scene, collision mesh,
spawn points and push volumes the viewer asks about without caring how the file
on disk was laid out.  ``SPEC-BSP46 §1.2`` is the container this reads.

Surface styles come from the `.shader` scripts of ``SPEC-Q3SHADER``:
``SPEC-BSP46 §6.2`` records no flag values on a surface, so what a texture name
means is decided by its material script, producing a
:class:`~twig_bb.surfaces.SurfaceStyle`.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import bspfile, jumppads, q3bsp, q3geometry, q3shader
from .entities import Entity
from .lightmapatlas import LightmapAtlas
from .materials import DEFAULT_LIGHTMAP_STRENGTH, MaterialLibrary
from .scene import build_scene
from .surfaces import SurfaceStyle
from .worldgeometry import SCENE_SCALE, WorldGeometry, to_scene_points

log = logging.getLogger(__name__)

#: Classnames a level editor writes for a player start.  Mapping vocabulary
#: rather than a format fact: nothing in ``SPEC-BSP46 §5`` defines them, and
#: they are the same words in every editor's entity list.
SPAWN_CLASSNAMES = (
    'info_player_start', 'info_player_deathmatch', 'info_player_team1',
    'info_player_team2', 'team_ctf_redplayer', 'team_ctf_blueplayer',
    'team_ctf_redspawn', 'team_ctf_bluespawn', 'info_player_coop',
)

#: A map lives at ``maps/<name>.bsp`` inside its content tree, so its content
#: root is the directory above ``maps`` (``SPEC-BSP46 §7.2``).
MAPS_DIR = 'maps'


@dataclass
class SpawnPoint:
    """Where a player may start, in scene space."""

    position: np.ndarray
    #: Yaw in degrees as the map authored it.
    angle: float = 0.0
    classname: str = ''


@dataclass
class LoadedMap:
    """One loaded map: its geometry, its materials, and what a viewer asks of it."""

    path: str
    name: str
    family: str
    version: int
    bsp: Any
    world: WorldGeometry
    atlas: LightmapAtlas
    library: MaterialLibrary
    roots: List[str]
    #: What a texture name means as a surface, as its material script says
    #: (``SPEC-Q3SHADER``).
    style_for: Optional[Callable[[str], SurfaceStyle]] = None

    @property
    def entities(self) -> Sequence[Entity]:
        return self.bsp.entities

    def visibility(self) -> Any:
        """Which of this map's rooms can be seen from which.

        Built once and kept: the tables are the file's own and do not change,
        and a level asks about them every frame.  A map compiled without
        visibility data yields one that rejects nothing, so a caller never has
        to ask whether there is any.
        """
        found = getattr(self, '_visibility', None)
        if found is None:
            from .visibility import Visibility
            found = Visibility.from_bsp(self.bsp)
            self._visibility = found
        return found

    @property
    def gravity(self) -> float:
        """The map's gravity in units per second squared (``SPEC-TRIGGER-PUSH §8``)."""
        return jumppads.map_gravity(self.bsp.entities)

    def scene(self, animator: Any = None) -> Any:
        """The scenegraph group for this map's drawable surfaces.

        ``animator`` is a :class:`~twig_bb.animator.SurfaceAnimator` to
        collect the surfaces whose materials move; without one the map is built
        exactly as before and its animated materials are drawn still.
        """
        return build_scene(self.world, self.atlas, self.library, animator)

    def texture_names(self) -> List[str]:
        """Every texture this map's drawn surfaces name, once each."""
        return sorted({batch.style.name for batch in self.world.batches
                       if batch.style.draw and not batch.style.sky})

    def unscripted_surfaces(self) -> List[str]:
        """Drawn surfaces this map names that no material script defines.

        Not an error (``SPEC-Q3SHADER §3.2``): the name is used as a texture
        path and the surface draws.  It is worth *reporting* because everything
        else the script would have said is gone with it -- most visibly the
        animation, so a pool of lava that should churn sits perfectly still and
        the animator gets the blame for content the user does not have.
        """
        return sorted({batch.style.name for batch in self.world.batches
                       if batch.style.draw and not batch.style.sky
                       and not batch.style.scripted})

    @cached_property
    def _missing_textures(self) -> List[str]:
        """The texture names whose image could not be found.

        Most maps name only the textures they add and take the rest from the
        game's base content, which is not shipped with the map.  Without this
        an absent content tree is indistinguishable from a broken loader: the
        map renders, in grey.

        Worked out once: a loaded map does not change, and the developer
        overlay asks every frame.  Resolving a few hundred texture names
        against the content tree is most of a millisecond, which is a real
        part of a frame to spend on a number that cannot have moved.
        """
        return [name for name in self.texture_names()
                if self.library.resolve(name) is None]

    def missing_textures(self) -> List[str]:
        """The texture names whose image could not be found."""
        return self._missing_textures

    def collision_mesh(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """One static trimesh of the map's solid surfaces, in scene space."""
        return self.world.collision_mesh()

    def model_bounds(self, index: Optional[int]
                     ) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """A brush model's map-space bounds, or None (``SPEC-BSP46 §4.6``)."""
        if index is None:
            return None
        models = self.bsp.models
        if index < 0 or index >= len(models):
            return None
        record = models[index]
        return (np.asarray(record['mins'], dtype='d'),
                np.asarray(record['maxs'], dtype='d'))

    def pickups(self, table: Any = None) -> Any:
        """Everything the map placed for players to collect.

        ``SPEC-Q3ENTITIES §3``.  A classname this game has nothing to give for
        is skipped rather than being an error (`§3.2.4`), and
        :func:`~twig_bb.items.unknown_classnames` is how to find out what
        was skipped -- which matters, because a level whose whole weapon
        circuit is content nobody has plays exactly like a broken reader.
        """
        from . import items
        return items.from_entities(self.entities, table)

    def unplaceable_pickups(self) -> Any:
        """Pickup classnames this game has nothing for, and how many of each."""
        from . import items
        return items.unknown_classnames(self.entities)

    def liquid_volumes(self) -> Any:
        """The map's water, slime and lava as boxes to swim in."""
        from . import liquids
        return liquids.from_map(self)

    def speakers(self) -> Any:
        """The map's ambient sounds, as one group to put in the scene.

        ``SPEC-Q3ENTITIES §1``.  Empty for the 21 of 50 shipped maps that place
        none, and for any map loaded without the content its sounds live in.
        """
        from . import speakers
        return speakers.from_map(self)

    def push_volumes(self, scene_gravity: Optional[float] = None
                     ) -> List[jumppads.PushVolume]:
        """This map's push volumes (``SPEC-TRIGGER-PUSH §1``, ``§9.4``)."""
        return jumppads.push_volumes(self, scene_gravity)

    def spawn_points(self) -> List[SpawnPoint]:
        """Every player start the map defines, in scene space."""
        spawns: List[SpawnPoint] = []
        for entity in self.bsp.entities:
            if entity.classname.lower() not in SPAWN_CLASSNAMES:
                continue
            position = to_scene_points(np.array([entity.vector('origin')]))[0]
            spawns.append(SpawnPoint(position=position,
                                     angle=entity.number('angle'),
                                     classname=entity.classname))
        return spawns


def load(path: str, lightmap_strength: Optional[float] = None,
         extra_roots: Sequence[str] = (),
         subdivisions: Optional[int] = None) -> LoadedMap:
    """Load the map at ``path``, whichever family it belongs to."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    sniffed = bspfile.sniff_version(path)
    if sniffed is None:
        with open(path, 'rb') as handle:
            head = handle.read(4)
        if head[:2] == b'PK':
            raise bspfile.MalformedBSP(
                'this looks like a .pk3/.zip archive, not a .bsp map: %s' % (path,))
        raise bspfile.MalformedBSP('%s is not an IBSP map' % (path,))
    _magic, version = sniffed
    roots = _content_roots(path, extra_roots)
    name = os.path.splitext(os.path.basename(path))[0]
    strength = (DEFAULT_LIGHTMAP_STRENGTH if lightmap_strength is None
                else lightmap_strength)
    if version == q3bsp.BSP_VERSION:
        return _load_quake3(path, name, roots, strength, subdivisions)
    raise bspfile.MalformedBSP(
        'IBSP version %d is not supported (expected %d)'
        % (version, q3bsp.BSP_VERSION))


def _content_roots(path: str, extra: Sequence[str]) -> List[str]:
    """The directories a map's textures and scripts are resolved against."""
    directory = os.path.dirname(os.path.abspath(path))
    root = (os.path.dirname(directory)
            if os.path.basename(directory).lower() == MAPS_DIR else directory)
    roots = [root]
    for candidate in extra:
        if candidate and candidate not in roots:
            roots.append(candidate)
    return roots


def _load_quake3(path: str, name: str, roots: List[str], strength: float,
                 subdivisions: Optional[int]) -> LoadedMap:
    """Read a version 46 map and the material scripts that describe it."""
    bsp = q3bsp.load(path)
    library = MaterialLibrary(roots, family='quake3', lightmap_strength=strength)
    materials = q3shader.load_scripts(roots)

    def style_for(texture_name: str) -> SurfaceStyle:
        return q3shader.style_for(materials, texture_name)

    kwargs: Dict[str, Any] = {}
    if subdivisions is not None:
        kwargs['subdivisions'] = subdivisions
    world, atlas = q3geometry.build(bsp, style_for=style_for, **kwargs)
    return LoadedMap(path=path, name=name, family='quake3',
                     version=q3bsp.BSP_VERSION, bsp=bsp, world=world,
                     atlas=atlas, library=library, roots=roots,
                     style_for=style_for)


def main() -> None:
    """Report what a map contains, without opening a window."""
    import argparse
    parser = argparse.ArgumentParser(
        description='Read a Quake 3 map and report it')
    parser.add_argument('target', help='a .bsp map file')
    parser.add_argument('--verbose', action='store_true', help='log the details')
    options = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if options.verbose else logging.INFO)
    loaded = load(options.target)
    print('%s: %s, IBSP version %d' % (loaded.name, loaded.family, loaded.version))
    print('  %d entities, %d batches, %d triangles'
          % (len(loaded.entities), len(loaded.world.batches),
             loaded.world.triangle_count))
    print('  %d lightmap pages, %d textures (%d missing)'
          % (len(loaded.atlas.pages), len(loaded.texture_names()),
             len(loaded.missing_textures())))
    print('  gravity %g units/s^2, %d spawn points'
          % (loaded.gravity, len(loaded.spawn_points())))
    print('  %s' % (jumppads.describe(loaded.push_volumes()),))
    low, high = loaded.world.bounds
    print('  bounds %s .. %s metres (%g m per map unit)'
          % (np.round(low, 2), np.round(high, 2), SCENE_SCALE))
