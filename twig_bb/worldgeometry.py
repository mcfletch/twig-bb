"""Batched triangle geometry, in scene space, for either map family.

A :class:`GeometryBuilder` collects surfaces keyed by
(:class:`~twig_bb.surfaces.SurfaceStyle`, lightmap page) and hands back a
:class:`WorldGeometry` of merged :class:`Batch` objects — one draw call each.
Both family geometry builders feed this, so the scene builder and the collision
importer see one representation.

Surfaces arrive in **map** coordinates: right-handed, +Z up, roughly an inch
per unit (``SPEC-BSP38 §3.1``, ``§3.2``; ``SPEC-BSP46 §3.1``, ``§3.2``).  The
scenegraph is Y-up and metric, so the whole pool is rotated and scaled once at
:meth:`GeometryBuilder.build` time rather than per face.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .surfaces import SurfaceStyle

# SPEC-BSP38 §3.2 / SPEC-BSP46 §3.2 -- one map unit is about one inch.
SCENE_SCALE = 0.0254


def to_scene_points(points: Any) -> np.ndarray:
    """Map-space positions to scene-space: +Z up in units to +Y up in metres."""
    array = np.asarray(points, dtype='f')
    return np.column_stack((array[:, 0], array[:, 2], -array[:, 1])) * SCENE_SCALE


def to_scene_directions(vectors: Any) -> np.ndarray:
    """Map-space directions to scene space: the same rotation, no scale.

    Normals and tangents must keep unit length, so the metre scale that applies
    to positions must not be applied here.
    """
    array = np.asarray(vectors, dtype='f')
    return np.column_stack((array[:, 0], array[:, 2], -array[:, 1]))


def orient_triangles(indices: Any, positions: Any, normals: Any) -> np.ndarray:
    """Reverse any triangle whose winding disagrees with its surface normal.

    ``SPEC-BSP38 §5.3`` says the file's winding is consistent but may be the
    wrong way round for a given API, and that a reader should determine the
    convention once and reverse uniformly.  Deciding it from each triangle's own
    outward normal settles it from the data instead of from an assumption about
    either engine's culling, and it is equally correct for a version 46 face,
    whose normals come from its vertices (``SPEC-BSP46 §4.9``).

    A degenerate triangle has no geometric normal to compare, so it is left as
    it is.
    """
    indices = np.asarray(indices, dtype=np.uint32).ravel()
    positions = np.asarray(positions, dtype='d')
    normals = np.asarray(normals, dtype='d')
    triangles = indices.reshape((-1, 3))
    if not len(triangles):
        return indices
    p0 = positions[triangles[:, 0]]
    geometric = np.cross(positions[triangles[:, 1]] - p0,
                         positions[triangles[:, 2]] - p0)
    reference = normals[triangles].sum(axis=1)
    flip = np.einsum('ij,ij->i', geometric, reference) < 0.0
    triangles = triangles.copy()
    triangles[flip] = triangles[flip][:, ::-1]
    return triangles.ravel()


@dataclass
class Batch:
    """One draw call: a merged vertex pool sharing a style and lightmap page."""

    style: SurfaceStyle
    #: Index of the lightmap atlas page this batch samples, or -1 for none.
    lightmap_page: int
    positions: np.ndarray                       # (N, 3) float32, scene space
    normals: np.ndarray                         # (N, 3) float32
    tangents: np.ndarray                        # (N, 4) float32, xyz + handedness
    texcoords: np.ndarray                       # (N, 2) float32, material UVs
    texcoords1: np.ndarray                      # (N, 2) float32, lightmap UVs
    indices: np.ndarray                         # (M,) uint32, triangles

    @property
    def triangle_count(self) -> int:
        return len(self.indices) // 3


@dataclass(frozen=True)
class SurfaceIndex:
    """Which surface each triangle of a collision mesh came from.

    A ray cast against the mesh reports the triangle it met
    (:attr:`omi_physics.raycast.RayHit.triangle`); this turns that number back
    into the :class:`~twig_bb.surfaces.SurfaceStyle` it belongs to, which is
    what lets an impact on metal differ from one on stone without searching the
    geometry a second time for a point the cast has already found.

    The mesh is a soup of merged batches, so the index is stored as the
    *boundaries* between them rather than one style per triangle: a map is
    tens of thousands of triangles and a few hundred surfaces, and the answer
    is a binary search over the small number.
    """

    #: Triangle at which each batch's run **ends**, ascending; the last entry
    #: is the length of the whole mesh.
    ends: np.ndarray
    #: The style of each run, in the same order.
    styles: Tuple[SurfaceStyle, ...]

    def __len__(self) -> int:
        """How many triangles the index covers."""
        return int(self.ends[-1]) if len(self.ends) else 0

    def style_at(self, triangle: int) -> Optional[SurfaceStyle]:
        """The surface a triangle belongs to, or None if it is not in the mesh.

        None rather than a nearest guess, because a caller reads this to choose
        an effect and a *wrong* material reads as a bug in the effect while a
        missing one falls back to the default and is merely plain.
        """
        triangle = int(triangle)
        if triangle < 0 or triangle >= len(self):
            return None
        return self.styles[int(np.searchsorted(self.ends, triangle, 'right'))]


@dataclass
class WorldGeometry:
    """Every batch of a map, plus what the rest of the viewer asks of them."""

    batches: List[Batch] = field(default_factory=list)
    bounds: Tuple[np.ndarray, np.ndarray] = field(
        default_factory=lambda: (np.zeros(3, 'f'), np.zeros(3, 'f')))

    @property
    def triangle_count(self) -> int:
        return sum(batch.triangle_count for batch in self.batches)

    def collision_batches(self) -> List[Batch]:
        """The batches the collision mesh is built from, in the order it uses.

        One list, read by both :meth:`collision_mesh` and
        :meth:`collision_surfaces`, because two walks of the batches that could
        disagree about which are in and in what order would eventually put an
        impact's material one surface out — and nothing would say so.
        """
        return [batch for batch in self.batches
                if batch.style.solid and not batch.style.liquid]

    def collision_mesh(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """``(points, triangles)`` for the solid surfaces, or None if there are none.

        One static trimesh for the whole map is what the character controller
        wants.  Liquid surfaces are left out -- a liquid is a volume to swim in
        rather than a floor (``SPEC-BSP38 §9.4``) -- so the avatar falls into
        water and :mod:`twig_bb.liquids` decides when it is submerged.
        """
        points: List[np.ndarray] = []
        triangles: List[np.ndarray] = []
        offset = 0
        for batch in self.collision_batches():
            points.append(batch.positions)
            triangles.append(batch.indices.reshape((-1, 3)).astype(np.uint32) + offset)
            offset += len(batch.positions)
        if not points:
            return None
        return (np.concatenate(points).astype('d'),
                np.concatenate(triangles).astype(np.uint32))

    def collision_surfaces(self) -> SurfaceIndex:
        """What each triangle of :meth:`collision_mesh` is made of.

        Empty rather than None for a map with nothing solid, because every
        caller of this does the same thing with an empty one as with no index
        at all -- asks it, and is told nothing.
        """
        batches = self.collision_batches()
        counts = np.cumsum([batch.triangle_count for batch in batches],
                           dtype='i8')
        return SurfaceIndex(ends=counts,
                            styles=tuple(batch.style for batch in batches))


class _Group:
    """The surfaces accumulated for one batch, before they are merged."""

    def __init__(self, style: SurfaceStyle, lightmap_page: int) -> None:
        self.style = style
        self.lightmap_page = lightmap_page
        self.positions: List[np.ndarray] = []
        self.normals: List[np.ndarray] = []
        self.texcoords: List[np.ndarray] = []
        self.texcoords1: List[np.ndarray] = []
        self.indices: List[np.ndarray] = []
        self.tangents: List[Optional[np.ndarray]] = []
        self.counts: List[int] = []


class GeometryBuilder:
    """Accumulate surfaces in map space; emit merged, scene-space batches."""

    def __init__(self) -> None:
        self._groups: Dict[Any, _Group] = {}

    def add_surface(self, style: SurfaceStyle, lightmap_page: int,
                    positions: Any, normals: Any, texcoords: Any,
                    texcoords1: Any, indices: Any,
                    tangents: Optional[Any] = None) -> None:
        """Add one surface's triangles, in map coordinates.

        ``indices`` are local to this surface's own vertices; they are rebased
        onto the merged pool when the batch is built.  ``tangents`` may be
        supplied where a surface knows its own tangent frame exactly; otherwise
        one is estimated from the UVs at build time.
        """
        indices = np.asarray(indices, dtype=np.uint32).ravel()
        if not len(indices):
            return
        key = (style.batch_key(), int(lightmap_page))
        group = self._groups.get(key)
        if group is None:
            group = self._groups[key] = _Group(style, int(lightmap_page))
        group.positions.append(np.asarray(positions, dtype='f').reshape((-1, 3)))
        group.normals.append(np.asarray(normals, dtype='f').reshape((-1, 3)))
        group.texcoords.append(np.asarray(texcoords, dtype='f').reshape((-1, 2)))
        group.texcoords1.append(np.asarray(texcoords1, dtype='f').reshape((-1, 2)))
        group.indices.append(indices)
        group.counts.append(len(group.positions[-1]))
        group.tangents.append(
            None if tangents is None
            else np.asarray(tangents, dtype='f').reshape((-1, 4)))

    def build(self) -> WorldGeometry:
        """Merge, convert to scene space, and return the finished geometry.

        Batches come out in the order their first surface arrived, so a map
        builds the same scene every time.
        """
        batches = [self._build_batch(group) for group in self._groups.values()]
        return WorldGeometry(batches=batches, bounds=_bounds(batches))

    def _build_batch(self, group: _Group) -> Batch:
        offsets = np.cumsum([0] + group.counts[:-1])
        indices = np.concatenate([
            chunk + offset
            for chunk, offset in zip(group.indices, offsets, strict=True)])
        positions = to_scene_points(np.concatenate(group.positions))
        normals = to_scene_directions(np.concatenate(group.normals))
        texcoords = np.concatenate(group.texcoords)
        texcoords1 = np.concatenate(group.texcoords1)
        tangents = self._tangents(group, positions, normals, texcoords, indices)
        return Batch(
            style=group.style, lightmap_page=group.lightmap_page,
            positions=np.ascontiguousarray(positions, 'f'),
            normals=np.ascontiguousarray(normals, 'f'),
            tangents=np.ascontiguousarray(tangents, 'f'),
            texcoords=np.ascontiguousarray(texcoords, 'f'),
            texcoords1=np.ascontiguousarray(texcoords1, 'f'),
            indices=np.ascontiguousarray(indices, np.uint32))

    @staticmethod
    def _tangents(group: _Group, positions: np.ndarray, normals: np.ndarray,
                  texcoords: np.ndarray, indices: np.ndarray) -> np.ndarray:
        """Supplied tangents rotated into scene space, or estimated from UVs.

        The estimator is OpenGLContext's own (Lengyel's method), the same one
        the glTF loader uses to fill in missing tangents, so normal-mapped map
        surfaces and normal-mapped models are shaded from the same frame.
        """
        supplied = [chunk for chunk in group.tangents if chunk is not None]
        if len(supplied) == len(group.tangents):
            packed = np.concatenate(supplied)
            return np.column_stack(
                (to_scene_directions(packed[:, :3]), packed[:, 3]))
        from OpenGLContext.loaders.gltf.meshes import estimate_tangents
        return estimate_tangents(positions, normals, texcoords, indices)


def _bounds(batches: List[Batch]) -> Tuple[np.ndarray, np.ndarray]:
    """Axis-aligned bounds over every batch, in scene space."""
    if not batches:
        return (np.zeros(3, 'f'), np.zeros(3, 'f'))
    lows = np.array([batch.positions.min(axis=0) for batch in batches])
    highs = np.array([batch.positions.max(axis=0) for batch in batches])
    return (lows.min(axis=0), highs.max(axis=0))
