"""Where the art that ships with this package lives, and how a table asks for it.

**A table names a file; this finds it and loads it.**  Both the weapons
(:mod:`twig_bb.weapons`) and the pickups (:mod:`twig_bb.items`) declare
their model as a path relative to the art directory (:func:`assets_directory`), so putting §7's commissioned
art in front of a stand-in is an edit to a table and never a code change.  The
one thing they both need from code is this: turn that relative name into a
subtree, and do something sensible when it will not load.

**A model that will not load is not an error.**  It leaves a hand empty or a
pickup undrawn, and the game carries on: an item's *rules* are what decide a
match, and a level whose circuit stops working because one ``.glb`` is corrupt
would be a far worse failure than one with an invisible medikit in it.  The
warning is logged, once, with the traceback.

**Recolouring is here because the alternative is four copies of a sphere.**  A
pickup that differs from another only in colour is one file and one number, not
a second file with the same 500 vertices in it -- see :func:`recolour`.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterator, Optional, Sequence

from OpenGLContext.contentpacks import Application, ContentStore

from . import catalog

log = logging.getLogger(__name__)

__all__ = ['CONTENT', 'IN_WHEEL', 'art_is_here', 'assets_directory', 'brighten', 'path_for',
           'load', 'recolour', 'shapes']

#: The copy that ships inside the package, read while the art pack is not here.
IN_WHEEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')


class _Content(Application):
    """The game's packs, in the store :func:`twig_bb.download.store` opens."""

    def store(self, root: Optional[str] = None) -> ContentStore:
        from . import download
        return download.store(root or self.root)


#: The game's content: its registry, its store, and its art pack.
CONTENT = _Content('twig-bb', catalog.CATALOG_PATH, base='twig-bb/art',
                   fallback=IN_WHEEL)


def assets_directory(cache_dir: Optional[str] = None) -> str:
    """Where this game's own art is read from, as of now.

    The art pack once it is installed, else the copy inside the wheel;
    :class:`~OpenGLContext.contentpacks.application.NotInstalled` if neither.
    Asked each time, since the game is imported before a first run can have
    fetched anything.
    """
    from . import download
    return CONTENT.base_directory(download.store(cache_dir))


def art_is_here(cache_dir: Optional[str] = None) -> bool:
    """Whether the game's own art can be read: the pack, or the wheel's copy."""
    try:
        assets_directory(cache_dir)
    except LookupError:
        return False
    return True


def path_for(relative: str) -> str:
    """Where a table's model name actually is on disk."""
    return os.path.join(assets_directory(), relative)


def load(relative: str, mount: Optional[str] = None) -> Optional[Any]:
    """The scenegraph subtree for one model, or None if it will not load.

    Every call reads the file again and hands back a subtree nobody else holds,
    because the caller is entitled to :func:`recolour` what it gets.  Callers
    that want one copy cache it themselves -- how long a model should be kept
    is a question about the thing holding it, not about the loader.

    ``mount`` names an attachment point, and asks for the subtree placed so
    that the point *the model itself* declares sits at the origin -- ready to
    hang on a rig's point of the same name.  A model that declares no such
    point comes back placed by its own origin, which is what every model does
    without this.
    """
    path = relative
    try:
        path = path_for(relative)
        from OpenGLContext.loaders.gltf import load_gltf
        scene = load_gltf(path)
        if mount is None:
            return scene.group
        from OpenGLContext.character.attachment import mounted
        return mounted(scene, mount)
    except Exception:                       # noqa: BLE001 - art, not rules
        log.warning('could not load the model %s', path, exc_info=True)
        return None


def shapes(node: Any) -> Iterator[Any]:
    """Every ``Shape`` in a subtree, in the order it was built."""
    if getattr(node, 'geometry', None) is not None:
        yield node
    for child in getattr(node, 'children', None) or ():
        for found in shapes(child):
            yield found


def brighten(node: Any, glow: float) -> int:
    """Light a subtree from inside without repainting it; returns materials touched.

    The half of :func:`recolour` that art which *arrived* coloured still needs.
    A map places no dynamic lights, so every pickup needs a floor of its own or
    it is a black shape in a corner -- but a model built to look like something
    (a launcher in a bubble, rather than a shape whose colour is the whole of
    what it says) must not have that shape painted over to get it.

    Each material glows in **its own** colour rather than in one shared one, so
    the model keeps its reds red and its greys grey instead of being pulled
    towards a single hue by the lighting it carries.

    **Every material, including the ones you can see through.**  A pickup's
    shell needs the floor as much as its contents do: a level bakes its
    lighting and places no lamps, so a shell left unlit borrows its colour from
    surroundings that have none to give and the whole pickup reads as a black
    ball across a room.  Whether the shell then looks *right* is a question for
    the art -- see the glaze in the build script -- and not a reason to leave
    it dark here.
    """
    amount = float(glow)
    touched = 0
    for shape in shapes(node):
        material = getattr(getattr(shape, 'appearance', None), 'material', None)
        if material is None:
            continue
        own: Any = getattr(material, 'baseColor', None)
        if own is None:
            own = getattr(material, 'diffuseColor', (1.0, 1.0, 1.0))
        lit = tuple(float(value) * amount for value in own)
        if hasattr(material, 'emissiveColor'):
            material.emissiveColor = lit
        touched += 1
    return touched


def recolour(node: Any, colour: Sequence[float], glow: float = 0.0) -> int:
    """Repaint a subtree in one colour; returns how many materials were touched.

    **Mutates what it is given**, which is why :func:`load` never shares: two
    pickups of different kinds are two loads, and the four health packs are the
    same sphere painted four ways rather than four spheres.

    Only the base and emissive colours move.  Transparency, alpha mode, metallic,
    roughness and sheen are the model's own and are what make a glass bubble read
    as glass -- a recolour that flattened those would be a repaint of the
    material rather than of the colour, and every variant would look like the
    same plastic.

    ``glow`` is a fraction of the colour added as emission.  A map places no
    dynamic lights at all -- both families bake their lighting into lightmaps --
    so a pickup in an unlit corner is a black shape without it.  It is a floor,
    not a light: it touches this model and nothing else in the world.
    """
    wanted = tuple(float(value) for value in colour)
    lit = tuple(value * float(glow) for value in wanted)
    touched = 0
    for shape in shapes(node):
        material = getattr(getattr(shape, 'appearance', None), 'material', None)
        if material is None:
            continue
        for name, value in (('baseColor', wanted), ('diffuseColor', wanted),
                            ('emissiveColor', lit)):
            if hasattr(material, name):
                setattr(material, name, value)
        touched += 1
    return touched
