"""Resolving a map's ``noise`` path to a sound file in the content packs.

A map names a sound the way it names a texture — a path relative to the content
tree, whose extension is advisory — so this is the same search over the same
roots, and it is the same :class:`~twig_bb.contentsearch.ContentSearch` doing
it.  What is here is only the three spellings a `noise` arrives in
(``SPEC-Q3ENTITIES §1.2.2``) and what to do about the one that is not a path.

``*falling1.wav`` is that one.  The ``*`` marks a sound belonging to an
entity's own model rather than to the content tree (``SPEC-Q3ENTITIES
§1.2.5``), and a viewer with no such models cannot resolve it.  It is skipped
without looking, deliberately: a file that happened to match the name after the
asterisk would be a *different* sound, and a wrong sound is worse than none.

**A `noise` that resolves to nothing is a silence, not a failure.**  Maps
routinely name sounds from a base game a given install did not fetch — two of
the 46 distinct values in the shipped content do — so a miss warns once and the
map loads (``SPEC-Q3ENTITIES §1.2.7``).
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Optional, Sequence

from .contentsearch import ContentSearch

log = logging.getLogger(__name__)

#: The audio extensions the content ships and the engine decodes, most likely
#: first (``SPEC-Q3ENTITIES §2.1``: 255 `.wav` against 98 `.ogg`).
SOUND_EXTENSIONS = ('.wav', '.ogg')

#: ``SPEC-Q3ENTITIES §1.2.5``: a `noise` beginning with this names an entity
#: model's own sound and is not a path into the content tree.
MODEL_SOUND_PREFIX = '*'


class SoundLibrary:
    """Sound lookup for one map's content roots.

    Every answer is kept, including the misses: a speaker is asked for its clip
    while the scene is built and a game may build several, and a sound that is
    not there must not be looked for again.
    """

    def __init__(self, roots: Sequence[str]) -> None:
        self.roots = [os.path.abspath(root) for root in roots]
        self._files = ContentSearch(self.roots)
        self._resolved: Dict[str, Optional[str]] = {}

    def resolve(self, noise: str) -> Optional[str]:
        """The file a ``noise`` key names, or None.

        None covers both ways a sound can be unavailable — a path that is not
        in any root, and a name that is not a path at all — because a caller
        does the same thing about each: nothing.  Which one it was is in the
        warning.
        """
        if noise in self._resolved:
            return self._resolved[noise]
        found = self._lookup(noise)
        self._resolved[noise] = found
        return found

    def _lookup(self, noise: str) -> Optional[str]:
        """Resolve one name, warning about whichever way it failed."""
        if not noise:
            return None
        if noise.startswith(MODEL_SOUND_PREFIX):
            log.warning('%s belongs to an entity model rather than to the '
                        'content tree; it will be silent', noise)
            return None
        # SPEC-Q3ENTITIES §1.2.2: a leading slash is an alternate spelling of
        # the same path, not a different namespace.  §1.2.3: the extension is
        # advisory, so it is stripped and ours are tried in turn.
        stem = os.path.splitext(noise.lstrip('/').replace('\\', '/'))[0]
        found = self._files.find(stem, SOUND_EXTENSIONS)
        if found is None:
            log.warning('no sound found for %s; it will be silent', noise)
        return found
