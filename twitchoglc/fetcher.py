"""Fetching content packs without freezing the window.

A texture pack is 450 MB. Fetching one on the frame loop's thread stops the
window dead for minutes — no redraw, no cancel, and on most desktops an
eventual "this application is not responding" from the window manager.

So the work happens on a worker thread and **the frame loop polls**:
:meth:`FetchJob.poll` is called once a frame, publishes whatever the worker has
managed since the last call, and is the *only* place anything the worker wrote
is read. That single rule is the whole of the thread safety here, and it is why
a caller needs no lock of its own: everything a caller touches —
:attr:`~FetchJob.finished`, :attr:`~FetchJob.fraction`, :attr:`~FetchJob.roots`
— is written by ``poll`` on the caller's own thread.

The consequence is worth stating plainly because it looks like a bug and is
not: a job whose worker has run to completion still reports itself unfinished
until it is polled. A frame loop that stops polling stops learning, which is
correct — there is nobody to tell.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, List, Optional, Sequence

from .assetpack import AssetPack

log = logging.getLogger(__name__)

__all__ = ['Cancelled', 'FetchJob', 'fetch_pack']

#: What one pack's fetch is called with: the pack, a progress callback taking
#: bytes-so-far and an optional total, and a predicate that goes true when the
#: user has cancelled.  Returns the pack's unpacked content root.
Fetch = Callable[[AssetPack, Callable[[int, Optional[int]], None],
                  Callable[[], bool]], str]


class Cancelled(Exception):
    """The user asked for the download to stop.

    Distinct from a failure so the two can be reported differently: nothing
    went wrong, and telling somebody their own decision was an error is a poor
    way to answer it.
    """


def fetch_pack(pack: AssetPack, progress: Any, cancel: Any,
               cache_dir: Optional[str] = None) -> str:
    """Fetch and unpack one pack, reporting progress and honouring a cancel.

    The default worker of :class:`FetchJob`, separated so a test can drive the
    job with something that touches no network.
    """
    from OpenGLContext.loaders import resolver

    from . import download
    existing = download.pack_root(pack, cache_dir)
    if existing is not None:
        progress(pack.approximate_bytes, pack.approximate_bytes)
        return existing
    try:
        archive = resolver.fetch_to_cache(
            pack.url, cache_dir=cache_dir,
            max_bytes=download.fetch_limit(pack.approximate_bytes),
            progress=progress, cancel=cancel)
    except resolver.FetchCancelled as error:
        raise Cancelled(str(error)) from error
    directory = download.pack_directory(pack, cache_dir)
    if pack.archive == 'zip':
        download.unpack(archive, directory, require_map=False)
    else:
        download._extract_tar(archive, directory)
    return directory


class FetchJob:
    """One user-consented download of one or more packs, run off the frame loop.

    **One bar for the job, not one per pack.** A user who consents to three
    packs agreed to a single download of their combined size; a bar that fills
    and resets three times reads as three failures. :attr:`fraction` therefore
    spans the whole set, weighted by the sizes the user was shown.
    """

    def __init__(self, packs: Sequence[AssetPack],
                 fetch: Optional[Fetch] = None,
                 cache_dir: Optional[str] = None,
                 on_progress: Optional[Callable[[], None]] = None) -> None:
        self.packs = list(packs)
        self.cache_dir = cache_dir
        self._fetch: Fetch = fetch if fetch is not None else (
            lambda pack, progress, cancel: fetch_pack(
                pack, progress, cancel, cache_dir=cache_dir))
        #: Called after each :meth:`poll` that saw something change, so a
        #: caller can ask for a redraw without polling for a difference.
        self.on_progress = on_progress

        #: How much of the job the user consented to, in bytes.
        self.total_bytes = sum(pack.approximate_bytes for pack in self.packs)

        # -- published by poll(), read by the frame loop ------------------
        #: Whether the worker has finished, as of the last poll.
        self.finished = False
        #: The error that stopped it, or None.  A cancellation is not one.
        self.failed: Optional[BaseException] = None
        #: Whether it stopped because the user said so.
        self.cancelled = False
        #: The content roots of the packs that did arrive.
        self.roots: List[str] = []
        #: How far along, 0 to 1.
        self.fraction = 1.0 if not self.packs else 0.0
        #: A line for the user: which pack, and how far.
        self.state = 'ready'

        # -- written by the worker, read only under _lock -----------------
        self._lock = threading.Lock()
        self._done_bytes = 0
        self._current = ''
        self._roots: List[str] = []
        self._failed: Optional[BaseException] = None
        self._complete = False
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- the frame loop's side -------------------------------------------
    def start(self) -> 'FetchJob':
        """Begin, on a worker thread.  Returns self, so it can be chained."""
        if self._thread is not None:
            return self
        self._thread = threading.Thread(target=self._run, name='twitch-fetch',
                                        daemon=True)
        self._thread.start()
        return self

    def cancel(self) -> None:
        """Ask the download to stop.  Safe before it starts and after it ends."""
        self._cancel.set()
        self.cancelled = True

    def poll(self) -> bool:
        """Publish whatever the worker has managed; returns whether anything did.

        Called once a frame.  The only place the worker's state is read, which
        is what lets everything above be touched without a lock.
        """
        with self._lock:
            done, current = self._done_bytes, self._current
            roots, failed, complete = list(self._roots), self._failed, self._complete
        fraction = (1.0 if not self.total_bytes
                    else min(1.0, done / float(self.total_bytes)))
        state = self._describe(current, fraction, complete)
        changed = (fraction != self.fraction or state != self.state
                   or complete != self.finished or roots != self.roots)
        self.fraction, self.state = fraction, state
        self.roots, self.finished = roots, complete
        if complete:
            self.cancelled = self.cancelled or isinstance(failed, Cancelled)
            self.failed = None if isinstance(failed, Cancelled) else failed
        if changed and self.on_progress is not None:
            self.on_progress()
        return changed

    def _describe(self, current: str, fraction: float, complete: bool) -> str:
        """The line a user reads while this is happening."""
        if complete:
            if self.cancelled or isinstance(self._failed, Cancelled):
                return 'cancelled'
            return 'failed' if self._failed is not None else 'done'
        if not current:
            return 'ready'
        return '%s — %d%% of %s' % (current, round(fraction * 100),
                                    self.human_total())

    def human_total(self) -> str:
        """The whole job's size as the user should read it."""
        return '%d MB' % (round(self.total_bytes / 1e6),)

    # -- the worker's side ------------------------------------------------
    def _run(self) -> None:
        """Fetch each pack in turn.  Never raises: the frame loop cannot catch it."""
        before = 0
        for pack in self.packs:
            if self._cancel.is_set():
                self._stop(Cancelled('cancelled before %s' % (pack.key,)))
                return
            with self._lock:
                self._current = pack.title
            try:
                root = self._fetch(pack, self._reporter(before, pack),
                                   self._cancel.is_set)
            except Cancelled as error:
                self._stop(error)
                return
            except Exception as error:          # noqa: BLE001 - reported, not raised
                log.warning('could not fetch %s', pack.key, exc_info=True)
                # Whatever did arrive is kept: two of three packs is usable,
                # and throwing it away would make the next attempt start over.
                self._stop(error)
                return
            before += pack.approximate_bytes
            with self._lock:
                self._roots.append(root)
                self._done_bytes = before
        self._stop(None)

    def _reporter(self, before: int, pack: AssetPack) -> Any:
        """A progress callback for one pack, offset into the whole job.

        A pack whose real size overruns what it published must not push the
        job's total past its own size, or the bar goes backwards when the next
        pack starts.
        """
        def report(done: int, total: Optional[int]) -> None:
            with self._lock:
                self._done_bytes = before + min(done, pack.approximate_bytes)
        return report

    def _stop(self, error: Optional[BaseException]) -> None:
        with self._lock:
            self._failed = error
            self._complete = True
