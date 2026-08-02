"""One downloadable content pack, as a value.

Its own module because two things need it and neither should need the other:
:mod:`twitchoglc.catalog` reads packs out of a data file, and
:mod:`twitchoglc.download` fetches and unpacks them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class AssetPack:
    """An optional download that fills in content a map does not carry.

    ``approximate_bytes`` and ``copyright`` exist because both are put in front
    of the user before anything is fetched; a pack that cannot state its size
    and its terms has no business being offered.
    """

    key: str
    title: str
    url: str
    #: Directory name it unpacks into, under the shared content cache.
    directory: str
    #: ``zip`` or ``tar`` — the latter covering every compression a tarball
    #: arrives under, which the reader detects for itself.
    archive: str
    approximate_bytes: int
    copyright: str
    #: A path that, when present, proves the pack is already unpacked.  Empty
    #: where the directory existing and being non-empty is proof enough.
    marker: str
    #: Which map family it helps, or None for anything.
    family: Optional[str] = None
    #: Keys of packs this one is incomplete without.
    companions: Tuple[str, ...] = ()
    #: A sentence about what it is, for the download and notices screens.
    notes: str = ''
    #: Where a human reads about it, for the acknowledgements screen.
    url_page: str = ''

    def human_size(self) -> str:
        """The download size as the user should read it."""
        return '%d MB' % (round(self.approximate_bytes / 1e6),)
