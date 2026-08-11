"""Turn version 46 faces into batched triangles with lightmap coordinates.

A version 46 face is highly self-describing: its vertices carry positions,
normals, material UVs and lightmap UVs directly (``SPEC-BSP46 §4.9``,
``§4.9.1``), and its triangles are a run of *meshverts*, each an offset from the
face's own first vertex (``SPEC-BSP46 §4.10.1``).  So this builder projects
nothing and derives no luxel grid; it gathers, addresses
the lightmap image the face names (``§4.12``, ``§4.13``), and tessellates
Bezier patches (``§6.3``–``§6.5``).

What a surface *looks* like does not come from the file: ``SPEC-BSP46 §6.2``
records no flag values for this family, and E.1 explains why none are
interpreted.  The caller passes a ``style_for`` callback, which the material
layer answers from the map's ``.shader`` scripts.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, Optional, Tuple

import numpy as np

from .lightmapatlas import LightmapAtlas, build_atlas
from .q3bsp import (
    FACE_BILLBOARD, FACE_MESH, FACE_PATCH, FACE_POLYGON, Q3BSP,
)
from .surfaces import SurfaceStyle
from .worldgeometry import GeometryBuilder, WorldGeometry, orient_triangles

log = logging.getLogger(__name__)

#: Samples per Bezier sub-patch edge.  ``SPEC-BSP46 §6.6``: the count is the
#: renderer's own choice and affects smoothness only.
DEFAULT_SUBDIVISIONS = 8

#: Face types this builder draws (``SPEC-BSP46 §4.12.1``).  Type 4 is a
#: billboard, which carries no polygon geometry, so it is skipped.
INDEXED_TYPES = (FACE_POLYGON, FACE_MESH)

StyleFor = Callable[[str], SurfaceStyle]

# Per-vertex channels carried through patch interpolation: position, normal,
# material UV, lightmap UV (``SPEC-BSP46 §4.9``).
_PATCH_CHANNELS = 10


def bezier_basis(samples: int) -> np.ndarray:
    """The quadratic Bernstein weights at ``samples`` evenly spaced parameters.

    ``SPEC-BSP46 §6.5``: b0 = (1 - u)^2, b1 = 2u(1 - u), b2 = u^2.
    """
    u = np.linspace(0.0, 1.0, max(int(samples), 2))
    return np.column_stack(((1.0 - u) ** 2, 2.0 * u * (1.0 - u), u ** 2))


def tessellate_patch(control: np.ndarray,
                     subdivisions: int = DEFAULT_SUBDIVISIONS
                     ) -> Tuple[np.ndarray, np.ndarray]:
    """Evaluate a control grid into a sample grid and its triangle indices.

    ``SPEC-BSP46 §6.4``: control points ``[2i..2i+2] x [2j..2j+2]`` form one
    biquadratic patch, and neighbouring patches share their edge control points,
    so the sample grids join without a seam.  ``§6.5``: every channel is
    interpolated with the same weights.
    """
    control = np.asarray(control, dtype='d')
    rows, columns = control.shape[0], control.shape[1]
    down, across = (rows - 1) // 2, (columns - 1) // 2
    if down < 1 or across < 1:
        return (np.zeros((0, 0, control.shape[2]), 'f'),
                np.zeros((0,), np.uint32))
    steps = max(int(subdivisions), 1)
    basis = bezier_basis(steps + 1)
    height, width = down * steps + 1, across * steps + 1
    grid = np.zeros((height, width, control.shape[2]), 'd')
    for i in range(down):
        for j in range(across):
            block = control[2 * i:2 * i + 3, 2 * j:2 * j + 3]
            patch = np.einsum('ui,vj,ijc->uvc', basis, basis, block)
            grid[i * steps:i * steps + steps + 1,
                 j * steps:j * steps + steps + 1] = patch
    return grid.astype('f'), _grid_indices(height, width)


def build(bsp: Q3BSP, style_for: Optional[StyleFor] = None, model: int = 0,
          subdivisions: int = DEFAULT_SUBDIVISIONS
          ) -> Tuple[WorldGeometry, LightmapAtlas]:
    """Build one model's geometry and the lightmap atlas its faces address.

    ``model`` 0 is the world; 1 and above are brush models
    (``SPEC-BSP46 §4.6.1``), whose faces are a contiguous range.
    """
    faces = _model_faces(bsp, model)
    if not len(faces):
        return WorldGeometry(), build_atlas([])
    styles = style_for or (lambda name: SurfaceStyle(name=name))
    atlas, page_of = _pack_lightmaps(bsp, faces)
    builder = GeometryBuilder()
    style_cache: Dict[int, SurfaceStyle] = {}
    for face_index in faces:
        face = bsp.faces[face_index]
        texture = int(face['texture'])
        style = style_cache.get(texture)
        if style is None:
            style = style_cache[texture] = styles(_texture_name(bsp, texture))
        _add_face(builder, bsp, face, style, page_of(int(face['lm_index'])),
                  atlas, subdivisions)
    return builder.build(), atlas


def _texture_name(bsp: Q3BSP, texture: int) -> str:
    """The material name of a face's texture record (``SPEC-BSP46 §6.1``)."""
    if 0 <= texture < len(bsp.textures):
        return bsp.texture_name(texture)
    return ''


def _model_faces(bsp: Q3BSP, model: int) -> np.ndarray:
    """The face indices belonging to one model (``SPEC-BSP46 §4.6``)."""
    if model < 0 or model >= len(bsp.models):
        return np.zeros((0,), np.int64)
    record = bsp.models[model]
    start, count = int(record['face']), int(record['num_faces'])
    faces = np.arange(start, start + count, dtype=np.int64)
    return faces[(faces >= 0) & (faces < len(bsp.faces))]


def _pack_lightmaps(bsp: Q3BSP, faces: np.ndarray
                    ) -> Tuple[LightmapAtlas, Callable[[int], int]]:
    """Pack the lightmap images the given faces reference.

    ``SPEC-BSP46 §4.12.2``: an index of -1, or one outside the lump, means the
    face has no baked lighting.  Only referenced images are packed, so a map
    that ships unused ones does not pay for them in atlas pages.
    """
    referenced = sorted({int(index) for index in bsp.faces['lm_index'][faces]
                         if 0 <= int(index) < len(bsp.lightmaps)})
    atlas = build_atlas([bsp.lightmaps[index] for index in referenced])
    slots = {image: slot for slot, image in enumerate(referenced)}

    def page_of(lm_index: int) -> int:
        slot = slots.get(int(lm_index))
        return -1 if slot is None else slot

    return atlas, page_of


def _add_face(builder: GeometryBuilder, bsp: Q3BSP, face: np.ndarray,
              style: SurfaceStyle, slot: int, atlas: LightmapAtlas,
              subdivisions: int) -> None:
    """Add one face's triangles to the batch its style and page select."""
    kind = int(face['type'])
    if kind in INDEXED_TYPES:
        vertices, indices = _indexed_face(bsp, face)
    elif kind == FACE_PATCH:
        vertices, indices = _patch_face(bsp, face, subdivisions)
    else:
        # SPEC-BSP46 §4.12.1: a billboard carries no polygon geometry, and an
        # unknown type is not something to guess at.
        if kind != FACE_BILLBOARD:
            log.debug('skipping face of unknown type %d', kind)
        return
    if vertices is None or not len(indices):
        return
    positions, normals, uv, lightmap_uv = vertices
    page = atlas.page_of(slot) if slot >= 0 else -1
    uv1 = (atlas.uv_from_normalised(slot, lightmap_uv) if slot >= 0
           else np.zeros_like(lightmap_uv))
    builder.add_surface(style, page, positions, normals, uv, uv1,
                        orient_triangles(indices, positions, normals))


def _indexed_face(bsp: Q3BSP, face: np.ndarray):
    """A polygon or mesh face's vertices and triangles (``SPEC-BSP46 §4.12.1``)."""
    first, count = int(face['vertex']), int(face['num_vertexes'])
    mesh_first, mesh_count = int(face['meshvert']), int(face['num_meshverts'])
    if count <= 0 or mesh_count <= 0:
        return None, np.zeros((0,), np.uint32)
    if first < 0 or first + count > len(bsp.vertexes):
        return None, np.zeros((0,), np.uint32)
    if mesh_first < 0 or mesh_first + mesh_count > len(bsp.meshverts):
        return None, np.zeros((0,), np.uint32)
    block = bsp.vertexes[first:first + count]
    # SPEC-BSP46 §4.10.1: a meshvert is an offset from the face's first vertex,
    # so it indexes this block directly.
    indices = bsp.meshverts[mesh_first:mesh_first + mesh_count].astype(np.int64)
    if indices.min() < 0 or indices.max() >= count:
        log.debug('face has a meshvert outside its own vertex block')
        return None, np.zeros((0,), np.uint32)
    return ((block['position'].astype('f'), block['normal'].astype('f'),
             block['surface'].astype('f'), block['lightmap'].astype('f')),
            indices.astype(np.uint32))


def _patch_face(bsp: Q3BSP, face: np.ndarray, subdivisions: int):
    """A Bezier patch face's tessellated vertices (``SPEC-BSP46 §6.3``–``§6.5``)."""
    first = int(face['vertex'])
    width, height = (int(v) for v in face['size'])
    if width < 3 or height < 3 or width % 2 == 0 or height % 2 == 0:
        return None, np.zeros((0,), np.uint32)          # §6.3
    count = width * height
    if first < 0 or first + count > len(bsp.vertexes):
        return None, np.zeros((0,), np.uint32)
    block = bsp.vertexes[first:first + count]
    control = np.zeros((height, width, _PATCH_CHANNELS), 'd')
    # §6.3: row-major with width as the fast axis.
    control[:, :, 0:3] = block['position'].reshape((height, width, 3))
    control[:, :, 3:6] = block['normal'].reshape((height, width, 3))
    control[:, :, 6:8] = block['surface'].reshape((height, width, 2))
    control[:, :, 8:10] = block['lightmap'].reshape((height, width, 2))
    grid, indices = tessellate_patch(control, subdivisions)
    flat = grid.reshape((-1, _PATCH_CHANNELS))
    normals = _normalised(flat[:, 3:6])
    return ((flat[:, 0:3], normals, flat[:, 6:8], flat[:, 8:10]), indices)


def _normalised(vectors: np.ndarray) -> np.ndarray:
    """Unit-length rows; interpolating unit normals shortens them."""
    lengths = np.linalg.norm(vectors, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    return (vectors / lengths).astype('f')


def _grid_indices(height: int, width: int) -> np.ndarray:
    """Two triangles per quad of a ``height`` x ``width`` sample grid."""
    if height < 2 or width < 2:
        return np.zeros((0,), np.uint32)
    corners = np.arange(height * width).reshape((height, width))
    top_left = corners[:-1, :-1].ravel()
    return np.column_stack((
        top_left, top_left + 1, top_left + width,
        top_left + 1, top_left + width + 1, top_left + width,
    )).ravel().astype(np.uint32)
