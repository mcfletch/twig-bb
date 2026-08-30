"""Pack many small baked-lighting blocks into a few GPU textures.

Version 46 gives whole 128 x 128 images that faces address by index
(``SPEC-BSP46 §4.13``).  A map has thousands of these and a renderer wants a
handful of large ones, so they feed this packer and address the result through
:meth:`LightmapAtlas.uv_from_luxels` or :meth:`LightmapAtlas.uv_from_normalised`.

**Why a shelf pack.** The whole set is sorted by height once and laid down in
rows, so placing a block is integer arithmetic and no search runs over the
pixels.  The alternative — a skyline packer that searches for each rectangle's
best position — costs a per-rectangle scan, which on a map's worth of blocks is
tens of millions of tiny array operations and dominates the map's whole load
time.  The plan's budget is a load of about two seconds; this stage must be a
small fraction of it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

import numpy as np

log = logging.getLogger(__name__)

#: Page edge in texels. 2048 is inside the 3.3-core guaranteed minimum of 1024?
#: No -- GL 3.3 guarantees at least 1024, but every driver this viewer targets
#: exceeds 2048 by a wide margin, and halving the page would double the page
#: count and hence the draw calls.
DEFAULT_PAGE_SIZE = 2048

#: Texels left between neighbouring blocks.  Sampling at luxel centres already
#: keeps bilinear taps inside a block, so this is only insurance against
#: floating-point drift at a block's edge.
DEFAULT_PADDING = 1

#: Rec. 709 luminance weights, for reducing a luxel to one brightness.
LUMINANCE = np.array([0.2126, 0.7152, 0.0722], dtype='f')


@dataclass(frozen=True)
class Placement:
    """Where one block ended up: which page, and its top-left texel."""

    page: int
    x: int
    y: int
    width: int
    height: int


class LightmapAtlas:
    """The packed pages, and the mapping from block coordinates onto them."""

    def __init__(self, pages: List[np.ndarray], placements: List[Optional[Placement]],
                 page_size: int) -> None:
        self.pages = pages
        self.placements = placements
        self.page_size = page_size

    def page_of(self, index: int) -> int:
        """The page a block landed on, or -1 if it has none."""
        place = self.placements[index]
        return -1 if place is None else place.page

    def median_luxel(self) -> Optional[float]:
        """The middle brightness of this map's baked light, from 0 to 1.

        How bright the map was *baked*, which is not a constant across content:
        a map records absolute radiosity and different compilers and different
        projects settle on wildly different absolute scales.  A viewer applying
        one fixed exposure to all of them over-exposes whichever content was
        baked brighter than the exposure was chosen for, and the surfaces come
        out pale with their shadows lifted off the floor.

        Unlit luxels are left out: a page is mostly the black between blocks,
        and counting it would report every map as dark whatever its lit
        surfaces look like.  The median rather than the mean, because a few
        bright light fixtures should not decide the exposure of a whole level.

        None when the map has no baked light at all.
        """
        if not self.pages:
            return None
        luminance = np.concatenate([
            np.asarray(page, dtype='f').reshape((-1, 3)) @ LUMINANCE
            for page in self.pages])
        lit = luminance[luminance > 0]
        if not len(lit):
            return None
        return float(np.median(lit)) / 255.0

    def uv_from_luxels(self, index: int, luxels: Any) -> np.ndarray:
        """Atlas UVs for coordinates given in luxels within the block.

        ``SPEC-BSP38 §7.7``: a luxel is sampled at its centre, so the half-texel
        offset belongs here; §7.7 also notes that packing into a shared atlas
        means adding the block's offset before normalising by the atlas size.
        """
        place = self.placements[index]
        coords = np.asarray(luxels, dtype='f').reshape((-1, 2))
        if place is None:
            return np.zeros_like(coords)
        return np.column_stack((
            (place.x + coords[:, 0] + 0.5) / self.page_size,
            (place.y + coords[:, 1] + 0.5) / self.page_size))

    def uv_from_normalised(self, index: int, uv: Any) -> np.ndarray:
        """Atlas UVs for coordinates already normalised over the whole block.

        ``SPEC-BSP46 §4.9.3``: a version 46 vertex carries its lightmap
        coordinate normalised within the face's lightmap image, so the block's
        own extent scales it rather than a luxel count.
        """
        place = self.placements[index]
        coords = np.asarray(uv, dtype='f').reshape((-1, 2))
        if place is None:
            return np.zeros_like(coords)
        return np.column_stack((
            (place.x + coords[:, 0] * place.width) / self.page_size,
            (place.y + coords[:, 1] * place.height) / self.page_size))


def build_atlas(blocks: Sequence[Optional[np.ndarray]],
                page_size: int = DEFAULT_PAGE_SIZE,
                padding: int = DEFAULT_PADDING) -> LightmapAtlas:
    """Pack ``blocks`` — each ``(height, width, 3)`` uint8, or None — into pages.

    Returns an atlas whose ``placements`` line up index-for-index with
    ``blocks``.  A page is black where nothing was placed, so an unused region
    contributes no light if a UV ever strays into it.
    """
    sizes = [(0, 0) if block is None else (block.shape[1], block.shape[0])
             for block in blocks]
    page_size = _page_size_for(sizes, page_size, padding)
    placements = _shelf_pack(sizes, page_size, padding)
    pages = _blit(blocks, placements, page_size)
    return LightmapAtlas(pages, placements, page_size)


def _page_size_for(sizes: Sequence[Any], page_size: int, padding: int) -> int:
    """Grow the page until the largest block fits, rounded up to a power of two.

    A single face whose luxel grid is bigger than the requested page would
    otherwise have to be dropped, losing its baked lighting entirely.
    """
    needed = 0
    for width, height in sizes:
        needed = max(needed, int(width) + padding, int(height) + padding)
    while page_size < needed:
        page_size *= 2
    return page_size


def _shelf_pack(sizes: Sequence[Any], page_size: int,
                padding: int) -> List[Optional[Placement]]:
    """Height-sorted shelf packing: one pass, integer arithmetic only."""
    order = sorted((i for i, (w, h) in enumerate(sizes) if w > 0 and h > 0),
                   key=lambda i: -int(sizes[i][1]))
    placements: List[Optional[Placement]] = [None] * len(sizes)
    page, shelf_y, shelf_height, cursor_x = 0, 0, 0, 0
    for index in order:
        width, height = int(sizes[index][0]), int(sizes[index][1])
        step_w, step_h = width + padding, height + padding
        if cursor_x + step_w > page_size:                   # next shelf
            shelf_y += shelf_height
            shelf_height, cursor_x = 0, 0
        if shelf_y + step_h > page_size:                    # next page
            page += 1
            shelf_y, shelf_height, cursor_x = 0, 0, 0
        placements[index] = Placement(page, cursor_x, shelf_y, width, height)
        cursor_x += step_w
        shelf_height = max(shelf_height, step_h)
    return placements


def _blit(blocks: Sequence[Optional[np.ndarray]],
          placements: Sequence[Optional[Placement]],
          page_size: int) -> List[np.ndarray]:
    """Copy each block into its page."""
    count = max((place.page for place in placements if place is not None),
                default=-1) + 1
    pages = [np.zeros((page_size, page_size, 3), np.uint8) for _ in range(count)]
    for block, place in zip(blocks, placements, strict=True):
        if place is None or block is None:
            continue
        pages[place.page][place.y:place.y + place.height,
                          place.x:place.x + place.width] = block
    log.debug('packed %d lightmap blocks into %d %dx%d pages',
              sum(1 for p in placements if p is not None), count, page_size, page_size)
    return pages
