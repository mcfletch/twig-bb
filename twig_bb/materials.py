"""Resolve texture names to images, and surface styles to PBR materials.

Two lookups live here.  **Where a name's image is**: a version 46 name is
already rooted at the archive (``SPEC-BSP46 §6.1``, ``§7.3``), and the extension
it arrives with is advisory, so the supported ones are tried in turn
(``SPEC-Q3SHADER §1.6``).

**What a style becomes**: a :class:`SurfaceStyle` maps onto one ``PBRMaterial``.

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

from . import crnfile
from .contentsearch import ContentSearch
from .surfaces import SurfaceStyle

log = logging.getLogger(__name__)

#: Extension search order, first hit wins (``SPEC-Q3SHADER §1.6``,
#: ``SPEC-BSP46 §7.3``).
#:
#: `.webp` and `.crn` come last, after every format the older content uses, so
#: a tree holding both spellings of a texture is read in whichever the content
#: it was authored against would have used.  `.crn` is Crunch
#: (:mod:`twig_bb.crnfile`, ``SPEC-CRN``) and needs an optional package; the
#: extension is listed either way, since a name that resolves to a file this
#: build cannot decode is a clearer thing to report than a name that resolves
#: to nothing.
TEXTURE_EXTENSIONS = ('.tga', '.jpg', '.png', '.jpeg', '.webp', '.crn')

#: Size assumed for a texture whose image is absent.  ``SPEC-BSP46 §6.2``
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

#: The middle brightness :data:`DEFAULT_LIGHTMAP_STRENGTH` was chosen against,
#: as :meth:`~twig_bb.lightmapatlas.LightmapAtlas.median_luxel` measures it.
#: The median of the per-map medians of twelve Quake 3 levels; the same twelve
#: run from 0.049 to 0.72, so this is a centre and not a bound.
REFERENCE_MEDIAN_LUXEL = 0.0986

#: A trailing light value on a shader name: `light1_5000`, `baslt4_1_2k`,
#: `gothic_light2_4K`.  See :meth:`MaterialLibrary._light_variant`.
LIGHT_VARIANT = re.compile(r'^(.+)_\d+k?$', re.IGNORECASE)


def auto_lightmap_strength(median: Optional[float]) -> float:
    """The exposure for a map whose baked light sits at ``median``.

    **A ceiling, never a brightener.** A map baked brighter than
    :data:`REFERENCE_MEDIAN_LUXEL` is pulled back until its middle brightness
    lands there; a map baked at or below it is left at
    :data:`DEFAULT_LIGHTMAP_STRENGTH` and keeps whatever darkness its author
    baked in.

    Both halves of that matter. Normalising in *both* directions would give
    every level the same mid-tone and flatten the difference between a dim
    corridor and a floodlit hangar, which is a decision the map's author
    already made. Not normalising at all leaves content baked on a brighter
    absolute scale washed out — pale surfaces with their shadows lifted —
    which is what this exists to fix, since the exposure was picked against one
    body of content and the scale is not shared between projects.

    ``median`` of None, which is a map with no baked light, takes the default:
    there is nothing to be over-exposed.
    """
    if not median or median <= REFERENCE_MEDIAN_LUXEL:
        return DEFAULT_LIGHTMAP_STRENGTH
    return DEFAULT_LIGHTMAP_STRENGTH * REFERENCE_MEDIAN_LUXEL / median


class MaterialLibrary:
    """Texture lookup and PBR material construction for one map's content."""

    def __init__(self, roots: Sequence[str], family: str = 'quake3',
                 lightmap_strength: float = DEFAULT_LIGHTMAP_STRENGTH) -> None:
        self.roots = [os.path.abspath(root) for root in roots]
        self.family = family
        self.lightmap_strength = float(lightmap_strength)
        self._images: Dict[str, Any] = {}
        self._textures: Dict[Tuple[str, bool], PBRTexture] = {}
        self._materials: Dict[Tuple[Any, ...], PBRMaterial] = {}
        self._lightmaps: Dict[int, PBRTexture] = {}
        self._files = ContentSearch(self.roots)

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
        found = self._search(candidate, TEXTURE_EXTENSIONS)
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

        A version 46 name already carries its own root (``SPEC-BSP46 §6.1``).
        """
        return os.path.splitext(name.replace('\\', '/'))[0]

    def _search(self, relative: str, extensions: Sequence[str]) -> Optional[str]:
        """First existing file for ``relative`` + each extension, in each root.

        The search itself is :class:`~twig_bb.contentsearch.ContentSearch`,
        shared with every other kind of asset a map names.
        """
        return self._files.find(relative, extensions)

    # -- images ----------------------------------------------------------
    def image(self, name: str) -> Any:
        """The decoded image for a texture name, or None; loaded once."""
        if name not in self._images:
            path = self.resolve(name)
            self._images[name] = open_image(path) if path else None
        return self._images[name]

    def texture_size(self, name: str) -> Tuple[int, int]:
        """``(width, height)`` of a texture's image (``SPEC-BSP46 §6.2``)."""
        image = self.image(name)
        if image is None:
            return FALLBACK_TEXTURE_SIZE
        return (int(image.size[0]), int(image.size[1]))

    def _texture(self, path: str, srgb: bool) -> Optional[PBRTexture]:
        """A cached :class:`PBRTexture` for a file, or None if it will not open."""
        key = (path, srgb)
        texture = self._textures.get(key)
        if texture is None:
            image = open_image(path)
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


def open_image(path: Optional[str]) -> Any:
    """Decode an image file, or None if it cannot be read.

    Crunch textures (``SPEC-CRN``) are block-compressed and go to
    :mod:`twig_bb.crnfile`; everything else is a format the imaging library
    reads for itself.
    """
    if not path:
        return None
    if os.path.splitext(path)[1].lower() == crnfile.EXTENSION:
        return crnfile.load(path)
    try:
        from PIL import Image
        image = Image.open(path)
        image.load()
        return image
    except Exception as error:                  # noqa: BLE001 - never fail a load
        log.warning('cannot read texture %s: %s', path, error)
        return None
