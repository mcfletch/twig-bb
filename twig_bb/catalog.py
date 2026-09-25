"""What this build offers to download, read from its own registry file.

The packs live in :data:`CATALOG_PATH` rather than in Python, so one can be
added, its size corrected or its URL moved without a code change -- and so what
a given build offers can be read off one file instead of out of a module.

Reading and validating it is the engine's
(:mod:`OpenGLContext.contentpacks.catalog`); what is here is which file, and
that this game's packs sit under the ``twig-bb`` namespace. Validation is
strict: a pack that fails to load is refused loudly rather than skipped, and the
field that matters most is ``copyright``, since :mod:`twig_bb.notices` generates
the acknowledgements screen from these entries.
"""

from __future__ import annotations

import os
from typing import Optional
from collections.abc import Sequence

from OpenGLContext.contentpacks import catalog as engine
from OpenGLContext.contentpacks.catalog import BadCatalog

from .assetpack import AssetPack

__all__ = ['BadCatalog', 'CATALOG_PATH', 'NAMESPACE', 'load', 'pack_for_key']

#: The registry shipped with the package.
CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'packs.json')

#: The namespace this game's packs sit under. A registry added to a build may
#: declare only its own, so nothing added can answer for a pack shipped here.
NAMESPACE = 'twig-bb'


def load(path: Optional[str] = None) -> list[AssetPack]:
    """Every pack the registry declares, in file order.

    One file, validated on its own. What a pack needs is checked against the
    whole set rather than against one registry, so that is
    :func:`OpenGLContext.contentpacks.catalog.merge`, which
    :data:`twig_bb.download.ASSET_PACKS` applies to the shipped one.
    """
    return engine.load(path or CATALOG_PATH)


def pack_for_key(key: str, packs: Optional[Sequence[AssetPack]] = None
                 ) -> Optional[AssetPack]:
    """The pack with this key, or None.

    A bare name reaches this game's own pack of that name: keys are namespaced
    so that a registry added to a build cannot answer for one shipped here, and
    inside this game the namespace is implied.
    """
    wanted = key if '/' in key else '%s/%s' % (NAMESPACE, key)
    return engine.pack_for_key(wanted, load() if packs is None else packs)
