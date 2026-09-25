"""Fetching content packs without freezing the window.

The job itself is the engine's
:class:`OpenGLContext.contentpacks.fetch.FetchJob`: a texture pack is 450 MB,
fetching one on the frame loop's thread stops the window dead for minutes, and
the rule that makes it safe -- the worker writes under a lock and ``poll()``,
called once a frame, is the only place anything it wrote is read -- is the
engine's to state. What is here is that a job of this game's fetches into this
game's store.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

from OpenGLContext.contentpacks.fetch import Cancelled
from OpenGLContext.contentpacks.fetch import FetchJob as _FetchJob
from OpenGLContext.contentpacks.fetch import fetch_pack as _fetch_pack

from .assetpack import AssetPack

__all__ = ['Cancelled', 'FetchJob', 'fetch_pack']


def fetch_pack(pack: AssetPack, progress: Any, cancel: Any,
               cache_dir: Optional[str] = None) -> str:
    """Fetch and unpack one pack, reporting progress and honouring a cancel."""
    from . import download
    return _fetch_pack(pack, download.store(cache_dir), progress, cancel)


class FetchJob(_FetchJob):
    """One user-consented download of one or more packs, into this game's store.

    The engine's job takes the store it writes to; this one opens the game's
    store, at ``cache_dir`` if given, so a caller names packs and no store.
    """

    def __init__(self, packs: Sequence[AssetPack],
                 fetch: Optional[Callable[..., str]] = None,
                 cache_dir: Optional[str] = None,
                 on_progress: Optional[Callable[[], None]] = None) -> None:
        from . import download
        super().__init__(packs, download.store(cache_dir), fetch=fetch,
                         cache_dir=None, on_progress=on_progress)

