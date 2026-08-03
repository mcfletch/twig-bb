"""`IBSP` version 46 maps — Quake 3.

Every layout and constant here cites ``SPEC-BSP46``, whose own provenance is a
published format reference, this project's earlier BSD reader, and the bytes of
sample maps.  No engine source was consulted for any of it.

The two families share a container but not a directory: v46 has 17 lumps where
v38 has 19, and an index means something different in each (``SPEC-BSP46
§2.2``).  Two lump readers therefore exist rather than one parameterised one.

Deliberately absent: any interpretation of the surface-flags or contents words
(``SPEC-BSP46 §6.2`` and E.1).  Quake 3 surface behaviour comes from the
``.shader`` scripts and the texture name, both content rather than engine data,
so no v46 flag table is defined here — and SPEC-BSP38 §8's table, which
describes a different family's assignment of the same field, must never be
applied to a v46 map.
"""

from __future__ import annotations

from typing import List

import numpy as np

from . import bspfile
from .entities import Entity, parse_entities

# SPEC-BSP46 §1.2, §1.5.
BSP_VERSION = 46
HEADER_LUMPS = 17

# SPEC-BSP46 §3.2 -- the same Quake units as SPEC-BSP38 §3.2.
UNITS_TO_METRES = 0.0254

# SPEC-BSP46 §2.1 -- directory index by lump.
LUMP_ENTITIES = 0
LUMP_TEXTURES = 1
LUMP_PLANES = 2
LUMP_NODES = 3
LUMP_LEAFS = 4
LUMP_LEAFFACES = 5
LUMP_LEAFBRUSHES = 6
LUMP_MODELS = 7
LUMP_BRUSHES = 8
LUMP_BRUSHSIDES = 9
LUMP_VERTEXES = 10
LUMP_MESHVERTS = 11
LUMP_EFFECTS = 12
LUMP_FACES = 13
LUMP_LIGHTMAPS = 14
LUMP_LIGHTVOLS = 15
LUMP_VISDATA = 16

# SPEC-BSP46 §4.12.1 -- the face type enumeration.
FACE_POLYGON = 1
FACE_PATCH = 2
FACE_MESH = 3
FACE_BILLBOARD = 4

# SPEC-BSP46 §4.13.1 -- every lightmap record is one 128 x 128 RGB image.
LIGHTMAP_SIZE = 128
LIGHTMAP_BYTES = LIGHTMAP_SIZE * LIGHTMAP_SIZE * 3

# Record layouts. Field names are this module's own; order, types and sizes are
# the spec's, and all scalars are little-endian (SPEC-BSP46 §1.3).
TEXTURE = np.dtype([                            # §4.1, 72 bytes
    ('name', 'S64'), ('flags', '<i4'), ('contents', '<i4')])
PLANE = np.dtype([('normal', '<f4', 3), ('distance', '<f4')])   # §4.2, 16 bytes
NODE = np.dtype([                               # §4.3, 36 bytes
    ('plane', '<i4'), ('children', '<i4', 2),
    ('mins', '<i4', 3), ('maxs', '<i4', 3)])
LEAF = np.dtype([                               # §4.4, 48 bytes
    ('cluster', '<i4'), ('area', '<i4'), ('mins', '<i4', 3), ('maxs', '<i4', 3),
    ('leafface', '<i4'), ('num_leaffaces', '<i4'),
    ('leafbrush', '<i4'), ('num_leafbrushes', '<i4')])
LEAFFACE = np.dtype('<i4')                      # §4.5.1
LEAFBRUSH = np.dtype('<i4')                     # §4.5.1
MODEL = np.dtype([                              # §4.6, 40 bytes
    ('mins', '<f4', 3), ('maxs', '<f4', 3),
    ('face', '<i4'), ('num_faces', '<i4'),
    ('brush', '<i4'), ('num_brushes', '<i4')])
BRUSH = np.dtype([                              # §4.7, 12 bytes
    ('brushside', '<i4'), ('num_brushsides', '<i4'), ('texture', '<i4')])
BRUSHSIDE = np.dtype([('plane', '<i4'), ('texture', '<i4')])     # §4.8, 8 bytes
VERTEX = np.dtype([                             # §4.9, 44 bytes
    ('position', '<f4', 3), ('surface', '<f4', 2), ('lightmap', '<f4', 2),
    ('normal', '<f4', 3), ('colour', 'u1', 4)])
MESHVERT = np.dtype('<i4')                      # §4.10, offset from face's first vertex
EFFECT = np.dtype([                             # §4.11, 72 bytes
    ('name', 'S64'), ('brush', '<i4'), ('unknown', '<i4')])
FACE = np.dtype([                               # §4.12, 104 bytes
    ('texture', '<i4'), ('effect', '<i4'), ('type', '<i4'),
    ('vertex', '<i4'), ('num_vertexes', '<i4'),
    ('meshvert', '<i4'), ('num_meshverts', '<i4'),
    ('lm_index', '<i4'), ('lm_start', '<i4', 2), ('lm_size', '<i4', 2),
    ('lm_origin', '<f4', 3), ('lm_s_axis', '<f4', 3), ('lm_t_axis', '<f4', 3),
    ('normal', '<f4', 3), ('size', '<i4', 2)])
LIGHTVOL = np.dtype([                           # §4.14, 8 bytes
    ('ambient', 'u1', 3), ('directional', 'u1', 3), ('direction', 'u1', 2)])

_RECORD_LUMPS = (
    ('textures', LUMP_TEXTURES, TEXTURE),
    ('planes', LUMP_PLANES, PLANE),
    ('nodes', LUMP_NODES, NODE),
    ('leafs', LUMP_LEAFS, LEAF),
    ('leaffaces', LUMP_LEAFFACES, LEAFFACE),
    ('leafbrushes', LUMP_LEAFBRUSHES, LEAFBRUSH),
    ('models', LUMP_MODELS, MODEL),
    ('brushes', LUMP_BRUSHES, BRUSH),
    ('brushsides', LUMP_BRUSHSIDES, BRUSHSIDE),
    ('vertexes', LUMP_VERTEXES, VERTEX),
    ('meshverts', LUMP_MESHVERTS, MESHVERT),
    ('effects', LUMP_EFFECTS, EFFECT),
    ('faces', LUMP_FACES, FACE),
    ('lightvols', LUMP_LIGHTVOLS, LIGHTVOL),
)


class Q3BSP:
    """A version 46 map: its lumps as arrays, and its entities as objects."""

    #: The family name the rest of the viewer dispatches on.
    family = 'quake3'
    version = BSP_VERSION

    textures: np.ndarray
    planes: np.ndarray
    nodes: np.ndarray
    leafs: np.ndarray
    leaffaces: np.ndarray
    leafbrushes: np.ndarray
    models: np.ndarray
    brushes: np.ndarray
    brushsides: np.ndarray
    vertexes: np.ndarray
    meshverts: np.ndarray
    effects: np.ndarray
    faces: np.ndarray
    lightvols: np.ndarray

    def __init__(self, path: str, data: np.ndarray) -> None:
        self.path = path
        self.data = data
        version = bspfile.read_version(data)
        if version != BSP_VERSION:
            raise bspfile.MalformedBSP(
                'expected IBSP version %d, found %d' % (BSP_VERSION, version))
        self.directory = bspfile.read_directory(data, HEADER_LUMPS)
        for name, index, dtype in _RECORD_LUMPS:
            setattr(self, name, bspfile.lump_records(data, self.directory,
                                                     index, dtype, name))
        self.lightmaps = self._read_lightmaps()
        # SPEC-BSP46 §4.15: the visibility lump is carried but not decoded.
        self.visdata = bspfile.lump_bytes(data, self.directory, LUMP_VISDATA,
                                          'visdata')
        self.entities: List[Entity] = parse_entities(
            bytes(bspfile.lump_bytes(data, self.directory, LUMP_ENTITIES,
                                     'entities')))

    def _read_lightmaps(self) -> np.ndarray:
        """The lightmaps lump as ``(count, 128, 128, 3)`` bytes (§4.13.1).

        Fixed-size records with no header, so the whole lump reshapes; a
        trailing partial image is dropped, as for any record lump (§1.6).
        """
        raw = bspfile.lump_bytes(self.data, self.directory, LUMP_LIGHTMAPS,
                                 'lightmaps')
        count = len(raw) // LIGHTMAP_BYTES
        return raw[:count * LIGHTMAP_BYTES].reshape(
            (count, LIGHTMAP_SIZE, LIGHTMAP_SIZE, 3))

    @property
    def worldspawn(self) -> Entity:
        """The map-wide settings entity (``SPEC-BSP38 §10.7`` via ``SPEC-BSP46 §5.1``)."""
        for entity in self.entities:
            if entity.classname == 'worldspawn':
                return entity
        return Entity({})

    def texture_name(self, texture_index: int) -> str:
        """The material path of a texture record (``SPEC-BSP46 §6.1``).

        A forward-slash path relative to the archive root with no extension;
        it is also the name of a ``.shader`` material.
        """
        return bspfile.fixed_string(
            np.frombuffer(self.textures[int(texture_index)]['name'], dtype=np.uint8))


def load(path: str) -> Q3BSP:
    """Read the version 46 map at ``path``."""
    return Q3BSP(path, bspfile.read_file(path))
