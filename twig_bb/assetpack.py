"""One downloadable content pack, as a value.

The type itself is the engine's
:class:`OpenGLContext.contentpacks.ContentPack`, since a pack of Quake art is a
content pack like any other and the engine is where a capability a game would
also want belongs. ``AssetPack`` is the name this game calls it by.
"""

from __future__ import annotations

from OpenGLContext.contentpacks import ContentPack

#: What a downloadable pack is here.
AssetPack = ContentPack

__all__ = ['AssetPack', 'ContentPack']
