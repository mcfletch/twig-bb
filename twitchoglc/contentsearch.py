"""Finding a file a map named, under the content roots the map was loaded with.

Every kind of asset a map names — a texture, a material script, a sound — is
found the same way, and the rule is not obvious enough to write twice:

* the **roots** are searched in precedence order, so a map's own tree shadows
  the base content it was built against (``SPEC-BSP46 §7.3``);
* the **extension a name carries is advisory** and the supported ones are tried
  in turn (``SPEC-Q3SHADER §1.6`` for textures, ``SPEC-Q3ENTITIES §1.2.3`` for
  sounds, arrived at independently from each);
* a name that misses in every case gets a **case-insensitive** retry, because
  this content is authored as though the filesystem ignored case and on a
  case-sensitive one an exact lookup silently loses real files;
* and a name may **never leave its root**, because map content is untrusted.

Root precedence is resolved before extension preference: a tree that overrides
a base asset does so in whatever format it chose, and a search that could reach
past a root would let a stale base `.wav` beat an override's `.ogg`.

The class is a cache as much as a search.  A map naming a hundred absent
textures must not walk the tree a hundred times, so each directory is listed at
most once and the answer — including "there is no such directory" — is kept.
"""

from __future__ import annotations

import os
from typing import Dict, Optional, Sequence, Tuple


class ContentSearch:
    """Path lookup over one map's content roots, with its directory listings."""

    def __init__(self, roots: Sequence[str]) -> None:
        self.roots = [os.path.abspath(root) for root in roots]
        self._listings: Dict[Tuple[str, str], Optional[Dict[str, str]]] = {}

    def find(self, relative: str,
             extensions: Sequence[str]) -> Optional[str]:
        """The first existing file for ``relative`` plus each extension.

        ``relative`` carries no extension of its own: the caller has already
        stripped whatever the content named, because that spelling is advisory.
        Returns None when no root holds it, which is a normal outcome — most
        maps name assets from a base game that may not have been fetched.
        """
        for root in self.roots:
            for extension in extensions:
                path = safe_join(root, relative + extension)
                if path and os.path.isfile(path):
                    return path
            found = self._case_insensitive(root, relative, extensions)
            if found:
                return found
        return None

    def exists(self, root: str, relative: str) -> Optional[str]:
        """``relative`` under one root, exactly as spelled, or None.

        For the caller that wants to know whether a *particular* file is there
        rather than which of several is — reporting an asset whose format is
        recognised but undecodable, say.
        """
        path = safe_join(os.path.abspath(root), relative)
        return path if path and os.path.isfile(path) else None

    def _case_insensitive(self, root: str, relative: str,
                          extensions: Sequence[str]) -> Optional[str]:
        """The file whose name differs from ``relative`` only in case.

        The containment check of :func:`safe_join` has to be repeated here and
        not only in :meth:`find`: this path walks the tree segment by segment,
        so a `..` segment would climb out of the root by an entirely different
        route from the one the join refuses.
        """
        if safe_join(root, relative) is None:
            return None
        directory, _, stem = relative.rpartition('/')
        listing = self._listing(root, directory)
        if listing is None:
            return None
        for extension in extensions:
            match = listing.get((stem + extension).lower())
            if match:
                return match
        return None

    def _listing(self, root: str, directory: str) -> Optional[Dict[str, str]]:
        """``{lower-case filename: full path}`` for one directory, listed once.

        The directory itself may also be differently cased, so each segment of
        the path is resolved the same way.
        """
        key = (root, directory)
        if key in self._listings:
            return self._listings[key]
        path: Optional[str] = root
        for segment in directory.split('/') if directory else []:
            path = _child_directory(path, segment)
            if path is None:
                break
        listing: Optional[Dict[str, str]] = None
        if path is not None and os.path.isdir(path):
            try:
                listing = {name.lower(): os.path.join(path, name)
                           for name in os.listdir(path)}
            except OSError:                     # unreadable directory
                listing = None
        self._listings[key] = listing
        return listing


def safe_join(root: str, relative: str) -> Optional[str]:
    """Join a content-supplied path to a root, refusing to escape it.

    Map content is untrusted: a name is attacker-controlled for any map from
    the internet, so a name containing `..` or an absolute path must not read
    outside the content root.
    """
    if os.path.isabs(relative):
        return None
    path = os.path.normpath(os.path.join(root, relative))
    if path != root and not path.startswith(root + os.sep):
        return None
    return path


def _child_directory(parent: Optional[str], name: str) -> Optional[str]:
    """The named subdirectory of ``parent``, matching case-insensitively."""
    if parent is None:
        return None
    exact = os.path.join(parent, name)
    if os.path.isdir(exact):
        return exact
    try:
        entries = os.listdir(parent)
    except OSError:
        return None
    lowered = name.lower()
    for entry in entries:
        if entry.lower() == lowered:
            candidate = os.path.join(parent, entry)
            if os.path.isdir(candidate):
                return candidate
    return None
