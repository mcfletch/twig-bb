"""How a surface looks, expressed once for every map family.

A :class:`SurfaceStyle` is the single vocabulary in which translucency,
masking, double-sidedness, scrolling, sky, shininess and lightmapping are
stated.  Each family's reader translates its own flags or material scripts into
one of these, so nothing downstream — batching, materials, the scene builder,
the collision mesh — ever branches on which family a map came from.

The version 38 translation lives here because it is a pure reading of
``SPEC-BSP38 §8.1`` — the stock Quake 2 bits, which are the only ones this
viewer reads.  The Quake 3 translation is script-driven and lives in
:mod:`twitchoglc.q3shader`, since ``SPEC-BSP46 §6.2`` records no flag values
for that family and the viewer interprets none.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Tuple

from . import q2bsp
from .surfaceanim import SurfaceAnimation, flowing_animation

# SPEC-BSP38 §8.1: TRANS33 draws at roughly one-third opacity and TRANS66 at
# roughly two-thirds.
OPACITY_TRANS33 = 1.0 / 3.0
OPACITY_TRANS66 = 2.0 / 3.0

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
    #: What the surface does over time: scrolling texture coordinates, vertex
    #: deformation, a colour wave, a frame cycle.  ``SPEC-Q3SHADER §2.4``
    #: describes them; :mod:`twitchoglc.surfaceanim` evaluates them.  Both
    #: families produce one of these, so nothing downstream branches on which
    #: map format asked for the movement.
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
                # Two surfaces that move differently cannot share a draw call,
                # however alike the rest of them is.
                self.animation)


def style_from_quake2_flags(name: str, flags: int) -> SurfaceStyle:
    """Read a version 38 texinfo surface-flags word into a style.

    Only the stock Quake 2 bits of ``SPEC-BSP38 §8.1`` are read.  ``§8.4``
    requires unrecognised bits to be ignored rather than rejected, which falls
    out of testing only the bits named there — and covers the additions §8.2
    records for engines this viewer no longer targets.

    The warp flag also marks the surface as a liquid: version 38 keeps its
    contents on brushes and leaves rather than on a face (``SPEC-BSP38 §9.1``),
    so the warp a compiler puts on the faces of a water, slime or lava volume
    is what a face-based reader has to go by.  A liquid does not block a player
    -- ``§9.4`` names solid, playerclip and window as what does -- so it is left
    out of the collision mesh and swum through instead.

    ``SPEC-BSP38 §7.8`` decides the lightmap: a warped, sky or nodraw surface
    carries none, and a translucent one is drawn blended and unlit for the same
    reason ``SPEC-Q3SHADER §2.2`` gives in the other family.  Nothing here sets
    ``double_sided``: version 38 has no flag for it.
    """
    sky = bool(flags & q2bsp.SURF_SKY)
    warping = bool(flags & q2bsp.SURF_WARP)
    nodraw = bool(flags & q2bsp.SURF_NODRAW)
    opacity = 1.0
    if flags & q2bsp.SURF_TRANS33:
        opacity = OPACITY_TRANS33
    elif flags & q2bsp.SURF_TRANS66:
        opacity = OPACITY_TRANS66
    return SurfaceStyle(
        name=name,
        draw=not nodraw,
        sky=sky,
        opacity=opacity,
        scrolling=bool(flags & q2bsp.SURF_FLOWING),
        # A flowing surface is expressed as the same value object a `.shader`
        # script produces, so the renderer never learns which family asked.
        animation=(flowing_animation() if flags & q2bsp.SURF_FLOWING
                   else SurfaceAnimation()),
        warping=warping,
        liquid=warping,
        solid=not warping,
        lightmapped=not (sky or warping or nodraw or opacity < 1.0),
        emissive=bool(flags & q2bsp.SURF_LIGHT),
        # Sky is never written into a shadow map: it is a hole showing the
        # backdrop, not a surface (SPEC-BSP38 §8.1).
        casts_shadow=not sky,
    )
