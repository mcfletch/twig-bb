"""Build a PBR scenegraph from batched world geometry.

One :class:`~OpenGLContext.scenegraph.shape.Shape` per batch, each holding a
:class:`~OpenGLContext.scenegraph.pbrmesh.PBRMesh` and a ``PBRMaterial`` from
:mod:`twitchoglc.materials`.  Baked lighting is wired through the pass's
``lightmap`` channel, which reads its texture linearly — a lightmap holds light
rather than colour, so it must not be gamma-decoded — and samples the second UV
set, where the atlas coordinates live.

Two kinds of batch are built but not drawn: an undrawn surface
(``SPEC-BSP38 §8.1``'s nodraw, ``SPEC-Q3SHADER §2.2``'s equivalents), and sky.
Sky is left out deliberately: ``SPEC-BSP38 §8.1`` calls the surface a hole
through which the sky is shown, so not drawing it is what lets the background
node show through the hole.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from OpenGLContext.scenegraph.appearance import Appearance
from OpenGLContext.scenegraph.group import Group
from OpenGLContext.scenegraph.pbrmesh import PBRMesh
from OpenGLContext.scenegraph.shape import Shape

from .animator import SurfaceAnimator
from .lightmapatlas import LightmapAtlas
from .materials import MaterialLibrary
from .worldgeometry import Batch, WorldGeometry

log = logging.getLogger(__name__)

_NAME_SAFE = re.compile(r'[^A-Za-z0-9_]')


def build_scene(world: WorldGeometry, atlas: LightmapAtlas,
                library: MaterialLibrary,
                animator: Optional[SurfaceAnimator] = None) -> Group:
    """A ``Group`` of shapes for every drawable batch of ``world``.

    ``animator`` collects the batches whose materials move
    (``SPEC-Q3SHADER §2.4``) as they are built.  Registering here rather than
    walking the finished scenegraph is what lets a surface be told to deform
    *before* its vertex buffers exist, which is what decides whether its
    texture-coordinate buffer is built dynamic.
    """
    children = []
    for index, batch in enumerate(world.batches):
        shape = build_shape(batch, index, atlas, library, animator)
        if shape is not None:
            children.append(shape)
    log.debug('scene built with %d shapes from %d batches (%d animated)',
              len(children), len(world.batches),
              0 if animator is None else len(animator))
    return Group(children=children)


def build_shape(batch: Batch, index: int, atlas: LightmapAtlas,
                library: MaterialLibrary,
                animator: Optional[SurfaceAnimator] = None) -> Optional[Shape]:
    """One batch as a shape, or None when the batch is not drawn."""
    style = batch.style
    if not style.draw or style.sky:
        return None
    page = _page(atlas, batch.lightmap_page)
    material = library.material_for(style, lightmap=page,
                                    lightmap_key=batch.lightmap_page)
    mesh = PBRMesh(
        positions=batch.positions,
        normals=batch.normals,
        texcoords=batch.texcoords,
        texcoords1=batch.texcoords1,
        tangents=batch.tangents,
        indices=batch.indices,
        material=material,
        # PBRMesh.solid is the backface-culling flag, so a two-sided material
        # must clear it (SPEC-Q3SHADER §2.1's `cull none`; version 38 has no
        # flag for it, so a v38 surface is always single-sided).
        solid=not style.double_sided)
    # Sky is drawn by the backdrop rather than as geometry, so it must not be
    # written into a shadow map either; the shadow pass reads this opt-out off
    # the geometry node.
    mesh.castsShadow = style.casts_shadow
    if animator is not None:
        animator.add(style, material, mesh=mesh, resolve=library.texture_for)
    return Shape(geometry=mesh, appearance=Appearance(material=material),
                 DEF=_shape_name(style.name, index))


def _page(atlas: LightmapAtlas, page: int) -> Optional[Any]:
    """The atlas page a batch samples, or None when it has no baked lighting."""
    if page < 0 or page >= len(atlas.pages):
        return None
    return atlas.pages[page]


def _shape_name(texture: str, index: int) -> str:
    """A stable, readable DEF so a shape can be found in a scenegraph dump."""
    stem = texture.rsplit('/', 1)[-1] or 'surface'
    return '%s_%d' % (_NAME_SAFE.sub('_', stem), index)
