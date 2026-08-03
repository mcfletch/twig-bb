"""What this build offers to download, read from a data file.

The list of content packs lives in :data:`CATALOG_PATH` rather than in Python,
so a pack can be added, its size corrected or its URL moved without a code
change — and so what a given build offers can be read off one file instead of
out of a module.

**Validation is strict on purpose.** A pack that fails to load is refused
loudly rather than skipped, and every field has to be one the schema declares.
Both rules answer the same failure: an entry with a mistyped key would
otherwise be accepted, ignored for ever, and never noticed. The one that
matters most is ``copyright`` — the acknowledgements screen is *generated* from
these entries, so a pack that cannot state its terms would be offered for
download and left out of the notices, which is precisely what the notices exist
to prevent.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence

from .assetpack import AssetPack

__all__ = ['BadCatalog', 'CATALOG_PATH', 'load', 'pack_for_key']

#: The catalogue shipped with the package.
CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'packs.json')

#: Fields an entry must carry.  Each is either shown to the user before they
#: consent to a download or needed to perform one.
REQUIRED = ('key', 'title', 'url', 'directory', 'archive',
            'approximate_bytes', 'copyright', 'marker')

#: Fields an entry may carry, and what it means to leave each one out.
OPTIONAL = {
    'family': None,             # which map family it helps; None for any
    'companions': (),           # keys of packs it is incomplete without
    'notes': '',                # a sentence for the download and notices screens
    'url_page': '',             # where a human reads about it
}


class BadCatalog(ValueError):
    """The catalogue could not be read, or an entry in it is not usable.

    Raised rather than skipping the entry: a pack silently dropped for a typo
    is a pack nobody can download and nobody can see the absence of.
    """


def load(path: Optional[str] = None) -> List[AssetPack]:
    """Every pack the catalogue at ``path`` declares, in file order."""
    path = path or CATALOG_PATH
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            document = json.load(handle)
    except (OSError, ValueError) as error:
        raise BadCatalog('cannot read the content catalogue %s: %s'
                         % (path, error)) from error
    entries = document.get('packs') if isinstance(document, dict) else None
    if not isinstance(entries, list):
        raise BadCatalog('%s has no "packs" list' % (path,))
    return [_pack(entry, path) for entry in entries]


def pack_for_key(key: str, packs: Optional[Sequence[AssetPack]] = None
                 ) -> Optional[AssetPack]:
    """The pack with this key, or None."""
    for pack in (load() if packs is None else packs):
        if pack.key == key:
            return pack
    return None


def _pack(entry: Any, path: str) -> AssetPack:
    """One catalogue entry as an :class:`AssetPack`, or a clear complaint."""
    if not isinstance(entry, dict):
        raise BadCatalog('%s holds an entry that is not an object' % (path,))
    known = set(REQUIRED) | set(OPTIONAL)
    unknown = sorted(set(entry) - known)
    if unknown:
        raise BadCatalog('%s: pack %r declares %s, which no field is called'
                         % (path, entry.get('key', '?'), ', '.join(unknown)))
    missing = [name for name in REQUIRED if name not in entry]
    if missing:
        raise BadCatalog('%s: pack %r is missing %s'
                         % (path, entry.get('key', '?'), ', '.join(missing)))
    if not str(entry['copyright']).strip():
        raise BadCatalog(
            '%s: pack %r states no copyright.  The acknowledgements screen is '
            'generated from that field, so a pack without one would be offered '
            'for download and never credited.' % (path, entry['key']))
    if int(entry['approximate_bytes']) <= 0:
        raise BadCatalog('%s: pack %r states no size, and the user is asked to '
                         'consent to one' % (path, entry['key']))
    values: Dict[str, Any] = {name: entry[name] for name in REQUIRED}
    for name, default in OPTIONAL.items():
        values[name] = entry.get(name, default)
    values['companions'] = tuple(values['companions'] or ())
    values['approximate_bytes'] = int(values['approximate_bytes'])
    return AssetPack(**values)
