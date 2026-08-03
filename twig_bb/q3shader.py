"""Quake 3 `.shader` material scripts.

Everything here cites ``SPEC-Q3SHADER``.  This is where a version 46 map's
surface behaviour comes from: ``SPEC-BSP46 §6.2`` records no flag values for
that family and E.1 explains why none are interpreted, so translucency,
masking, culling, sky and lightmapping are all read out of the material scripts
instead — which are content, not engine data.

The language is line-oriented in a way `.rscript` is not (``SPEC-Q3SHADER
§1.3``, ``§2.1.1``): `//` comments to the end of the line, and a directive's
arguments never span a line, so an unrecognised directive is skipped by the
line rather than by a known argument count.  The two languages therefore get
two tokenisers, not one.

The output is a :class:`Material` per name, which reduces to the shared
:class:`~twig_bb.surfaces.SurfaceStyle` so nothing downstream branches on
map family.
"""

from __future__ import annotations

import glob
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from . import surfaceanim
from .surfaces import SurfaceStyle

log = logging.getLogger(__name__)

SCRIPT_DIR = 'scripts'
SCRIPT_EXTENSION = '.shader'

#: ``SPEC-Q3SHADER §2.3`` -- reserved `map` arguments that name no file.
LIGHTMAP_TOKEN = '$lightmap'
WHITE_IMAGE_TOKEN = '$whiteimage'

#: ``SPEC-Q3SHADER §2.1`` -- values of `cull` that turn backface culling off.
TWO_SIDED_CULL = frozenset(('none', 'disable', 'twosided'))

#: ``SPEC-Q3SHADER §2.2`` -- surface parameters this viewer acts on.
PARM_SKY = 'sky'
PARM_TRANS = 'trans'
PARM_NOLIGHTMAP = 'nolightmap'
PARM_NONSOLID = 'nonsolid'
PARM_ALPHASHADOW = 'alphashadow'
LIQUID_PARMS = frozenset(('water', 'slime', 'lava'))
#: Compile-time and gameplay volumes that are never drawn.
UNDRAWN_PARMS = frozenset((
    'nodraw', 'trigger', 'clip', 'playerclip', 'botclip', 'origin', 'hint',
    'skip'))

#: ``SPEC-Q3SHADER §2.3`` -- the blend that leaves a surface opaque.
OPAQUE_BLEND = ('gl_one', 'gl_zero')

#: Stage keywords whose first argument is a texture path (``§2.3``).
TEXTURE_KEYWORDS = ('map', 'clampmap')

#: Opacity given to a surface the scripts call translucent.  The language says
#: *that* a surface blends, not by how much (``SPEC-Q3SHADER §2.2``, ``§2.3``),
#: unlike version 38's two explicit fractions (``SPEC-BSP38 §8.1``).
TRANSLUCENT_OPACITY = 0.5


@dataclass
class Material:
    """One `.shader` definition, reduced to what a PBR viewer can express."""

    name: str
    image: str = ''
    draw: bool = True
    sky: bool = False
    solid: bool = True
    masked: bool = False
    double_sided: bool = False
    transparent: bool = False
    lightmapped: bool = True
    liquid: bool = False
    #: Which liquid this material's surfaces bound (``SPEC-Q3SHADER §2.2``).
    liquidKind: str = ''
    surfaceparms: Set[str] = field(default_factory=set)
    #: What this material does over time (``SPEC-Q3SHADER §2.4``).
    animation: surfaceanim.SurfaceAnimation = field(
        default_factory=surfaceanim.SurfaceAnimation)

    def style(self) -> SurfaceStyle:
        """This material as the shared surface-style value object."""
        return SurfaceStyle(
            name=self.image or self.name,
            draw=self.draw and not self.sky,
            sky=self.sky,
            opacity=TRANSLUCENT_OPACITY if self.transparent else 1.0,
            masked=self.masked,
            double_sided=self.double_sided,
            lightmapped=self.lightmapped and not self.transparent,
            solid=self.solid,
            liquid=self.liquid,
            liquidKind=self.liquidKind,
            animation=self.animation,
            # The two flags the style has always declared finally mean
            # something: one says the image slides, the other that the surface
            # itself moves under it.
            scrolling=any(isinstance(m, surfaceanim.TCModScroll)
                          for m in self.animation.tcmods),
            warping=(bool(self.animation.deforms)
                     or any(isinstance(m, surfaceanim.TCModTurb)
                            for m in self.animation.tcmods)),
            # SPEC-BSP46 §6.2: nothing here reads a v46 surface-flags bit, so
            # shininess and emission have no source in this family.
            casts_shadow=not self.sky,
        )


#: The editor and compiler volumes — clip brushes, caulk seals, hints, area
#: portals, triggers.  Their ``surfaceparm nodraw`` (``SPEC-Q3SHADER §2.2``)
#: lives in the *base game's* own ``scripts/common.shader``, not in a map's
#: archive, so a map loaded without the base scripts has no definition for them
#: and they fall through to being treated as ordinary textures — which paints
#: solid grey walls exactly where the original draws nothing.  The prefix is
#: mapping vocabulary every level editor uses.
COMMON_PREFIX = 'textures/common/'


def style_for(materials: Dict[str, Material], texture_name: str) -> SurfaceStyle:
    """The style of a named texture, defined or not.

    ``SPEC-Q3SHADER §3.2``: a name with no definition in any script is not an
    error — the name is simply used as a texture path.  The one exception is
    the ``textures/common/`` set, which is never drawn; see
    :data:`COMMON_PREFIX`.  A script that *does* define one of those names
    still wins, since this is a fallback for an absent definition rather than
    an override.
    """
    material = materials.get(texture_name.lower())
    if material is not None:
        return material.style()
    if texture_name.lower().startswith(COMMON_PREFIX):
        # Undrawn but still solid: a clip brush is invisible *and* blocks
        # movement, so dropping the collision along with the drawing would open
        # a hole in every map that uses one.
        return SurfaceStyle(name=texture_name, draw=False, lightmapped=False,
                            scripted=False)
    # Marked unscripted so it can be *reported*.  A map naming a base-game
    # shader nobody has -- `textures/liquids/protolava`, say -- draws a still,
    # untextured surface, and without saying so the viewer looks broken rather
    # than under-supplied.
    return SurfaceStyle(name=texture_name, scripted=False)


def load_scripts(roots: Sequence[str]) -> Dict[str, Material]:
    """Read every `.shader` under ``roots``; later definitions win (``§3.1``)."""
    materials: Dict[str, Material] = {}
    for root in roots:
        pattern = os.path.join(root, SCRIPT_DIR, '*' + SCRIPT_EXTENSION)
        for path in sorted(glob.glob(pattern)):
            try:
                with open(path, 'r', errors='replace') as handle:
                    text = handle.read()
            except OSError as error:
                log.warning('cannot read %s: %s', path, error)
                continue
            materials.update(parse(text))
    return materials


def parse(text: str) -> Dict[str, Material]:
    """Parse one `.shader` file into ``{lower-case name: material}``."""
    tokens = _tokenize(text)
    materials: Dict[str, Material] = {}
    index = 0
    while index < len(tokens):
        name, line = tokens[index]
        index += 1
        if name in ('{', '}'):
            continue
        if index >= len(tokens) or tokens[index][0] != '{':
            continue                            # a bare token names nothing
        material, index = _parse_body(name, tokens, index + 1)
        materials[material.name] = material     # §3.1: later definitions win
    return materials


def _tokenize(text: str) -> List[Tuple[str, int]]:
    """``(token, line number)`` pairs, with comments stripped.

    ``SPEC-Q3SHADER §1.3``: `//` comments to the end of the line and needs no
    preceding whitespace, so it is cut before splitting.  ``§1.5``: braces are
    tokens even when glued to their neighbours.  The line number is kept
    because ``§2.1.1`` skips an unrecognised directive by its line.
    """
    tokens: List[Tuple[str, int]] = []
    for number, raw in enumerate(text.splitlines()):
        comment = raw.find('//')
        if comment >= 0:
            raw = raw[:comment]
        for token in raw.replace('{', ' { ').replace('}', ' } ').split():
            tokens.append((token, number))
    return tokens


class _Body:
    """Accumulator for one material's directives while it is being parsed."""

    def __init__(self, name: str) -> None:
        self.material = Material(name=name.lower())
        self.stage_images: List[str] = []
        self.editor_image = ''
        #: Each stage's blend, by stage index.  **By index and not as a
        #: list**, because which stage blends is the whole question: a
        #: material draws its stages in order, one over another, so whether
        #: the *surface* is see-through is decided by the first of them and
        #: not by any of them.
        self.blends: Dict[int, Tuple[str, str]] = {}
        self.samples_lightmap = False
        #: Animation directives, gathered as they are met.  Stage directives
        #: are taken from the *first drawable* stage only: one PBR material
        #: draws one stage, so a second stage's ``tcMod`` describes a layer
        #: that is not being drawn (``SPEC-Q3SHADER E.1``, ``E.3``).
        self.deforms: List[surfaceanim.Deform] = []
        self.tcmods: List[surfaceanim.TCMod] = []
        self.rgbgen: Optional[surfaceanim.ColorGen] = None
        self.alphagen: Optional[surfaceanim.AlphaGen] = None
        self.animmap: Optional[surfaceanim.AnimMap] = None
        #: The stage whose image the material draws, and therefore the only
        #: stage whose animation means anything here.  -1 until one is seen.
        self.image_stage = -1
        self.stage_index = -1
        #: The index the first stage was given, so "did the first stage blend"
        #: can be asked without assuming where the counting started.
        self.first_stage = 0


def _parse_body(name: str, tokens: List[Tuple[str, int]], index: int):
    """Parse a material body from ``index`` until its closing brace."""
    body = _Body(name)
    depth = 1
    while index < len(tokens) and depth > 0:
        token, line = tokens[index]
        if token == '{':
            depth += 1
            if depth == 2:
                body.stage_index += 1
            index += 1
            continue
        if token == '}':
            depth -= 1
            index += 1
            continue
        arguments, index = _arguments(tokens, index + 1, line, token.lower())
        keyword = token.lower()
        if depth > 1:
            _stage_directive(body, keyword, arguments)
        else:
            _general_directive(body, keyword, arguments)
    return _finish(body), index


#: Argument counts for the keywords this viewer reads (``SPEC-Q3SHADER §2.1``,
#: ``§2.3``).  Knowing them lets several directives share a line, which shipped
#: content does; ``§2.1.1`` covers everything else, which is skipped by the line.
_ARITY = {
    'surfaceparm': 1, 'cull': 1, 'skyparms': 3, 'qer_editorimage': 1,
    'map': 1, 'clampmap': 1, 'alphafunc': 1,
}

#: `blend`, `add` and `filter` are one-token shorthands for a blend function;
#: anything else is a pair of GL factor names (``SPEC-Q3SHADER §2.3``).
_BLEND_SHORTHANDS = frozenset(('add', 'filter', 'blend'))


def _arguments(tokens: List[Tuple[str, int]], index: int, line: int,
               keyword: str) -> Tuple[List[str], int]:
    """A directive's arguments (``SPEC-Q3SHADER §2.1.1``).

    Arguments never span a line and never cross a brace, so the line bounds
    them at worst.  A keyword whose arity is known takes exactly that many, so
    a line carrying several directives still parses; an unknown keyword takes
    the rest of its line, which cannot desynchronise anything.
    """
    available: List[str] = []
    while index < len(tokens):
        token, token_line = tokens[index]
        if token_line != line or token in ('{', '}'):
            break
        available.append(token)
        index += 1
    wanted = _wanted(keyword, available)
    if wanted is None or wanted >= len(available):
        return available, index
    return available[:wanted], index - (len(available) - wanted)


def _wanted(keyword: str, available: List[str]) -> Optional[int]:
    """How many tokens ``keyword`` consumes, or None for "the rest of the line"."""
    if keyword == 'blendfunc':
        return 1 if available and available[0].lower() in _BLEND_SHORTHANDS else 2
    return _ARITY.get(keyword)


def _general_directive(body: _Body, keyword: str, arguments: List[str]) -> None:
    """Apply one body-level directive (``SPEC-Q3SHADER §2.1``)."""
    material = body.material
    if keyword == 'surfaceparm' and arguments:
        _surfaceparm(material, arguments[0].lower())
    elif keyword == 'cull' and arguments:
        material.double_sided = arguments[0].lower() in TWO_SIDED_CULL
    elif keyword == 'skyparms':
        material.sky = True
    elif keyword == 'qer_editorimage' and arguments:
        body.editor_image = arguments[0]
    elif keyword == 'deformvertexes':
        deform = surfaceanim.parse_deform(arguments)
        if deform is not None:
            body.deforms.append(deform)
    # §2.1, §2.1.1: everything else -- the q3map_* family, fogparms, sort,
    # tessSize and any unknown keyword -- is skipped.


def _surfaceparm(material: Material, value: str) -> None:
    """Apply one `surfaceparm` value (``SPEC-Q3SHADER §2.2``)."""
    material.surfaceparms.add(value)
    if value in UNDRAWN_PARMS:
        material.draw = False
    if value == PARM_SKY:
        material.sky = True
    if value == PARM_NONSOLID:
        material.solid = False
    if value == PARM_NOLIGHTMAP:
        material.lightmapped = False
    if value == PARM_ALPHASHADOW:
        material.masked = True
    if value in LIQUID_PARMS:
        # A liquid is a volume to swim in, not a surface to stand on
        # (``SPEC-Q3SHADER §2.2`` names the three; ``SPEC-BSP38 §9.4`` states
        # the rule the other family words explicitly -- what stops a player is
        # solid, playerclip and window, and a liquid is none of them).
        material.liquid = True
        # Which one, which the version 38 side has no way to say from a face.
        material.liquidKind = value
        material.solid = False
    if value == PARM_TRANS or value in LIQUID_PARMS:
        material.transparent = True
        material.lightmapped = False


def _stage_directive(body: _Body, keyword: str, arguments: List[str]) -> None:
    """Apply one stage directive (``SPEC-Q3SHADER §2.3``, ``§2.4``)."""
    if keyword in ANIMATION_KEYWORDS:
        _animation_directive(body, keyword, arguments)
        return
    if keyword in TEXTURE_KEYWORDS and arguments:
        token = arguments[0]
        lowered = token.lower()
        if lowered == LIGHTMAP_TOKEN:
            body.samples_lightmap = True        # §2.3.2
        elif lowered != WHITE_IMAGE_TOKEN:
            _claim_image(body)
            body.stage_images.append(token)
    elif keyword == 'animmap' and len(arguments) > 1:
        # §2.3: a rate then frame names; the first frame stands in, and §2.4.5
        # says what the rest of them do.
        _claim_image(body)
        body.stage_images.append(arguments[1])
        _claim_stage(body)
        if body.animmap is None:
            body.animmap = surfaceanim.parse_animmap(arguments)
    elif keyword == 'blendfunc' and arguments:
        body.blends[body.stage_index] = _blend(arguments)
    elif keyword == 'alphafunc':
        body.material.masked = True
    # §2.3: tcGen, depthFunc, depthWrite and detail are parsed and ignored.


#: Stage directives that describe animation rather than a texture or a blend.
ANIMATION_KEYWORDS = ('tcmod', 'rgbgen', 'alphagen')


def _claim_image(body: _Body) -> None:
    """Note this stage as the one the material draws, if none has been.

    ``§2.3.1``: the drawable image is the *first* stage's map, so the first
    stage to offer one is the stage this viewer puts on screen -- and the only
    one whose animation it can honour.
    """
    if body.image_stage < 0:
        body.image_stage = body.stage_index


def _claim_stage(body: _Body) -> bool:
    """Whether this stage is the one whose animation is taken.

    **The stage that is drawn**, which is the first with an image of its own
    (``§2.3.1``) -- not the first that happens to animate.  A viewer drawing
    one PBR material draws that one stage, so a `tcMod` on a later stage
    describes a layer it never puts on screen, and applying it to the base
    moves the wrong thing.

    That is not a small difference.  A lit panel with a faint glow scrolling
    across it on an additive third stage had the *panel* racing past at 0.7
    texture widths a second, because the third stage's scroll was the first
    animation anyone declared and it claimed the material.
    """
    return body.stage_index == body.image_stage


def _animation_directive(body: _Body, keyword: str, arguments: List[str]) -> None:
    """Apply one animation directive from a stage (``SPEC-Q3SHADER §2.4``)."""
    if not _claim_stage(body):
        return
    if keyword == 'tcmod':
        modifier = surfaceanim.parse_tcmod(arguments)
        if modifier is not None:
            body.tcmods.append(modifier)
    elif keyword == 'rgbgen':
        color = surfaceanim.parse_rgbgen(arguments)
        if color is not None:
            body.rgbgen = color
    elif keyword == 'alphagen':
        opacity = surfaceanim.parse_alphagen(arguments)
        if opacity is not None:
            body.alphagen = opacity


def _blend(arguments: List[str]) -> Tuple[str, str]:
    """A blend function as a pair of factor names (``SPEC-Q3SHADER §2.3``).

    The one-token shorthands `add`, `filter` and `blend` all describe blends
    that are not opaque, so they map to a pair that is not the opaque one.
    """
    lowered = [token.lower() for token in arguments[:2]]
    if len(lowered) == 1:
        return ('shorthand', lowered[0])
    return (lowered[0], lowered[1])


def _finish(body: _Body) -> Material:
    """Resolve the accumulated directives into the finished material."""
    material = body.material
    # §2.3.1: the first drawable stage map, then the editor image, then the
    # material's own name.
    material.image = (body.stage_images[0] if body.stage_images
                      else body.editor_image or material.name)
    # §2.3: the stages are drawn in order, each over the one before, so the
    # **first** decides whether the surface is see-through.  A first stage with
    # no blend is an opaque surface and everything after it -- an environment
    # reflection, an additive glow, the lightmap -- is detail painted on top.
    # Reading *any* stage's blend as transparency made every lit floor in the
    # game a sheet of glass with the room below showing through it.
    first = min(body.blends) if body.blends else None
    if first is not None and first == body.first_stage:
        if body.blends[first] != OPAQUE_BLEND:
            material.transparent = True
    if material.masked:
        material.transparent = False            # a cut-out is not blending
    material.lightmapped = (material.lightmapped and body.samples_lightmap
                            and not material.transparent)   # §2.3.2
    material.animation = surfaceanim.SurfaceAnimation(
        tcmods=tuple(body.tcmods), deforms=tuple(body.deforms),
        rgbgen=body.rgbgen, alphagen=body.alphagen, animmap=body.animmap)
    return material
