"""Synthesise small `IBSP` files so the readers can be tested without a map.

The layouts written here are the ones the readers must accept: ``SPEC-BSP38``
§1–§4 for version 38 and ``SPEC-BSP46`` §1–§4 for version 46.  Building the
bytes independently of the reader is the point — a test that fed the reader its
own dtypes would only prove the dtypes are self-consistent.
"""

from __future__ import annotations

import struct
from typing import Dict, Optional, Sequence, Tuple

# SPEC-BSP38 §1.1/§1.5 and SPEC-BSP46 §1.1/§1.5.
MAGIC = b'IBSP'
V38_LUMPS = 19
V46_LUMPS = 17

# SPEC-BSP38 §2.1 — lump index by name.
V38_INDEX = {
    'entities': 0, 'planes': 1, 'vertexes': 2, 'visibility': 3, 'nodes': 4,
    'texinfo': 5, 'faces': 6, 'lighting': 7, 'leafs': 8, 'leaffaces': 9,
    'leafbrushes': 10, 'edges': 11, 'surfedges': 12, 'models': 13,
    'brushes': 14, 'brushsides': 15, 'pop': 16, 'areas': 17, 'areaportals': 18,
}

# SPEC-BSP46 §2.1 — a different order, and two fewer lumps.
V46_INDEX = {
    'entities': 0, 'textures': 1, 'planes': 2, 'nodes': 3, 'leafs': 4,
    'leaffaces': 5, 'leafbrushes': 6, 'models': 7, 'brushes': 8,
    'brushsides': 9, 'vertexes': 10, 'meshverts': 11, 'effects': 12,
    'faces': 13, 'lightmaps': 14, 'lightvols': 15, 'visdata': 16,
}


def build(version: int, lumps: Dict[str, bytes]) -> bytes:
    """Assemble a whole file from ``{lump name: payload}``.

    Lumps not supplied are written as zero-length, which SPEC-BSP38 §1.6 and
    SPEC-BSP46 §1.6 make legal.  Payloads are laid out in directory order with
    no padding; the readers must not depend on that (SPEC-BSP38 §1.8).
    """
    index = V38_INDEX if version == 38 else V46_INDEX
    count = V38_LUMPS if version == 38 else V46_LUMPS
    header_size = 8 + count * 8
    directory = [(0, 0)] * count
    payload = b''
    for name, data in lumps.items():
        directory[index[name]] = (header_size + len(payload), len(data))
        payload += data
    head = MAGIC + struct.pack('<i', version)
    for offset, size in directory:
        head += struct.pack('<ii', offset, size)
    return head + payload


def entity_text(entities: Sequence[Dict[str, str]]) -> bytes:
    """The entity lump for a list of key dicts (SPEC-BSP38 §10.2)."""
    blocks = []
    for entity in entities:
        pairs = ''.join('"%s" "%s"\n' % (k, v) for k, v in entity.items())
        blocks.append('{\n%s}\n' % pairs)
    return (''.join(blocks)).encode('ascii') + b'\x00'


# -- version 38 records ------------------------------------------------------

def v38_plane(normal: Sequence[float], distance: float, kind: int = 0) -> bytes:
    """SPEC-BSP38 §4.1 — 20 bytes."""
    return struct.pack('<4f i', normal[0], normal[1], normal[2], distance, kind)


def v38_vertex(position: Sequence[float]) -> bytes:
    """SPEC-BSP38 §4.2 — 12 bytes."""
    return struct.pack('<3f', *position)


def v38_texinfo(s_axis: Sequence[float], s_offset: float,
                t_axis: Sequence[float], t_offset: float,
                flags: int = 0, value: int = 0, name: str = 'e1u1/wall',
                next_frame: int = -1) -> bytes:
    """SPEC-BSP38 §4.5 — 76 bytes."""
    return (struct.pack('<3f f 3f f i i', *s_axis, s_offset, *t_axis, t_offset,
                        flags, value)
            + name.encode('ascii').ljust(32, b'\x00')[:32]
            + struct.pack('<i', next_frame))


def v38_face(plane: int, side: int, first_edge: int, num_edges: int,
             texinfo: int, styles: Sequence[int] = (0, 255, 255, 255),
             lightofs: int = -1) -> bytes:
    """SPEC-BSP38 §4.6 — 20 bytes."""
    return struct.pack('<H h i h h 4B i', plane, side, first_edge, num_edges,
                       texinfo, *styles, lightofs)


def v38_edge(a: int, b: int) -> bytes:
    """SPEC-BSP38 §4.10 — 4 bytes."""
    return struct.pack('<HH', a, b)


def v38_surfedge(value: int) -> bytes:
    """SPEC-BSP38 §4.11 — a signed index whose sign is direction."""
    return struct.pack('<i', value)


def v38_model(mins: Sequence[float], maxs: Sequence[float],
              origin: Sequence[float], root: int, first_face: int,
              num_faces: int) -> bytes:
    """SPEC-BSP38 §4.12 — 48 bytes."""
    return struct.pack('<3f 3f 3f iii', *mins, *maxs, *origin, root,
                       first_face, num_faces)


def v38_leaf(contents: int = 0, cluster: int = -1, area: int = 0,
             mins: Sequence[int] = (0, 0, 0), maxs: Sequence[int] = (0, 0, 0),
             first_leafface: int = 0, num_leaffaces: int = 0,
             first_leafbrush: int = 0, num_leafbrushes: int = 0) -> bytes:
    """SPEC-BSP38 §4.7 — 28 bytes."""
    return struct.pack('<i h h 3h 3h HHHH', contents, cluster, area, *mins,
                       *maxs, first_leafface, num_leaffaces, first_leafbrush,
                       num_leafbrushes)


def v38_node(plane: int, front: int, back: int,
             mins: Sequence[int] = (0, 0, 0), maxs: Sequence[int] = (0, 0, 0),
             first_face: int = 0, num_faces: int = 0) -> bytes:
    """SPEC-BSP38 §4.4 — 28 bytes."""
    return struct.pack('<i i i 3h 3h HH', plane, front, back, *mins, *maxs,
                       first_face, num_faces)


def v38_brush(first_side: int, num_sides: int, contents: int) -> bytes:
    """SPEC-BSP38 §4.13 — 12 bytes."""
    return struct.pack('<iii', first_side, num_sides, contents)


def v38_brushside(plane: int, texinfo: int) -> bytes:
    """SPEC-BSP38 §4.14 — 4 bytes."""
    return struct.pack('<Hh', plane, texinfo)


def v38_quad(origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
             size: float = 64.0, flags: int = 0, lightofs: int = -1,
             styles: Sequence[int] = (0, 255, 255, 255)) -> Dict[str, bytes]:
    """A one-face map: an axis-aligned square in the z = origin[2] plane.

    Its four vertices are walked through the edge/surfedge indirection of
    SPEC-BSP38 §4.10–§4.11 with one edge reversed, so a reader that ignores the
    sign of a surfedge produces a different ring.
    """
    x, y, z = origin
    corners = [(x, y, z), (x + size, y, z), (x + size, y + size, z), (x, y + size, z)]
    vertexes = b''.join(v38_vertex(c) for c in corners)
    # edge 0 is never referenced (SPEC-BSP38 §4.10.1)
    edges = v38_edge(0, 0) + v38_edge(0, 1) + v38_edge(1, 2) + v38_edge(3, 2) + v38_edge(3, 0)
    surfedges = (v38_surfedge(1) + v38_surfedge(2)
                 + v38_surfedge(-3)      # reversed: 2 -> 3
                 + v38_surfedge(4))
    return {
        'entities': entity_text([{'classname': 'worldspawn'}]),
        'planes': v38_plane((0, 0, 1), z, 2),
        'vertexes': vertexes,
        'edges': edges,
        'surfedges': surfedges,
        'texinfo': v38_texinfo((1, 0, 0), 0.0, (0, -1, 0), 0.0, flags=flags),
        'faces': v38_face(0, 0, 0, 4, 0, styles, lightofs),
        'models': v38_model((x, y, z), (x + size, y + size, z), (0, 0, 0), 0, 0, 1),
    }


# -- version 46 records ------------------------------------------------------

def v46_texture(name: str, flags: int = 0, contents: int = 1) -> bytes:
    """SPEC-BSP46 §4.1 — 72 bytes."""
    return name.encode('ascii').ljust(64, b'\x00')[:64] + struct.pack('<ii', flags, contents)


def v46_plane(normal: Sequence[float], distance: float) -> bytes:
    """SPEC-BSP46 §4.2 — 16 bytes."""
    return struct.pack('<4f', *normal, distance)


def v46_vertex(position: Sequence[float], surface: Sequence[float] = (0.0, 0.0),
               lightmap: Sequence[float] = (0.0, 0.0),
               normal: Sequence[float] = (0.0, 0.0, 1.0),
               colour: Sequence[int] = (255, 255, 255, 255)) -> bytes:
    """SPEC-BSP46 §4.9 — 44 bytes."""
    return struct.pack('<3f 2f 2f 3f 4B', *position, *surface, *lightmap,
                       *normal, *colour)


def v46_meshvert(offset: int) -> bytes:
    """SPEC-BSP46 §4.10 — an offset relative to the face's first vertex."""
    return struct.pack('<i', offset)


def v46_face(texture: int, kind: int, vertex: int, n_vertexes: int,
             meshvert: int, n_meshverts: int, lm_index: int = -1,
             size: Sequence[int] = (0, 0), effect: int = -1,
             normal: Sequence[float] = (0.0, 0.0, 1.0)) -> bytes:
    """SPEC-BSP46 §4.12 — 104 bytes."""
    return struct.pack(
        '<iii ii ii i 2i 2i 3f 3f 3f 3f 2i',
        texture, effect, kind, vertex, n_vertexes, meshvert, n_meshverts,
        lm_index, 0, 0, 0, 0,
        0.0, 0.0, 0.0,          # lightmap origin
        1.0, 0.0, 0.0,          # lightmap s axis
        0.0, 1.0, 0.0,          # lightmap t axis
        normal[0], normal[1], normal[2],
        size[0], size[1])


def v46_model(mins: Sequence[float], maxs: Sequence[float], face: int,
              n_faces: int, brush: int = 0, n_brushes: int = 0) -> bytes:
    """SPEC-BSP46 §4.6 — 40 bytes."""
    return struct.pack('<3f 3f iiii', *mins, *maxs, face, n_faces, brush, n_brushes)


def v46_node(plane: int, front: int, back: int,
             mins: Sequence[int] = (0, 0, 0), maxs: Sequence[int] = (0, 0, 0)) -> bytes:
    """SPEC-BSP46 §4.3 — 36 bytes."""
    return struct.pack('<i 2i 3i 3i', plane, front, back, *mins, *maxs)


def v46_leaf(cluster: int = -1, area: int = 0, mins: Sequence[int] = (0, 0, 0),
             maxs: Sequence[int] = (0, 0, 0), leafface: int = 0,
             n_leaffaces: int = 0, leafbrush: int = 0,
             n_leafbrushes: int = 0) -> bytes:
    """SPEC-BSP46 §4.4 — 48 bytes."""
    return struct.pack('<ii 3i 3i iiii', cluster, area, *mins, *maxs, leafface,
                       n_leaffaces, leafbrush, n_leafbrushes)


def v46_lightmap(value: int = 128) -> bytes:
    """SPEC-BSP46 §4.13 — one 128 x 128 RGB image."""
    return bytes([value]) * (128 * 128 * 3)


def v46_quad(size: float = 64.0, texture: str = 'textures/base/wall',
             lm_index: int = -1,
             lightmaps: Optional[bytes] = None) -> Dict[str, bytes]:
    """A one-face map: an axis-aligned square drawn from four meshverts."""
    corners = [(0, 0, 0), (size, 0, 0), (size, size, 0), (0, size, 0)]
    uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    vertexes = b''.join(
        v46_vertex(c, uv, (uv[0] * 0.5, uv[1] * 0.5)) for c, uv in zip(corners, uvs, strict=True))
    meshverts = b''.join(v46_meshvert(i) for i in (0, 1, 2, 0, 2, 3))
    lumps = {
        'entities': entity_text([{'classname': 'worldspawn'}]),
        'textures': v46_texture(texture),
        'vertexes': vertexes,
        'meshverts': meshverts,
        'faces': v46_face(0, 1, 0, 4, 0, 6, lm_index=lm_index),
        'models': v46_model((0, 0, 0), (size, size, 0), 0, 1),
    }
    if lightmaps is not None:
        lumps['lightmaps'] = lightmaps
    return lumps


def v46_brush(brushside: int, n_brushsides: int, texture: int) -> bytes:
    """SPEC-BSP46 §4.7 — 12 bytes."""
    return struct.pack('<iii', brushside, n_brushsides, texture)


def v46_brushside(plane: int, texture: int = 0) -> bytes:
    """SPEC-BSP46 §4.8 — 8 bytes."""
    return struct.pack('<ii', plane, texture)


def v46_box_brush(mins, maxs, texture: int = 0,
                  first_plane: int = 0) -> Tuple[bytes, bytes, bytes]:
    """A box brush as ``(brush, brushsides, planes)``.

    Six axis-aligned planes, each facing *out* of the box, which is how a
    brush states its own extent — and the only way to find out how deep a
    pool actually is, since the leaf holding it reaches much further.
    """
    planes = b''
    sides = b''
    for axis in range(3):
        planes += v46_plane(_axis_normal(axis, +1), float(maxs[axis]))
        planes += v46_plane(_axis_normal(axis, -1), float(-mins[axis]))
        sides += v46_brushside(first_plane + axis * 2, texture)
        sides += v46_brushside(first_plane + axis * 2 + 1, texture)
    return (v46_brush(0, 6, texture), sides, planes)


def _axis_normal(axis: int, sign: int):
    normal = [0.0, 0.0, 0.0]
    normal[axis] = float(sign)
    return normal


def v46_water(size: float = 64.0, depth: float = 32.0,
              brush_maxs=None) -> Dict[str, bytes]:
    """A map whose one leaf holds a brush textured with a liquid shader.

    Version 46 keeps no contents word on a leaf (SPEC-BSP46 §4.4.1), so the
    liquid is only findable through the brush and the texture it names.

    ``brush_maxs`` makes the *brush* smaller than the leaf that holds it, which
    is the ordinary case in a real map — a pool in a room — and the one that
    tells a volume read from the brush apart from one read from the leaf.
    """
    lumps = v46_quad(size=size, texture='textures/base/wall')
    lumps['textures'] = (v46_texture('textures/base/wall')
                         + v46_texture('textures/liquids/water'))
    mins = (0, 0, -int(depth))
    maxs = brush_maxs if brush_maxs is not None else (int(size), int(size), 0)
    brush, sides, planes = v46_box_brush(mins, maxs, texture=1)
    lumps['brushes'] = brush
    lumps['brushsides'] = sides
    lumps['planes'] = planes
    lumps['leafbrushes'] = struct.pack('<i', 0)
    # The leaf reaches well above the water, as a room's leaf does.
    lumps['leafs'] = v46_leaf(cluster=0, mins=mins,
                              maxs=(int(size), int(size), int(size)),
                              leafbrush=0, n_leafbrushes=1)
    return lumps
