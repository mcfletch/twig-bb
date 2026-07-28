"""Resolve texture names to images, and surface styles to PBR materials.

Two lookups live here.  **Where a name's image is** differs by family: a
version 38 texinfo name is a bare path under a `textures/` root with no
extension (``SPEC-BSP38 §6.4``), while a version 46 name is already rooted at
the archive (``SPEC-BSP46 §6.1``, ``§7.3``).  Either way the extension the name
arrives with is advisory and the supported ones are tried in turn
(``SPEC-Q3SHADER §1.6``).

**What a style becomes** does not differ: a :class:`SurfaceStyle` maps onto one
``PBRMaterial`` whatever family produced it, which is the point of having the
shared style at all.

The baked lightmap is wired in here too.  A lightmap holds light, not colour:
its luxels are linear samples and must not be sRGB-decoded, which is why the
channel is built with ``srgb=False``.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

from OpenGLContext.scenegraph.pbrmaterial import PBRMaterial, PBRTexture

from .surfaces import SurfaceStyle

log = logging.getLogger(__name__)

#: Extension search order, first hit wins (``SPEC-Q3SHADER §1.6``,
#: ``SPEC-BSP46 §7.3``).
TEXTURE_EXTENSIONS = ('.tga', '.jpg', '.png', '.jpeg')

#: ``SPEC-BSP38 §6.4`` names a `.wal` as the stock version 38 asset; it is
#: palette-indexed and the palette is separate content this viewer does not
#: carry, so its absence is reported rather than silently rendered blank.
UNDECODED_EXTENSIONS = ('.wal', '.pcx')

#: ``SPEC-BSP38 §6.4`` -- a version 38 name is relative to this root.
TEXTURE_ROOT = 'textures/'

#: Size assumed for a texture whose image is absent.  ``SPEC-BSP38 §6.2``
#: normalises UVs by the image's real dimensions, so this only affects the
#: tiling scale of surfaces whose content is missing.
FALLBACK_TEXTURE_SIZE = (64, 64)

#: Albedo used where no base-colour image was found.  Dark enough to sit in the
#: range real map textures occupy: a map is lit entirely by its baked lightmap
#: entirely, so a bright fallback multiplies straight through and
#: an untextured surface blows out to white instead of reading as missing.
FALLBACK_BASE_COLOR = (0.25, 0.25, 0.25)

#: Roughness for a map surface.  Neither family stores one, so this is the
#: viewer's own choice: map art is overwhelmingly matte, and a lightmapped
#: surface has its highlights baked in already.
ROUGHNESS_DEFAULT = 0.85

#: ``PBRMaterial.texCoordMask`` bit that makes the lightmap channel sample the
#: second UV set, which is where the atlas coordinates live.
TEXCOORD_MASK_LIGHTMAP = 32

#: Default exposure applied to a baked lightmap.  Not a format constant: a map
#: bakes absolute radiosity and every engine scales it at render time, so this
#: is the viewer's own default and ``--lightmap`` overrides it.
DEFAULT_LIGHTMAP_STRENGTH = 2.0

#: A trailing light value on a shader name: `light1_5000`, `baslt4_1_2k`,
#: `gothic_light2_4K`.  See :meth:`MaterialLibrary._light_variant`.
LIGHT_VARIANT = re.compile(r'^(.+)_\d+k?$', re.IGNORECASE)


class MaterialLibrary:
    """Texture lookup and PBR material construction for one map's content."""

    def __init__(self, roots: Sequence[str], family: str = 'quake2',
                 lightmap_strength: float = DEFAULT_LIGHTMAP_STRENGTH) -> None:
        self.roots = [os.path.abspath(root) for root in roots]
        self.family = family
        self.lightmap_strength = float(lightmap_strength)
        self._images: Dict[str, Any] = {}
        self._textures: Dict[Tuple[str, bool], PBRTexture] = {}
        self._materials: Dict[Tuple[Any, ...], PBRMaterial] = {}
        self._lightmaps: Dict[int, PBRTexture] = {}
        self._listings: Dict[Tuple[str, str], Optional[Dict[str, str]]] = {}

    # -- name resolution -------------------------------------------------
    def resolve(self, name: str) -> Optional[str]:
        """The file a texture name refers to, or None.

        ``SPEC-Q3SHADER §1.6``: whatever extension the name arrives with is
        advisory, so it is stripped and the supported ones are tried in turn,
        against each content root in precedence order.

        A name that resolves to nothing gets one more chance through
        :meth:`_light_variant`.
        """
        candidate = self._candidate(name)
        found = self._search(candidate, TEXTURE_EXTENSIONS, warn=True)
        if found is None:
            found = self._light_variant(candidate)
        return found

    def _light_variant(self, candidate: str) -> Optional[str]:
        """The texture a light-value shader name is built on, if that exists.

        Map authors name light-emitting surfaces after a shader rather than an
        image: `textures/base_light/light1_5000` is a shader that draws
        `light1` and emits 5000 units.  Those shaders live in the base game's
        scripts, so a map loaded without them resolves the name to no file and
        the surface renders untextured even though the image it is built on is
        sitting right there.

        Only a trailing run of digits with an optional `k` is dropped, which is
        what a light value looks like; a name like `comp3b_dark` keeps its
        suffix.  The fallback runs only after the exact name has already
        missed, so it can never displace a texture that genuinely exists.
        """
        match = LIGHT_VARIANT.match(candidate)
        if match is None:
            return None
        return self._search(match.group(1), TEXTURE_EXTENSIONS)

    def _candidate(self, name: str) -> str:
        """The extension-less path a name resolves against.

        A version 38 name is bare and is prefixed with the texture root
        (``SPEC-BSP38 §6.4``); a version 46 name already carries its own
        (``SPEC-BSP46 §6.1``).
        """
        stem = os.path.splitext(name.replace('\\', '/'))[0]
        if self.family == 'quake2' and not stem.startswith(TEXTURE_ROOT):
            stem = TEXTURE_ROOT + stem
        return stem

    def _search(self, relative: str, extensions: Sequence[str],
                warn: bool = False) -> Optional[str]:
        """First existing file for ``relative`` + each extension, in each root.

        An exact match always wins; only when every extension has missed does
        the case-insensitive lookup of :meth:`_case_insensitive` run, so a tree
        whose names match exactly costs no directory scans at all.
        """
        for root in self.roots:
            for extension in extensions:
                path = _safe_join(root, relative + extension)
                if path and os.path.isfile(path):
                    return path
            found = self._case_insensitive(root, relative, extensions)
            if found:
                return found
            if warn:
                self._warn_undecoded(root, relative)
        return None

    def _case_insensitive(self, root: str, relative: str,
                          extensions: Sequence[str]) -> Optional[str]:
        """The file whose name differs from ``relative`` only in case.

        Quake content is authored as though the filesystem ignored case — the
        Quake III shader manual asks for lowercase names, and maps and scripts
        do not always comply — so on a case-sensitive filesystem an exact-case
        lookup silently loses real textures.  Each directory is listed once and
        remembered.
        """
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

    def _warn_undecoded(self, root: str, relative: str) -> None:
        """Report an image that exists in a format this viewer cannot decode."""
        for extension in UNDECODED_EXTENSIONS:
            path = _safe_join(root, relative + extension)
            if path and os.path.isfile(path):
                log.warning('%s%s needs a palette this viewer does not carry; '
                            'the surface will be untextured', relative, extension)
                return

    # -- images ----------------------------------------------------------
    def image(self, name: str) -> Any:
        """The decoded image for a texture name, or None; loaded once."""
        if name not in self._images:
            path = self.resolve(name)
            self._images[name] = _open_image(path) if path else None
        return self._images[name]

    def texture_size(self, name: str) -> Tuple[int, int]:
        """``(width, height)`` of a texture's image (``SPEC-BSP38 §6.2``)."""
        image = self.image(name)
        if image is None:
            return FALLBACK_TEXTURE_SIZE
        return (int(image.size[0]), int(image.size[1]))

    def _texture(self, path: str, srgb: bool) -> Optional[PBRTexture]:
        """A cached :class:`PBRTexture` for a file, or None if it will not open."""
        key = (path, srgb)
        texture = self._textures.get(key)
        if texture is None:
            image = _open_image(path)
            if image is None:
                return None
            texture = self._textures[key] = PBRTexture(image, srgb=srgb)
        return texture

    def texture_for(self, name: str) -> Optional[PBRTexture]:
        """A base-colour texture for a texture *name*, or None if it is absent.

        The name goes through the same resolution and the same cache an ordinary
        surface's does, so a frame of an ``animMap`` cycle
        (``SPEC-Q3SHADER §2.4.5``) costs one decode however many surfaces show
        it and however many times it comes round.
        """
        path = self.resolve(name)
        if path is None:
            return None
        return self._texture(path, srgb=True)

    # -- materials -------------------------------------------------------
    def material_for(self, style: SurfaceStyle,
                     lightmap: Optional[np.ndarray] = None,
                     lightmap_key: Optional[int] = None) -> PBRMaterial:
        """The PBR material for a surface style, built once per style and page."""
        key = (style.batch_key(), lightmap_key if lightmap is not None else None)
        material = self._materials.get(key)
        if material is None:
            material = self._materials[key] = self._build(style, lightmap,
                                                          lightmap_key)
        return material

    def _build(self, style: SurfaceStyle, lightmap: Optional[np.ndarray],
               lightmap_key: Optional[int]) -> PBRMaterial:
        textures: Dict[str, PBRTexture] = {}
        base_path = self.resolve(style.name)
        if base_path:
            # A diffuse map is authored in sRGB; the lightmap below is not.
            base = self._texture(base_path, srgb=True)
            if base is not None:
                textures['baseColor'] = base
        texcoord_mask = 0
        strength = 1.0
        if lightmap is not None and style.lightmapped:
            textures['lightmap'] = self._lightmap_texture(lightmap, lightmap_key)
            texcoord_mask |= TEXCOORD_MASK_LIGHTMAP
            strength = self.lightmap_strength
        return PBRMaterial(
            baseColor=(1.0, 1.0, 1.0) if 'baseColor' in textures
            else FALLBACK_BASE_COLOR,
            metallic=0.0,
            roughness=ROUGHNESS_DEFAULT,
            emissiveColor=(0.0, 0.0, 0.0),
            transparency=1.0 - style.opacity if style.transparent else 0.0,
            alphaMode=_alpha_mode(style),
            alphaCutoff=style.alpha_cutoff,
            doubleSided=style.double_sided,
            texCoordMask=texcoord_mask,
            lightmapStrength=strength,
            textures=textures)

    def _lightmap_texture(self, page: np.ndarray,
                          key: Optional[int]) -> PBRTexture:
        """A cached texture for one atlas page.

        A lightmap holds light rather than colour: its luxels are linear
        samples, so the channel must not be marked sRGB and gamma-decoded.
        """
        if key is not None and key in self._lightmaps:
            return self._lightmaps[key]
        from PIL import Image
        texture = PBRTexture(Image.fromarray(np.asarray(page, np.uint8), 'RGB'),
                             srgb=False)
        if key is not None:
            self._lightmaps[key] = texture
        return texture


def _alpha_mode(style: SurfaceStyle) -> str:
    """glTF alpha mode for a style.

    ``SPEC-Q3SHADER §2.3`` makes a mask a discard rather than a blend, so the
    two are distinct modes rather than degrees of one.
    """
    if style.masked:
        return 'MASK'
    if style.transparent:
        return 'BLEND'
    return 'OPAQUE'


def _safe_join(root: str, relative: str) -> Optional[str]:
    """Join a content-supplied path to a root, refusing to escape it.

    Map content is untrusted: a texture name is attacker-controlled for any map
    from the internet, so a name containing `..` or an absolute path must not
    read outside the content root.
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


def _open_image(path: Optional[str]) -> Any:
    """Decode an image file, or None if it cannot be read."""
    if not path:
        return None
    try:
        from PIL import Image
        image = Image.open(path)
        image.load()
        return image
    except Exception as error:                  # noqa: BLE001 - never fail a load
        log.warning('cannot read texture %s: %s', path, error)
        return None
