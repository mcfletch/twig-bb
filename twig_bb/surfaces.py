"""How a surface looks, expressed independently of the material scripts.

A :class:`SurfaceStyle` is the single vocabulary in which translucency,
masking, double-sidedness, scrolling, sky, shininess and lightmapping are
stated.  The reader translates a texture name's material script into one of
these, so nothing downstream — batching, materials, the scene builder, the
collision mesh — ever branches on how the surface was described.

The translation is script-driven and lives in :mod:`twig_bb.q3shader`, since
``SPEC-BSP46 §6.2`` records no flag values on a surface and the viewer
interprets none.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Tuple

from .surfaceanim import SurfaceAnimation

# Alpha below which a masked texel is discarded.  SPEC-Q3SHADER §2.3:
# `alphaFunc GE128` keeps a texel whose alpha is at least 128 of 255.
ALPHA_CUTOFF = 128.0 / 255.0

#: Image extensions stripped from a texture name.  ``SPEC-BSP46 §6.1`` names
#: carry none, but ``SPEC-Q3SHADER §1.6`` paths inside a material script do, and
#: both end up naming a style; left alone, one texture would become two styles,
#: two batches and two copies of the same image.
IMAGE_EXTENSIONS = ('.tga', '.jpg', '.jpeg', '.png', '.pcx', '.wal')


def normalise_texture_name(name: str) -> str:
    """One spelling for a texture path, whatever the map or script wrote.

    Separators become forward slashes (``SPEC-BSP38 §6.4``, ``SPEC-BSP46 §6.1``
    both specify forward slashes, but real content contains backslashes), and a
    trailing image extension is dropped.
    """
    cleaned = name.replace('\\', '/')
    stem, _, extension = cleaned.rpartition('.')
    if stem and ('.' + extension.lower()) in IMAGE_EXTENSIONS:
        return stem
    return cleaned


@dataclass(frozen=True)
class SurfaceStyle:
    """The appearance and physical role of one surface, family-independent."""

    #: Texture path as the map names it, with no extension.
    name: str
    #: False for a surface that exists only for compilation or collision.
    draw: bool = True
    #: True where the skybox shows through instead of the surface.
    sky: bool = False
    #: 1.0 opaque; below that the surface is alpha-blended.
    opacity: float = 1.0
    #: True for a binary alpha cut-out rather than blending.
    masked: bool = False
    #: Discard threshold for a masked surface.
    alpha_cutoff: float = ALPHA_CUTOFF
    #: True where backface culling must be off.
    double_sided: bool = False
    #: True where the texture coordinates scroll over time.
    scrolling: bool = False
    #: True where the surface is deformed at run time (liquid turbulence).
    warping: bool = False
    #: True where a baked lightmap applies to this surface.
    lightmapped: bool = True
    #: True where the surface emits light.
    emissive: bool = False
    #: True where the surface is written into shadow maps.
    casts_shadow: bool = True
    #: True where the surface blocks movement.
    solid: bool = True
    #: True where the surface bounds a liquid volume -- water, slime or lava.
    liquid: bool = False
    #: True where a material script *defined* this surface.  A name with no
    #: definition is not an error (``SPEC-Q3SHADER §3.2``) — it is used as a
    #: plain texture path — but it is also a surface that has silently lost
    #: whatever the script said about it, including its animation.  A still
    #: pool of lava then reads as a broken animator rather than as content the
    #: user does not have, so this is carried in order to be *reported*.
    scripted: bool = True
    #: *Which* liquid the material script names: `water`, `slime` or `lava`,
    #: empty otherwise (``SPEC-Q3SHADER §2.2``).  Separate from :attr:`liquid`
    #: because what tints the view and how much it hurts both depend on it.
    liquidKind: str = ''
    #: What the surface does over time: scrolling texture coordinates, vertex
    #: deformation, a colour wave, a frame cycle.  ``SPEC-Q3SHADER §2.4``
    #: describes them; :mod:`twig_bb.surfaceanim` evaluates them.
    animation: SurfaceAnimation = field(default_factory=SurfaceAnimation)

    def __post_init__(self) -> None:
        # Normalising here rather than at each call site means every producer of
        # a style -- both families' flags and the material scripts -- ends up
        # with the same spelling, so styles compare and batch as one.
        object.__setattr__(self, 'name', normalise_texture_name(self.name))

    @property
    def animated(self) -> bool:
        """Whether this surface changes over time and so must be re-uploaded."""
        return self.animation.animated

    @property
    def transparent(self) -> bool:
        """Whether the surface must be drawn in the blended pass."""
        return self.opacity < 1.0

    def replace(self, **changes: Any) -> 'SurfaceStyle':
        """A copy with ``changes`` applied; the original is untouched.

        A material script refines what the map's own flags said, so the two
        sources compose rather than one overwriting the other.
        """
        return replace(self, **changes)

    def batch_key(self) -> Tuple[Any, ...]:
        """Grouping key: surfaces with an equal key may share one draw call."""
        return (self.name, self.draw, self.sky, self.opacity, self.masked,
                self.double_sided, self.scrolling, self.warping,
                self.lightmapped, self.emissive, self.casts_shadow, self.liquid,
                self.liquidKind, self.scripted,
                # Two surfaces that move differently cannot share a draw call,
                # however alike the rest of them is.
                self.animation)
