"""Driving a map's animated surfaces from one clock.

:mod:`twitchoglc.surfaceanim` says *what* a surface does at time ``t``; this
says where each answer goes, and how much it costs:

===========================  ==============================  ================
Directive                    Lands on                        Cost per frame
===========================  ==============================  ================
``tcMod`` (affine)           ``PBRMaterial.uv_transform``    one uniform
``rgbGen``                   ``PBRMaterial.baseColor``       one uniform
``alphaGen``                 ``PBRMaterial.transparency``    one uniform
``animMap``                  ``PBRMaterial.textures``        one texture bind
``deformVertexes``           the mesh's vertex buffers       the vertices
``tcMod turb``               the mesh's texcoord buffer      the vertices
===========================  ==============================  ================

The top four are why nearly every animated surface in a map is free: a scrolling
conveyor, a rotating fan, a pulsing light and a flickering screen all cost one
uniform each, however large the surface is.  Only the bottom two touch geometry,
and those are the liquids -- which are a small share of a map's faces, and the
reason the split is worth making rather than deforming everything.

**Units.**  A `.shader` script writes distances in *map* units; the scenegraph is
in metres.  A ``deformVertexes wave 100 sin 0 4 0 0.4`` asks for four map units
of heave, not four metres, so the deformer converts both ways: positions into map
units before evaluating, displacement back into metres afterwards.  Getting this
wrong is not subtle -- it is a water surface that swings forty times too far.

**One clock.**  Every surface is asked at the same ``t``, which is what makes a
map's scrolling textures move together rather than drift apart.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional, Sequence, Tuple

import numpy as np

from .surfaceanim import SurfaceAnimation
from .surfaces import SurfaceStyle
from .worldgeometry import SCENE_SCALE

log = logging.getLogger(__name__)

#: ``texCoordMask`` bits, matching ``PBRMaterial.texCoordMask`` and the
#: ``uvFor()`` decode in ``pbr.frag``: the low bit picks the second UV set for a
#: channel, the same bit shifted by 8 applies the UV transform to it.
BASE_COLOR_BIT = 1
LIGHTMAP_BIT = 32
TRANSFORM_SHIFT = 8

#: What a texture name resolves to -- a ``PBRTexture``, or None if it will not
#: load.  Supplied by the material library, which owns the caching.
Resolver = Callable[[str], Any]


class SurfaceDeformer:
    """One material's geometry and turbulence, at a settable time.

    An object rather than a closure so the per-frame update writes one float
    instead of allocating a new function for every liquid surface in a map.  It
    is handed to :meth:`OpenGLContext.scenegraph.pbrmesh.PBRMesh.set_surface_deformer`
    and is called with the mesh's rest pose.
    """

    def __init__(self, animation: SurfaceAnimation) -> None:
        self.animation = animation
        self.time = 0.0

    def __call__(self, positions: Any, normals: Any,
                 texcoords: Any) -> Tuple[Any, Any, Any]:
        """The rest pose moved for :attr:`time`.

        Positions arrive in scene metres and the script's numbers are in map
        units, so the conversion happens here rather than being spread through
        :mod:`~twitchoglc.surfaceanim` -- which knows nothing about this
        renderer's scale and should not have to.
        """
        animation = self.animation
        if positions is not None and (animation.deforming or animation.turbulent):
            in_map_units = np.asarray(positions, dtype='d') / SCENE_SCALE
        else:
            in_map_units = None
        if in_map_units is not None and animation.deforming:
            moved = animation.displace(in_map_units, normals, self.time)
            positions = np.asarray(moved, dtype='f') * SCENE_SCALE
            if normals is not None:
                normals = np.asarray(
                    animation.perturb(in_map_units, normals, self.time), dtype='f')
        if in_map_units is not None and texcoords is not None:
            offsets = animation.turbulence_at(in_map_units, self.time)
            if offsets is not None:
                texcoords = np.asarray(texcoords, dtype='f') + offsets.astype('f')
        return positions, normals, texcoords


class _AnimatedSurface:
    """One batch of a map whose material moves, and everything it moves."""

    __slots__ = ('animation', 'material', 'mesh', 'resolve', 'deformer',
                 'base_color', 'frame')

    def __init__(self, animation: SurfaceAnimation, material: Any,
                 mesh: Any = None, resolve: Optional[Resolver] = None) -> None:
        self.animation = animation
        self.material = material
        self.mesh = mesh
        self.resolve = resolve
        self.deformer: Optional[SurfaceDeformer] = None
        #: The authored colour, kept because ``rgbGen`` *multiplies* it rather
        #: than replacing it -- a material with no texture carries its own
        #: colour there, and overwriting it would repaint the surface white.
        self.base_color = tuple(getattr(material, 'baseColor', (1.0, 1.0, 1.0)))
        #: The frame currently bound, so an unchanged frame costs nothing.
        self.frame: Optional[str] = None

    def update(self, time: float) -> None:
        """Move this surface to where it is at ``time``."""
        animation = self.animation
        material = self.material
        if animation.transforming:
            material.uv_transform = _uv_matrix(animation, time)
        if animation.rgbgen is not None:
            generated = animation.color_at(time)
            material.baseColor = tuple(
                authored * level
                for authored, level in zip(self.base_color, generated, strict=True))
        if animation.alphagen is not None and _blends(material):
            material.transparency = 1.0 - animation.alpha_at(time)
        if animation.animmap is not None and self.resolve is not None:
            self._showFrame(time)
        if self.deformer is not None:
            self.deformer.time = time
            self.mesh.refresh_surface()

    def _showFrame(self, time: float) -> None:
        """Bind the frame showing at ``time``, if it is not already bound."""
        name = self.animation.frame_at(time)
        if name is None or name == self.frame:
            return
        texture = self.resolve(name) if self.resolve is not None else None
        if texture is None:
            # A frame that will not load leaves the last one showing, which is
            # what a gap in a cycle should look like -- not a hole in the wall.
            return
        self.frame = name
        # Replaced rather than mutated: the material bumps its upload version on
        # assignment, and an in-place edit would serve a stale texture set.
        textures = dict(material_textures(self.material))
        textures['baseColor'] = texture
        self.material.textures = textures


def material_textures(material: Any) -> dict:
    """A material's texture map, tolerating one that has none."""
    return getattr(material, 'textures', None) or {}


def _blends(material: Any) -> bool:
    """Whether an opacity written to this material would be drawn.

    An ``alphaGen`` on a surface the map never asked to blend cannot be shown,
    and writing it anyway would make the surface vanish rather than shimmer.
    """
    return getattr(material, 'alphaMode', None) == 'BLEND'


class SurfaceAnimator:
    """Every animated surface in one map, driven from one clock.

    Built while the scene is, and asked once a frame.  A surface that does not
    move is never taken on, so a map with no animated materials costs one empty
    loop -- and most of a map does not move.
    """

    def __init__(self, surfaces: Sequence[Any] = ()) -> None:
        self._surfaces: List[_AnimatedSurface] = list(surfaces)
        #: The time everything is currently at, so asking twice costs nothing.
        self._time: Optional[float] = None

    def __len__(self) -> int:
        return len(self._surfaces)

    def add(self, style: SurfaceStyle, material: Any, mesh: Any = None,
            resolve: Optional[Resolver] = None) -> bool:
        """Take on one batch; return whether it will actually be driven.

        A **constant** transform -- a `tcMod scale` that tiles the surface -- is
        applied here and then forgotten: it is a property of the surface rather
        than an animation, and a material that never changes should not be
        re-uploaded sixty times a second.
        """
        animation = style.animation
        if animation.transforming:
            _applyTransformMask(material)
            material.uv_transform = _uv_matrix(animation, 0.0)
        if not animation.animated:
            return False
        surface = _AnimatedSurface(animation, material, mesh, resolve)
        if mesh is not None and _needsVertices(animation):
            surface.deformer = SurfaceDeformer(animation)
            # Set before the mesh is first drawn, so its texture-coordinate
            # buffer is built dynamic -- see PBRMesh.deforms_texcoords.
            mesh.set_surface_deformer(surface.deformer)
        self._surfaces.append(surface)
        return True

    def update(self, time: float) -> int:
        """Move every surface to where it is at ``time``; return how many.

        Moving to a time it is **already at** does nothing and reports nothing:
        a paused game and a capture with a pinned clock both ask repeatedly, and
        recomputing an unchanged wave -- which for a liquid means a whole vertex
        pass and a buffer re-upload -- is pure waste.

        A material that raises is dropped for the frame rather than taking the
        rest of the map with it: one bad surface should cost its own animation,
        not freeze a level.
        """
        if time == self._time:
            return 0
        self._time = time
        moved = 0
        for surface in self._surfaces:
            try:
                surface.update(time)
            except Exception as error:
                log.warning('surface animation failed, leaving it still: %s', error)
                continue
            moved += 1
        return moved


def _uv_matrix(animation: SurfaceAnimation, time: float) -> list:
    """The material's UV transform for ``animation`` at ``time``.

    Transposed on the way across, because the two sides use opposite
    conventions and both are right for where they live:
    :mod:`twitchoglc.surfaceanim` is row-vector like the rest of this
    workspace's geometry (``uv @ M``, translation in the last *row*), while
    ``PBRMaterial.uv_transform`` follows ``KHR_texture_transform`` and the
    shader's ``uvTransform * vec3(uv, 1.0)`` (translation in the last
    *column*).  Handing one to the other untransposed does not fail -- it
    silently scrolls the surface diagonally and scales it wrongly, which is a
    much worse way to find out.
    """
    return animation.transform_at(time).T.tolist()


def _needsVertices(animation: SurfaceAnimation) -> bool:
    """Whether this animation has to touch geometry rather than a uniform."""
    return animation.deforming or animation.turbulent


def _applyTransformMask(material: Any) -> None:
    """Mark the base-colour channel as transformed, and only that one.

    The lightmap is deliberately left out: a scrolling texture that dragged the
    baked lighting along with it would take the shadows off the walls.
    """
    mask = int(getattr(material, 'texCoordMask', 0) or 0)
    material.texCoordMask = mask | (BASE_COLOR_BIT << TRANSFORM_SHIFT)
