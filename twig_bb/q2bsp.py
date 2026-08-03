"""`IBSP` version 38 maps — Quake 2.

Every layout, constant and flag value here cites ``SPEC-BSP38``; nothing in
this module was derived from an engine implementation.  The reader exposes each
lump as a ``numpy`` record array over the memory-mapped file plus the parsed
entity list, and stops there: turning faces into geometry is
:mod:`twig_bb.q2geometry`'s job, and deciding what a surface looks like is
:mod:`twig_bb.surfaces`'.

Only the stock Quake 2 surface flags of ``SPEC-BSP38 §8.1`` are defined here.
Quake 3 uses the same field differently (``SPEC-BSP46 §6.2``), so these values
must never be applied to a v46 map.
"""

from __future__ import annotations

from typing import List

import numpy as np

from . import bspfile
from .entities import Entity, parse_entities

# SPEC-BSP38 §1.2, §1.5.
BSP_VERSION = 38
HEADER_LUMPS = 19

# SPEC-BSP38 §3.2 -- one unit is about one inch.
UNITS_TO_METRES = 0.0254

# SPEC-BSP38 §2.1 -- directory index by lump, in the order the format defines.
LUMP_ENTITIES = 0
LUMP_PLANES = 1
LUMP_VERTEXES = 2
LUMP_VISIBILITY = 3
LUMP_NODES = 4
LUMP_TEXINFO = 5
LUMP_FACES = 6
LUMP_LIGHTING = 7
LUMP_LEAFS = 8
LUMP_LEAFFACES = 9
LUMP_LEAFBRUSHES = 10
LUMP_EDGES = 11
LUMP_SURFEDGES = 12
LUMP_MODELS = 13
LUMP_BRUSHES = 14
LUMP_BRUSHSIDES = 15
LUMP_POP = 16
LUMP_AREAS = 17
LUMP_AREAPORTALS = 18

# Record layouts. Field names are this module's own; the order, types and sizes
# are the spec's, and all scalars are little-endian (SPEC-BSP38 §1.3).
PLANE = np.dtype([                              # §4.1, 20 bytes
    ('normal', '<f4', 3), ('distance', '<f4'), ('type', '<i4')])
VERTEX = np.dtype([('position', '<f4', 3)])     # §4.2, 12 bytes
NODE = np.dtype([                               # §4.4, 28 bytes
    ('plane', '<i4'), ('front', '<i4'), ('back', '<i4'),
    ('mins', '<i2', 3), ('maxs', '<i2', 3),
    ('first_face', '<u2'), ('num_faces', '<u2')])
TEXINFO = np.dtype([                            # §4.5, 76 bytes
    ('s_axis', '<f4', 3), ('s_offset', '<f4'),
    ('t_axis', '<f4', 3), ('t_offset', '<f4'),
    ('flags', '<i4'), ('value', '<i4'), ('texture', 'S32'), ('next', '<i4')])
FACE = np.dtype([                               # §4.6, 20 bytes
    ('plane', '<u2'), ('side', '<i2'), ('first_edge', '<i4'),
    ('num_edges', '<i2'), ('texinfo', '<i2'), ('styles', 'u1', 4),
    ('lightofs', '<i4')])
LEAF = np.dtype([                               # §4.7, 28 bytes
    ('contents', '<i4'), ('cluster', '<i2'), ('area', '<i2'),
    ('mins', '<i2', 3), ('maxs', '<i2', 3),
    ('first_leafface', '<u2'), ('num_leaffaces', '<u2'),
    ('first_leafbrush', '<u2'), ('num_leafbrushes', '<u2')])
LEAFFACE = np.dtype('<u2')                      # §4.8
LEAFBRUSH = np.dtype('<u2')                     # §4.9
EDGE = np.dtype([('vertexes', '<u2', 2)])       # §4.10, 4 bytes
SURFEDGE = np.dtype('<i4')                      # §4.11, signed: sign is direction
MODEL = np.dtype([                              # §4.12, 48 bytes
    ('mins', '<f4', 3), ('maxs', '<f4', 3), ('origin', '<f4', 3),
    ('root_node', '<i4'), ('first_face', '<i4'), ('num_faces', '<i4')])
BRUSH = np.dtype([                              # §4.13, 12 bytes
    ('first_side', '<i4'), ('num_sides', '<i4'), ('contents', '<i4')])
BRUSHSIDE = np.dtype([('plane', '<u2'), ('texinfo', '<i2')])    # §4.14, 4 bytes
AREA = np.dtype([('num_portals', '<i4'), ('first_portal', '<i4')])       # §4.16
AREAPORTAL = np.dtype([('portal', '<i4'), ('other_area', '<i4')])        # §4.17

# Surface flags, SPEC-BSP38 §8.1 (stock Quake 2, carried unchanged by Alien Arena).
SURF_LIGHT = 0x00000001
SURF_SLICK = 0x00000002
SURF_SKY = 0x00000004
SURF_WARP = 0x00000008
SURF_TRANS33 = 0x00000010
SURF_TRANS66 = 0x00000020
SURF_FLOWING = 0x00000040
SURF_NODRAW = 0x00000080
# SPEC-BSP38 §8.2 records five further bits belonging to an engine this viewer
# no longer targets.  They are deliberately not defined: §8.4 requires a reader
# to ignore bits it does not recognise, which is exactly the right behaviour for
# them, and defining them would invite code that acts on them.

# Contents flags, SPEC-BSP38 §9.1 (visible) and §9.2 (non-visible).
CONTENTS_SOLID = 0x00000001
CONTENTS_WINDOW = 0x00000002
CONTENTS_AUX = 0x00000004
CONTENTS_LAVA = 0x00000008
CONTENTS_SLIME = 0x00000010
CONTENTS_WATER = 0x00000020
CONTENTS_MIST = 0x00000040
CONTENTS_AREAPORTAL = 0x00008000
CONTENTS_PLAYERCLIP = 0x00010000
CONTENTS_MONSTERCLIP = 0x00020000
CONTENTS_CURRENT_0 = 0x00040000
CONTENTS_CURRENT_90 = 0x00080000
CONTENTS_CURRENT_180 = 0x00100000
CONTENTS_CURRENT_270 = 0x00200000
CONTENTS_CURRENT_UP = 0x00400000
CONTENTS_CURRENT_DOWN = 0x00800000
CONTENTS_ORIGIN = 0x01000000
CONTENTS_MONSTER = 0x02000000
CONTENTS_DEADMONSTER = 0x04000000
CONTENTS_DETAIL = 0x08000000
CONTENTS_TRANSLUCENT = 0x10000000
CONTENTS_LADDER = 0x20000000

# SPEC-BSP38 §9.4 -- the unions a physics importer wants, stated as unions.
MASK_PLAYERSOLID = CONTENTS_SOLID | CONTENTS_PLAYERCLIP | CONTENTS_WINDOW
MASK_LIQUID = CONTENTS_WATER | CONTENTS_LAVA | CONTENTS_SLIME
MASK_OPAQUE = CONTENTS_SOLID | CONTENTS_SLIME | CONTENTS_LAVA

_RECORD_LUMPS = (
    ('planes', LUMP_PLANES, PLANE),
    ('vertexes', LUMP_VERTEXES, VERTEX),
    ('nodes', LUMP_NODES, NODE),
    ('texinfo', LUMP_TEXINFO, TEXINFO),
    ('faces', LUMP_FACES, FACE),
    ('leafs', LUMP_LEAFS, LEAF),
    ('leaffaces', LUMP_LEAFFACES, LEAFFACE),
    ('leafbrushes', LUMP_LEAFBRUSHES, LEAFBRUSH),
    ('edges', LUMP_EDGES, EDGE),
    ('surfedges', LUMP_SURFEDGES, SURFEDGE),
    ('models', LUMP_MODELS, MODEL),
    ('brushes', LUMP_BRUSHES, BRUSH),
    ('brushsides', LUMP_BRUSHSIDES, BRUSHSIDE),
    ('areas', LUMP_AREAS, AREA),
    ('areaportals', LUMP_AREAPORTALS, AREAPORTAL),
)


class Q2BSP:
    """A version 38 map: its lumps as arrays, and its entities as objects."""

    #: The family name the rest of the viewer dispatches on.
    family = 'quake2'
    version = BSP_VERSION

    planes: np.ndarray
    vertexes: np.ndarray
    nodes: np.ndarray
    texinfo: np.ndarray
    faces: np.ndarray
    leafs: np.ndarray
    leaffaces: np.ndarray
    leafbrushes: np.ndarray
    edges: np.ndarray
    surfedges: np.ndarray
    models: np.ndarray
    brushes: np.ndarray
    brushsides: np.ndarray
    areas: np.ndarray
    areaportals: np.ndarray

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
        # SPEC-BSP38 §7.1: the lighting lump is an undifferentiated byte array,
        # addressed only through the byte offsets in face records.
        self.lighting = bspfile.lump_bytes(data, self.directory, LUMP_LIGHTING,
                                           'lighting')
        # SPEC-BSP38 §4.3: the visibility lump's compression is not decoded --
        # a renderer that draws the whole map does not need it.
        self.visibility = bspfile.lump_bytes(data, self.directory,
                                             LUMP_VISIBILITY, 'visibility')
        self.entities: List[Entity] = parse_entities(
            bytes(bspfile.lump_bytes(data, self.directory, LUMP_ENTITIES,
                                     'entities')))

    @property
    def worldspawn(self) -> Entity:
        """The map-wide settings entity (``SPEC-BSP38 §10.7``).

        Found by classname rather than by position: §10.7 makes "first block"
        a convention, not a rule.  An empty entity when the map has none, so
        callers can read defaults off it without a None check.
        """
        for entity in self.entities:
            if entity.classname == 'worldspawn':
                return entity
        return Entity({})

    def texture_name(self, texinfo_index: int) -> str:
        """The texture path of a texinfo record (``SPEC-BSP38 §6.4``).

        A forward-slash path relative to a texture root, with no extension.
        """
        return bspfile.fixed_string(
            np.frombuffer(self.texinfo[int(texinfo_index)]['texture'], dtype=np.uint8))


def load(path: str) -> Q2BSP:
    """Read the version 38 map at ``path``."""
    return Q2BSP(path, bspfile.read_file(path))
