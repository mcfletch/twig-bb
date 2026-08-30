"""Baked lightmap pages that live beside a map rather than inside it.

``SPEC-BSP46 §4.13`` puts a map's baked light in a lump of 128 x 128 blocks that
faces address by index.  A map compiler can instead write those pages as image
files next to the `.bsp`, leaving the lump empty; ``SPEC-EXTLM`` describes the
naming and the indexing, and a reader that does not know about it draws such a
map with no baked light at all.

What a face means by its index does not change (``SPEC-EXTLM §3.1``, ``§3.2``):
the index names a page and the UVs are normalised over it.  Only the page's
size differs, and it is read from each image rather than assumed
(``SPEC-EXTLM §2.3``).

Pages are loaded **on demand**, which is what makes deluxemapped maps free:
``SPEC-EXTLM §4`` says a compiler may interleave light-direction pages with the
light pages, and since no face ever names one, a loader that fetches only the
pages faces ask for never reads them.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Sequence

import numpy as np

from .contentsearch import ContentSearch

log = logging.getLogger(__name__)

#: ``SPEC-EXTLM §2.1`` -- a page's file name, given its index.
PAGE_NAME = 'lm_%04d'

#: The directory a map's pages sit in, relative to the map file's own
#: directory, is the map's own name (``SPEC-EXTLM §2.1``).
MAPS_DIR = 'maps'


def wanted(bsp: object) -> bool:
    """Whether this map's baked light lives outside the file.

    ``SPEC-EXTLM §1.2``: an empty lightmap lump together with at least one face
    that still names a page.  A map with no baked light at all names no page,
    so it is not confused with one whose pages are elsewhere and it costs no
    search.
    """
    if len(getattr(bsp, 'lightmaps', ())):
        return False
    faces = getattr(bsp, 'faces', None)
    if faces is None or not len(faces):
        return False
    return bool((np.asarray(faces['lm_index']) >= 0).any())


def indices(bsp: object) -> List[int]:
    """The page indices this map's faces actually name, ascending.

    ``SPEC-EXTLM §3.3``: any negative index means the face has no page, so only
    non-negative values are pages to find.
    """
    faces = getattr(bsp, 'faces', None)
    if faces is None or not len(faces):
        return []
    found = np.unique(np.asarray(faces['lm_index']))
    return [int(value) for value in found if value >= 0]


class ExternalLightmaps:
    """A map's external pages, read as they are asked for.

    Indexable and sized like the lump it stands in for, so
    :mod:`twig_bb.q3geometry` addresses it exactly as it addresses
    ``bsp.lightmaps`` and nothing downstream branches on where the light came
    from.
    """

    def __init__(self, directory: str, count: int,
                 extensions: Sequence[str]) -> None:
        self.directory = directory
        self.count = count
        self.extensions = tuple(extensions)
        self._pages: Dict[int, Optional[np.ndarray]] = {}
        self._search = ContentSearch([directory])

    def __len__(self) -> int:
        return self.count

    def __getitem__(self, index: int) -> np.ndarray:
        page = self.page(int(index))
        if page is None:
            # A named page that will not open is one unlit surface, not a
            # failed map: black is what an absent lightmap has always meant.
            return np.zeros((1, 1, 3), dtype='u1')
        return page

    def page(self, index: int) -> Optional[np.ndarray]:
        """Page ``index`` as an ``(h, w, 3)`` byte array, or None."""
        if index not in self._pages:
            self._pages[index] = self._read(index)
        return self._pages[index]

    def _read(self, index: int) -> Optional[np.ndarray]:
        """Read one page off disk (``SPEC-EXTLM §2.1``, ``§2.2``)."""
        path = self._search.find(PAGE_NAME % (index,), self.extensions)
        if path is None:
            return None
        from .materials import open_image
        image = open_image(path)
        if image is None:
            return None
        return np.asarray(image.convert('RGB'), dtype='u1')


def for_map(map_path: str, bsp: object,
            extensions: Sequence[str]) -> Optional[ExternalLightmaps]:
    """This map's external pages, or None if it has none to find.

    ``SPEC-EXTLM §2.1``: the pages sit in a directory beside the map and named
    after it.  Returns None when the map's light is in the file already, when
    it has no baked light, or when the directory holds nothing — in each of
    which the caller keeps the lump it already has.
    """
    if not wanted(bsp):
        return None
    named = indices(bsp)
    if not named:
        return None
    directory = os.path.join(os.path.dirname(os.path.abspath(map_path)),
                             os.path.splitext(os.path.basename(map_path))[0])
    if not os.path.isdir(directory):
        log.info('%s has no lightmaps of its own and no %s directory beside '
                 'it; it will draw unlit', map_path, os.path.basename(directory))
        return None
    pages = ExternalLightmaps(directory, max(named) + 1, extensions)
    if pages.page(named[0]) is None:
        log.warning('%s names lightmap page %d, which %s does not hold',
                    map_path, named[0], directory)
        return None
    log.info('%s draws with %d external lightmap pages from %s',
             os.path.basename(map_path), len(named), directory)
    return pages
