"""Turn version 38 faces into batched triangles with lightmap coordinates.

A version 38 face stores no vertices of its own: it names a run of *surfedges*,
each a signed index into the edges lump whose sign is a direction, and the ring
is the first vertex of each successive directed edge (``SPEC-BSP38 §4.11.1``,
``§5.1``).  It stores no texture coordinates either — those are an affine
projection of world position through the face's texinfo axes (``§6.1``) — and no
per-vertex normals or tangents (``§5.4``), though ``§6.3`` means the projection
axes give the tangent frame exactly.

Lighting is addressed by a byte offset into one undifferentiated lump
(``§7.1``, ``§7.4``) with the grid derived from the face's own texture-space
extent (``§7.2``).

Everything runs over whole arrays rather than face by face: a map has tens of
thousands of faces, the plan's load budget is about two seconds, and per-face
Python with a handful of numpy calls each is what spends it.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from . import q2bsp
from .lightmapatlas import LightmapAtlas, build_atlas
from .q2bsp import Q2BSP
from .surfaces import SurfaceStyle, style_from_quake2_flags
from .worldgeometry import (
    GeometryBuilder, WorldGeometry, orient_triangles, to_scene_directions,
)

log = logging.getLogger(__name__)

#: ``SPEC-BSP38 §7.2`` -- the stock luxel grid is 16 world units in S and T.
DEFAULT_LUXEL_SCALE = 16.0

#: ``SPEC-BSP38 §7.5`` -- 255 marks an unused light-style slot and terminates
#: the list, so a face whose first slot is 255 has no baked lighting at all.
STYLE_UNUSED = 255

#: Dimensions assumed for a texture whose image file cannot be found.  The UV
#: projection of ``SPEC-BSP38 §6.2`` divides by the image's real size, so a
#: missing image can only be guessed at; the map still loads, at the wrong
#: tiling scale for that one surface.
FALLBACK_TEXTURE_SIZE = (64, 64)

TextureSize = Callable[[str], Tuple[int, int]]


def face_vertices(bsp: Q2BSP, face_index: int) -> np.ndarray:
    """The ring of world-space vertices of one face (``SPEC-BSP38 §5.1``)."""
    face = bsp.faces[face_index]
    start, count = int(face['first_edge']), int(face['num_edges'])
    return bsp.vertexes['position'][_ring_vertex_indices(bsp, start, count)]


def face_normal(bsp: Q2BSP, face_index: int) -> np.ndarray:
    """The outward normal of one face (``SPEC-BSP38 §4.6.1``, ``§5.3``)."""
    face = bsp.faces[face_index]
    normal = np.asarray(bsp.planes[int(face['plane'])]['normal'], dtype='d')
    return -normal if int(face['side']) else normal


def texture_coordinates(bsp: Q2BSP, texinfo_index: int,
                        points: np.ndarray) -> np.ndarray:
    """Texel-unit (S, T) for world points through a texinfo (``SPEC-BSP38 §6.1``)."""
    info = bsp.texinfo[int(texinfo_index)]
    points = np.asarray(points, dtype='d').reshape((-1, 3))
    return np.column_stack((
        points @ np.asarray(info['s_axis'], 'd') + float(info['s_offset']),
        points @ np.asarray(info['t_axis'], 'd') + float(info['t_offset'])))


def luxel_grid(st: np.ndarray,
               scale: Tuple[float, float]) -> Tuple[Tuple[float, float], Tuple[int, int]]:
    """``(texture minimum, (width, height))`` of a face's luxel grid.

    ``SPEC-BSP38 §7.2``: quantise the texture-space extent down and up to whole
    cells, and add one because the grid samples the cells' *corners*.  The
    scale is a parameter rather than the constant 16 so the relationship can be
    stated once and checked independently of it.
    """
    st = np.asarray(st, dtype='d').reshape((-1, 2))
    scales = np.asarray(scale, dtype='d')
    grid_min = np.floor(st.min(axis=0) / scales)
    grid_max = np.ceil(st.max(axis=0) / scales)
    size = (grid_max - grid_min + 1).astype(int)
    minimum = grid_min * scales
    return ((float(minimum[0]), float(minimum[1])),
            (int(size[0]), int(size[1])))


def build(bsp: Q2BSP, texture_size: Optional[TextureSize] = None,
          model: int = 0) -> Tuple[WorldGeometry, LightmapAtlas]:
    """Build one model's geometry and the lightmap atlas its faces address.

    ``model`` 0 is the world; 1 and above are the brush models entities attach
    themselves to (``SPEC-BSP38 §4.12.1``), whose faces are a contiguous range
    that may be drawn directly (``§4.12.2``).
    """
    faces = _model_faces(bsp, model)
    if not len(faces):
        return WorldGeometry(), build_atlas([])
    sizes = texture_size or (lambda name: FALLBACK_TEXTURE_SIZE)
    styles = _styles(bsp, faces)
    lighting = [_face_lighting(bsp, index, styles[index]) for index in faces]
    # One deferred pack of the whole set: see lightmapatlas for why a
    # per-rectangle search is the thing to avoid here.
    atlas = build_atlas([entry.block for entry in lighting])
    return _assemble(bsp, faces, styles, lighting, atlas, sizes), atlas


class _FaceLighting:
    """One face's chosen luxel grid, and how to address it."""

    __slots__ = ('block', 'texture_min', 'scale', 'size')

    def __init__(self, block: Optional[np.ndarray],
                 texture_min: Tuple[float, float] = (0.0, 0.0),
                 scale: Tuple[float, float] = (DEFAULT_LUXEL_SCALE,
                                               DEFAULT_LUXEL_SCALE),
                 size: Tuple[int, int] = (0, 0)) -> None:
        self.block = block
        self.texture_min = texture_min
        self.scale = scale
        self.size = size


def _model_faces(bsp: Q2BSP, model: int) -> np.ndarray:
    """The face indices belonging to one model (``SPEC-BSP38 §4.12``)."""
    if model < 0 or model >= len(bsp.models):
        return np.zeros((0,), np.int64)
    record = bsp.models[model]
    start, count = int(record['first_face']), int(record['num_faces'])
    faces = np.arange(start, start + count, dtype=np.int64)
    valid = (faces >= 0) & (faces < len(bsp.faces))
    faces = faces[valid]
    # SPEC-BSP38 §5.2 needs at least a triangle; a shorter ring is not a polygon.
    return faces[bsp.faces['num_edges'][faces] >= 3]


def _styles(bsp: Q2BSP, faces: np.ndarray) -> Dict[int, SurfaceStyle]:
    """The surface style of each face, from its texinfo (``SPEC-BSP38 §8``)."""
    cache: Dict[int, SurfaceStyle] = {}
    styles: Dict[int, SurfaceStyle] = {}
    for index in faces:
        texinfo = int(bsp.faces[index]['texinfo'])
        style = cache.get(texinfo)
        if style is None:
            if 0 <= texinfo < len(bsp.texinfo):
                style = style_from_quake2_flags(
                    bsp.texture_name(texinfo), int(bsp.texinfo[texinfo]['flags']))
            else:
                style = SurfaceStyle(name='', draw=False)
            cache[texinfo] = style
        styles[int(index)] = style
    return styles


def _face_lighting(bsp: Q2BSP, face_index: int,
                   style: SurfaceStyle) -> _FaceLighting:
    """A face's luxel grid from the lighting lump, or none.

    ``SPEC-BSP38 §7.5`` and ``§7.8``: a face whose first style slot is unused,
    or which is sky, warped or nodraw, has no baked lighting at all.
    """
    face = bsp.faces[face_index]
    if not style.lightmapped or int(face['styles'][0]) == STYLE_UNUSED:
        return _FaceLighting(None)                       # §7.5, §7.8
    points = face_vertices(bsp, face_index)
    scale = (DEFAULT_LUXEL_SCALE, DEFAULT_LUXEL_SCALE)
    texture_min, size = luxel_grid(
        texture_coordinates(bsp, int(face['texinfo']), points), scale)
    offset = int(face['lightofs'])
    needed = size[0] * size[1] * 3                       # §7.3
    if offset < 0 or offset + needed > len(bsp.lighting):
        return _FaceLighting(None)                       # §7.4
    # §7.5, §7.6: the style-0 block comes first and is the always-on
    # contribution; the animated styles that may follow it are not read.
    block = bsp.lighting[offset:offset + needed].reshape((size[1], size[0], 3))
    return _FaceLighting(block, texture_min, scale, size)


def _assemble(bsp: Q2BSP, faces: np.ndarray, styles: Dict[int, SurfaceStyle],
              lighting: List[_FaceLighting], atlas: LightmapAtlas,
              texture_size: TextureSize) -> WorldGeometry:
    """Group faces into batches and build each one's vertex arrays."""
    groups: Dict[Tuple, List[int]] = {}
    for slot, face_index in enumerate(faces):
        style = styles[int(face_index)]
        key = (style.batch_key(), atlas.page_of(slot))
        groups.setdefault(key, []).append(slot)
    builder = GeometryBuilder()
    sizes: Dict[str, Tuple[int, int]] = {}
    for (_key, page), slots in groups.items():
        style = styles[int(faces[slots[0]])]
        if style.name not in sizes:
            sizes[style.name] = _texture_size(texture_size, style.name)
        _add_batch(builder, bsp, faces, slots, style, page, lighting, atlas,
                   sizes[style.name])
    return builder.build()


def _texture_size(texture_size: TextureSize, name: str) -> Tuple[int, int]:
    """The image dimensions used to normalise UVs (``SPEC-BSP38 §6.2``)."""
    try:
        width, height = texture_size(name)
    except Exception:                                   # noqa: BLE001 - never fail a load
        return FALLBACK_TEXTURE_SIZE
    if width <= 0 or height <= 0:
        return FALLBACK_TEXTURE_SIZE
    return (int(width), int(height))


def _add_batch(builder: GeometryBuilder, bsp: Q2BSP, faces: np.ndarray,
               slots: List[int], style: SurfaceStyle, page: int,
               lighting: List[_FaceLighting], atlas: LightmapAtlas,
               texture_size: Tuple[int, int]) -> None:
    """Build one batch's vertex pool from the faces that share its key."""
    indices = faces[np.asarray(slots, dtype=np.int64)]
    records = bsp.faces[indices]
    counts = records['num_edges'].astype(np.int64)
    ring = _ring_vertex_indices(bsp, records['first_edge'].astype(np.int64), counts)
    points = bsp.vertexes['position'][ring].astype('d')

    texinfo = bsp.texinfo[records['texinfo'].astype(np.int64)]
    s_axis = np.repeat(texinfo['s_axis'].astype('d'), counts, axis=0)
    t_axis = np.repeat(texinfo['t_axis'].astype('d'), counts, axis=0)
    s = np.einsum('ij,ij->i', points, s_axis) + np.repeat(
        texinfo['s_offset'].astype('d'), counts)
    t = np.einsum('ij,ij->i', points, t_axis) + np.repeat(
        texinfo['t_offset'].astype('d'), counts)
    uv = np.column_stack((s / texture_size[0], t / texture_size[1]))     # §6.2

    normals = np.repeat(_face_normals(bsp, records), counts, axis=0)
    tangents = _tangents(s_axis, t_axis, normals)
    uv1 = _lightmap_uv(slots, counts, s, t, lighting, atlas)

    indices = orient_triangles(_fan_indices(counts), points, normals)
    builder.add_surface(style, page, points, normals, uv, uv1, indices,
                        tangents=tangents)


def _face_normals(bsp: Q2BSP, records: np.ndarray) -> np.ndarray:
    """Outward normals for a set of face records (``SPEC-BSP38 §4.6.1``)."""
    normals = bsp.planes['normal'][records['plane'].astype(np.int64)].astype('d')
    flip = records['side'].astype(np.int64) != 0
    normals[flip] = -normals[flip]
    return normals


def _tangents(s_axis: np.ndarray, t_axis: np.ndarray,
              normals: np.ndarray) -> np.ndarray:
    """Per-vertex tangent frames from the projection axes (``SPEC-BSP38 §6.3``).

    The S axis points along increasing S on the surface, which is what a
    tangent-space normal map is authored against, so a planar face's frame is
    exact.  ``§6.3`` also says the axes need be neither orthogonal nor unit
    length, hence the normalisation and the Gram-Schmidt against the normal.
    The w component is the bitangent's handedness, as the shader expects.
    """
    tangent = s_axis - normals * np.einsum('ij,ij->i', s_axis, normals)[:, None]
    length = np.linalg.norm(tangent, axis=1, keepdims=True)
    length[length == 0] = 1.0
    tangent = tangent / length
    # T grows downward in image space where S grows right, so the handedness
    # follows from whether t_axis agrees with normal x tangent.
    handed = np.sign(np.einsum('ij,ij->i', np.cross(normals, tangent), t_axis))
    handed[handed == 0] = 1.0
    scene = to_scene_directions(tangent)
    return np.column_stack((scene, -handed)).astype('f')


def _lightmap_uv(slots: List[int], counts: np.ndarray, s: np.ndarray,
                 t: np.ndarray, lighting: List[_FaceLighting],
                 atlas: LightmapAtlas) -> np.ndarray:
    """Atlas coordinates for every vertex of a batch (``SPEC-BSP38 §7.7``)."""
    total = int(counts.sum())
    uv = np.zeros((total, 2), 'f')
    offset = 0
    for slot, count in zip(slots, counts.tolist(), strict=True):
        entry = lighting[slot]
        end = offset + count
        if entry.block is not None:
            luxels = np.column_stack((
                (s[offset:end] - entry.texture_min[0]) / entry.scale[0],
                (t[offset:end] - entry.texture_min[1]) / entry.scale[1]))
            # Clamp into the grid the face actually described: a vertex exactly
            # on the last luxel can land a hair outside it through rounding.
            luxels[:, 0] = np.clip(luxels[:, 0], 0, max(entry.size[0] - 1, 0))
            luxels[:, 1] = np.clip(luxels[:, 1], 0, max(entry.size[1] - 1, 0))
            uv[offset:end] = atlas.uv_from_luxels(slot, luxels)
        offset = end
    return uv


def _ring_vertex_indices(bsp: Q2BSP, starts, counts) -> np.ndarray:
    """Vertex indices of one or more faces' rings, concatenated.

    ``SPEC-BSP38 §4.11.1``: the magnitude of a surfedge indexes the edges lump
    and the sign says which way the edge is walked; ``§5.1``: the ring is the
    first vertex of each successive directed edge.
    """
    starts = np.atleast_1d(np.asarray(starts, dtype=np.int64))
    counts = np.atleast_1d(np.asarray(counts, dtype=np.int64))
    positions = _concat_ranges(starts, counts)
    surfedges = bsp.surfedges[np.clip(positions, 0, max(len(bsp.surfedges) - 1, 0))]
    edges = bsp.edges['vertexes'][np.abs(surfedges)]
    return np.where(surfedges >= 0, edges[:, 0], edges[:, 1]).astype(np.int64)


def _concat_ranges(starts: np.ndarray, counts: np.ndarray) -> np.ndarray:
    """``concatenate([arange(s, s + c) for s, c in zip(starts, counts)])``.

    Written as one cumulative sum so a map's whole face set costs a handful of
    array operations instead of one Python loop iteration per face.
    """
    total = int(counts.sum())
    if not total:
        return np.zeros((0,), np.int64)
    steps = np.ones(total, dtype=np.int64)
    boundaries = np.cumsum(counts)[:-1]
    steps[0] = starts[0]
    steps[boundaries] = starts[1:] - (starts[:-1] + counts[:-1] - 1)
    return np.cumsum(steps)


def _fan_indices(counts: np.ndarray) -> np.ndarray:
    """Triangle-fan indices into a pool of concatenated rings (``§5.2``)."""
    triangles = counts - 2
    ring_starts = np.concatenate(([0], np.cumsum(counts)[:-1]))
    base = np.repeat(ring_starts, triangles)
    tri_starts = np.concatenate(([0], np.cumsum(triangles)[:-1]))
    local = np.arange(int(triangles.sum())) - np.repeat(tri_starts, triangles)
    return np.column_stack((base, base + local + 1, base + local + 2)).ravel()


# Re-exported so callers can name the flags this module reads without importing
# the container reader as well.
SURF_SKY = q2bsp.SURF_SKY
SURF_WARP = q2bsp.SURF_WARP
