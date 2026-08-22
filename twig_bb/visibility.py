"""Which rooms of a map can be seen from where you are standing.

A level is mostly walls. Standing in one room of a deathmatch map, nearly all of
the rest of it is behind something, and the frustum cannot say so: a pickup two
rooms ahead is straight in front of the camera and passes every test the
renderer has, because the renderer is not told about walls.

The map itself was told. A compiler divided the world into **clusters** and
worked out, for every one of them, which others can be seen from inside it
(``SPEC-BSP46 §4.15``). That answer ships in the file and costs a bit-test to
read. On a real map it rejects the great majority of what a frustum keeps -- on
``oa_dm3``, seven of fifty-five pickups are visible from an average spawn.

This is the *potentially* visible set, and the word is load-bearing: it is
conservative. Anything it rejects is certainly out of sight; some of what it
keeps is behind a wall anyway. That is the right direction to be wrong in, and it
is why this can be trusted to decide what not to draw.

Coordinates here are the **map's own** -- the units and axes the file uses -- not
the scene's metres. :func:`twig_bb.worldgeometry.to_map_points` is how a
position in the world comes back to them.
"""

from __future__ import annotations

import logging
import struct
from typing import Any, Optional, Sequence

import numpy as np

log = logging.getLogger(__name__)

__all__ = ['Visibility', 'NO_CLUSTER']

#: What a leaf outside any cluster carries (``SPEC-BSP46 §4.4``).  A point in
#: one is outside the world the compiler divided up -- above the sky, inside
#: solid -- and nothing can be said about what it sees.
NO_CLUSTER = -1


class Visibility:
    """A map's clusters, and which of them see which.

    Built from the lumps a loaded map already holds.  A map with no visibility
    data -- one compiled without it, or a synthetic one -- makes a
    :class:`Visibility` that says everything is visible, so a caller never has
    to ask whether there is any.
    """

    def __init__(self, nodes: Any = None, leafs: Any = None, planes: Any = None,
                 visdata: Any = None) -> None:
        self.nodes = nodes
        self.leafs = leafs
        self.planes = planes
        self._vectors: Optional[np.ndarray] = None
        if visdata is not None and len(visdata) >= 8:
            self._vectors = self._unpack(visdata)

    @staticmethod
    def _unpack(visdata: Any) -> Optional[np.ndarray]:
        """The bit vectors as ``(clusters, bytes)``, or None if malformed.

        ``SPEC-BSP46 §4.15.1``: two int32 counts, then that many flat vectors.
        A lump too short for what its own header claims is content this cannot
        read rather than an error -- the map still draws, with nothing culled.
        """
        raw = bytes(visdata)
        count, width = struct.unpack('<ii', raw[:8])
        if count <= 0 or width <= 0:
            return None
        wanted = 8 + count * width
        if len(raw) < wanted:
            log.warning('visibility data is %d bytes, short of the %d its '
                        'header describes; nothing will be culled by it',
                        len(raw), wanted)
            return None
        return np.frombuffer(raw[8:wanted], dtype=np.uint8).reshape(count, width)

    @classmethod
    def from_bsp(cls, bsp: Any) -> 'Visibility':
        """The visibility of a parsed map, or an empty one if it carries none."""
        if bsp is None:
            return cls()
        return cls(nodes=getattr(bsp, 'nodes', None),
                   leafs=getattr(bsp, 'leafs', None),
                   planes=getattr(bsp, 'planes', None),
                   visdata=getattr(bsp, 'visdata', None))

    def __bool__(self) -> bool:
        """Whether this can reject anything at all."""
        return self._vectors is not None and self.nodes is not None

    @property
    def clusters(self) -> int:
        """How many clusters the map was divided into."""
        return 0 if self._vectors is None else int(len(self._vectors))

    # -- where you are ----------------------------------------------------
    def leaf_at(self, where: Sequence[float]) -> int:
        """Which leaf holds ``where``, in map coordinates.

        The tree is descended by which side of each node's plane the point
        falls: at or in front of it takes the front child.  ``SPEC-BSP46
        §4.3.1``: a non-negative child indexes the nodes, and a negative one
        denotes leaf ``-(child) - 1``.
        """
        if self.nodes is None or self.planes is None or not len(self.nodes):
            return -1
        # Plain floats rather than numpy: this walks a dozen planes per body
        # per frame, and at three components a call into numpy costs more than
        # the arithmetic it does.
        px, py, pz = (float(where[0]), float(where[1]), float(where[2]))
        nodes, planes = self.nodes, self.planes
        index = 0
        # Bounded by the tree's own size: a malformed file whose children point
        # back up the tree must not spin here for ever.
        for _step in range(len(self.nodes) + 1):
            if index < 0:
                return -index - 1
            node = nodes[index]
            plane = planes[int(node['plane'])]
            normal = plane['normal']
            side = (px * float(normal[0]) + py * float(normal[1])
                    + pz * float(normal[2]) - float(plane['distance']))
            index = int(node['children'][0 if side >= 0.0 else 1])
        log.warning('the node tree did not reach a leaf; the map may be damaged')
        return -1

    def cluster_at(self, where: Sequence[float]) -> int:
        """Which cluster holds ``where``, or :data:`NO_CLUSTER`."""
        leaf = self.leaf_at(where)
        if leaf < 0 or self.leafs is None or leaf >= len(self.leafs):
            return NO_CLUSTER
        return int(self.leafs[leaf]['cluster'])

    # -- what it can see --------------------------------------------------
    def sees(self, here: int, there: int) -> bool:
        """Whether cluster ``there`` may be visible from cluster ``here``.

        True whenever the question cannot be answered -- no visibility data, a
        point outside every cluster, an index the data does not cover.  The set
        is what may be *rejected*; not knowing has to mean drawing it.
        """
        vectors = self._vectors
        if vectors is None or here < 0 or there < 0:
            return True
        if here >= len(vectors):
            return True
        byte = there >> 3
        if byte >= vectors.shape[1]:
            return True
        return bool(vectors[here][byte] & (1 << (there & 7)))

    def visible_from(self, where: Sequence[float]) -> Optional[np.ndarray]:
        """A mask over clusters of what ``where`` may see, or None for all.

        For a caller asking about many things from one place: one unpacking of
        the standing cluster's vector answers all of them, where
        :meth:`sees` would re-read a byte each time.
        """
        vectors = self._vectors
        if vectors is None:
            return None
        here = self.cluster_at(where)
        if here < 0 or here >= len(vectors):
            return None
        return np.unpackbits(vectors[here], bitorder='little').astype(bool)
