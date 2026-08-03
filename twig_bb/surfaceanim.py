"""Surfaces that move: the animation directives, and what they evaluate to.

Everything ``SPEC-Q3SHADER §2.4`` describes is a **pure function of scene time**
and nothing else.  That single property is what makes this module worth having
on its own: a whole map's surfaces animate in step because they are all asked
the same question -- *what do you look like at t?* -- and every answer is a
number a test can assert about, with no window, no map and no content.

Four families, and they differ in what they cost to apply:

:class:`TCModScroll` and friends
    Texture-coordinate modification.  Composes into **one 3x3 matrix** per
    material per frame, whatever the directives are, so a scrolling conveyor
    belt and a rotating fan cost a uniform each.  The one exception is
    :class:`TCModTurb`, whose offset depends on where a vertex *is* and so
    cannot be folded into a transform; it is kept separate rather than
    approximated.
:class:`DeformWave` and friends
    Geometry that moves.  This is what makes a water surface heave, and it is
    the expensive one: it touches vertices rather than a uniform.
:class:`ColorGen`
    Colour and opacity over time -- a pulsing glow, a flickering light.
:class:`AnimMap`
    A texture that cycles through frames.

The evaluation is vectorised over numpy arrays where a caller has many vertices
or many times, and returns plain floats where it does not, because both callers
exist and neither should have to convert.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple, Union

import numpy as np

#: ``SPEC-Q3SHADER §2.4.2``: texture coordinates turn about the centre of the
#: image, not about the origin.
TEXTURE_CENTRE = 0.5

#: ``SPEC-Q3SHADER §2.4.1``: an unrecognised wave function is treated as `sin`.
#: Content misspells these, and a surface that does not move at all is a more
#: visible error than one that moves with the commonest shape.
DEFAULT_WAVE = 'sin'

#: Below this a `stretch` wave would magnify without bound.  The directive
#: divides by the wave's value, and a wave crossing zero is a surface that
#: momentarily fills the screen.
MIN_STRETCH = 1e-3

#: ``SPEC-Q3SHADER §2.4.2.1``: `turb`'s dependence on vertex position is
#: described but not given as a formula, so the spatial term is **a choice**.
#: This is it: the three world coordinates are summed and scaled, which gives a
#: churn that travels across a surface rather than sliding along one axis.
TURB_SPATIAL_SCALE = 1.0 / 128.0

Number = Union[float, np.ndarray]


def _fraction(value: Number) -> Number:
    """The part of ``value`` after the decimal point, always in ``[0, 1)``.

    Python's ``%`` already returns a non-negative result for a positive divisor,
    which is what makes a negative phase behave rather than reflecting the wave.
    """
    return np.mod(value, 1.0)


def wave_shape(function: str, position: Number) -> Number:
    """One cycle of a named wave, at ``position`` through it.

    ``position`` is taken modulo 1, so any argument is on the cycle.  The
    **ranges differ between the shapes** -- ``sin`` and ``square`` are centred on
    zero, the rest are not -- and that is the specification's own definition
    rather than an oversight to normalise away: content is authored against it,
    and evening them up renders the wrong amplitude.
    """
    x = _fraction(position)
    name = function.lower()
    if name == 'triangle':
        return 1.0 - np.abs(2.0 * x - 1.0)
    if name == 'square':
        return np.where(x < 0.5, 1.0, -1.0)
    if name == 'sawtooth':
        return x
    if name == 'inversesawtooth':
        return 1.0 - x
    if name == 'noise':
        # Held for the cycle, and the same every run: a surface that flickers
        # differently on each launch cannot be compared against a reference
        # image, and the manual asks only that it be unpredictable in time.
        cycle = np.floor(position)
        return _hash_unit(cycle)
    return np.sin(2.0 * np.pi * x)


def _hash_unit(value: Number) -> Number:
    """A repeatable pseudo-random number in ``[0, 1)`` for each whole ``value``."""
    scaled = np.asarray(value, dtype='d') * 12.9898
    return np.asarray(np.abs(np.sin(scaled) * 43758.5453) % 1.0)


@dataclass(frozen=True)
class Wave:
    """A named shape with a base, an amplitude, a phase and a frequency.

    The five tokens ``SPEC-Q3SHADER §2.4.1`` spells out, and the value at time
    ``t`` is ``base + amplitude * f(phase + t * frequency)``.
    """

    function: str = DEFAULT_WAVE
    base: float = 0.0
    amplitude: float = 1.0
    phase: float = 0.0
    frequency: float = 1.0

    def at(self, time: Number, phase_offset: Number = 0.0) -> Number:
        """The wave's value at ``time`` seconds; vectorised over an array.

        ``phase_offset`` shifts where on the cycle this sample is taken, and is
        how a directive spreads one wave across a surface -- a vertex's own
        offset, added to the phase rather than to the time.  Adding it to the
        time instead would make it vanish whenever the frequency is zero, which
        is exactly the case where a surface is meant to hold a fixed ripple.
        """
        return self.base + self.amplitude * wave_shape(
            self.function,
            self.phase + phase_offset + np.asarray(time, dtype='d') * self.frequency)

    @property
    def moving(self) -> bool:
        """Whether this wave changes at all, rather than being a constant."""
        return self.amplitude != 0.0 and self.frequency != 0.0

    @classmethod
    def parse(cls, tokens: Sequence[str]) -> Optional['Wave']:
        """A wave from its five tokens, or None if they are not five numbers."""
        if len(tokens) < 5:
            return None
        try:
            numbers = [float(token) for token in tokens[1:5]]
        except ValueError:
            return None
        return cls(tokens[0].lower(), *numbers)


# ----------------------------------------------------------------------
# Texture-coordinate modification (SPEC-Q3SHADER §2.4.2)
# ----------------------------------------------------------------------


class TCMod:
    """A modification of a stage's texture coordinates.

    Subclasses supply :meth:`matrix`, which is where the whole design pays off:
    however many modifiers a material carries, they compose into one 3x3 and the
    renderer uploads one uniform.
    """

    @property
    def moving(self) -> bool:
        """Whether this modifier changes with time.

        A constant `scale` is a property of the surface rather than an
        animation, and a material carrying only constants needs no re-upload
        per frame.
        """
        return False

    def matrix(self, time: float) -> np.ndarray:
        """This modifier as a 3x3 row-vector transform at ``time``."""
        return np.identity(3)


def _centred(inner: np.ndarray) -> np.ndarray:
    """``inner`` applied about the centre of the image rather than the origin."""
    to_centre = np.identity(3)
    to_centre[2, :2] = (-TEXTURE_CENTRE, -TEXTURE_CENTRE)
    from_centre = np.identity(3)
    from_centre[2, :2] = (TEXTURE_CENTRE, TEXTURE_CENTRE)
    return to_centre @ inner @ from_centre


@dataclass(frozen=True)
class TCModScroll(TCMod):
    """Slide the image, in texture widths per second."""

    s: float = 0.0
    t: float = 0.0

    @property
    def moving(self) -> bool:
        return self.s != 0.0 or self.t != 0.0

    def matrix(self, time: float) -> np.ndarray:
        matrix = np.identity(3)
        matrix[2, :2] = (self.s * time, self.t * time)
        return matrix


@dataclass(frozen=True)
class TCModScale(TCMod):
    """Multiply the coordinates.  Constant: this tiles, it does not animate."""

    s: float = 1.0
    t: float = 1.0

    def matrix(self, time: float) -> np.ndarray:
        matrix = np.identity(3)
        matrix[0, 0], matrix[1, 1] = self.s, self.t
        return matrix


@dataclass(frozen=True)
class TCModRotate(TCMod):
    """Turn the image about its centre, in degrees per second."""

    degrees: float = 0.0

    @property
    def moving(self) -> bool:
        return self.degrees != 0.0

    def matrix(self, time: float) -> np.ndarray:
        angle = math.radians(self.degrees * time)
        cos, sin = math.cos(angle), math.sin(angle)
        inner = np.identity(3)
        inner[0, 0], inner[0, 1] = cos, sin
        inner[1, 0], inner[1, 1] = -sin, cos
        return _centred(inner)


@dataclass(frozen=True)
class TCModStretch(TCMod):
    """Scale about the centre by the reciprocal of a wave.

    The reciprocal is what makes it a *stretch*: a wave above one shrinks the
    image and so stretches what is drawn on it.
    """

    wave: Wave = field(default_factory=Wave)

    @property
    def moving(self) -> bool:
        return self.wave.moving

    def matrix(self, time: float) -> np.ndarray:
        value = float(self.wave.at(time))
        scale = 1.0 / (value if abs(value) >= MIN_STRETCH else MIN_STRETCH)
        inner = np.identity(3)
        inner[0, 0] = inner[1, 1] = scale
        return _centred(inner)


@dataclass(frozen=True)
class TCModTransform(TCMod):
    """A general affine transform of the coordinates.  Constant."""

    m00: float = 1.0
    m01: float = 0.0
    m10: float = 0.0
    m11: float = 1.0
    t0: float = 0.0
    t1: float = 0.0

    def matrix(self, time: float) -> np.ndarray:
        matrix = np.identity(3)
        matrix[0, :2] = (self.m00, self.m01)
        matrix[1, :2] = (self.m10, self.m11)
        matrix[2, :2] = (self.t0, self.t1)
        return matrix


@dataclass(frozen=True)
class TCModTurb(TCMod):
    """Churn the coordinates by an amount that depends on where a vertex is.

    The one modifier that is **not** an affine transform, so it never enters the
    composed matrix -- :meth:`matrix` is the identity and :meth:`offsets` is
    where the effect lives.  Approximating it as a scroll would turn a churning
    liquid into a sliding one, which is exactly the difference the directive
    exists to express (``SPEC-Q3SHADER §2.4.2.1``).
    """

    wave: Wave = field(default_factory=Wave)

    @property
    def moving(self) -> bool:
        return self.wave.moving

    def offsets(self, points: Any, time: float) -> np.ndarray:
        """The per-vertex coordinate offset for ``points`` at ``time``.

        ``points`` is an ``(N, 3)`` array of positions; the result is
        ``(N, 2)``.  The spatial term is a **choice** -- see
        :data:`TURB_SPATIAL_SCALE`.
        """
        positions = np.asarray(points, dtype='d').reshape(-1, 3)
        spatial = positions.sum(axis=1) * TURB_SPATIAL_SCALE
        value = np.asarray(self.wave.at(time, spatial), dtype='d')
        # The two axes are offset by a quarter cycle so the churn is circular
        # rather than diagonal, which is what stops it reading as a scroll.
        across = np.asarray(self.wave.at(time, spatial + 0.25), dtype='d')
        return np.stack([value, across], axis=1)


#: How many arguments each ``tcMod`` form takes, and what it builds.
_TCMOD_ARITY = {'scroll': 2, 'scale': 2, 'rotate': 1, 'transform': 6,
                'stretch': 5, 'turb': 4}


def parse_tcmod(tokens: Sequence[str]) -> Optional[TCMod]:
    """One ``tcMod`` directive's arguments as a modifier, or None.

    None for a form this viewer does not implement and for one whose arguments
    do not parse: ``SPEC-Q3SHADER §2.1.1`` skips what it does not recognise, and
    a half-read directive is worse than none.
    """
    if not tokens:
        return None
    form = tokens[0].lower()
    arguments = tokens[1:]
    wanted = _TCMOD_ARITY.get(form)
    if wanted is None or len(arguments) < wanted:
        return None
    if form == 'stretch':
        wave = Wave.parse(arguments[:5])
        return TCModStretch(wave) if wave is not None else None
    if form == 'turb':
        # `turb`'s four numbers are a wave's four with the shape fixed at sine.
        wave = Wave.parse([DEFAULT_WAVE] + list(arguments[:4]))
        return TCModTurb(wave) if wave is not None else None
    try:
        numbers = [float(token) for token in arguments[:wanted]]
    except ValueError:
        return None
    if form == 'scroll':
        return TCModScroll(*numbers)
    if form == 'scale':
        return TCModScale(*numbers)
    if form == 'rotate':
        return TCModRotate(*numbers)
    return TCModTransform(*numbers)


def coordinate_transform(modifiers: Sequence[TCMod], time: float) -> np.ndarray:
    """Every modifier composed into one 3x3, applied in the order written.

    Order matters and is the directive's own: each modifier acts on the output
    of the last (``SPEC-Q3SHADER §2.4.2``).
    """
    matrix = np.identity(3)
    for modifier in modifiers:
        matrix = matrix @ modifier.matrix(time)
    return matrix


def apply_transform(matrix: Any, coordinate: Sequence[float]) -> np.ndarray:
    """A texture coordinate through a 3x3 transform.

    Row-vector convention, matching the rest of this workspace: a coordinate is
    a row and multiplies on the left.
    """
    homogeneous = np.array([coordinate[0], coordinate[1], 1.0])
    return np.asarray(homogeneous @ np.asarray(matrix))[:2]


# ----------------------------------------------------------------------
# Vertex deformation (SPEC-Q3SHADER §2.4.3)
# ----------------------------------------------------------------------


class Deform:
    """Geometry that moves at run time."""

    def displace(self, points: Any, normals: Any, time: float) -> np.ndarray:
        """``points`` moved for the frame at ``time``.  Returns a new array."""
        return np.array(points, dtype='d')

    def perturb(self, points: Any, normals: Any, time: float) -> np.ndarray:
        """``normals`` bent for the frame at ``time``.  Returns a new array."""
        return np.array(normals, dtype='d')


@dataclass(frozen=True)
class DeformWave(Deform):
    """Displace each vertex along its own normal by a wave.

    ``division`` spreads the phase across the surface, so a large face ripples
    rather than heaving as one rigid sheet.  A division of zero moves the whole
    surface together, which is what makes a small panel throb.
    """

    division: float = 0.0
    wave: Wave = field(default_factory=Wave)

    def displace(self, points: Any, normals: Any, time: float) -> np.ndarray:
        positions = np.asarray(points, dtype='d').reshape(-1, 3)
        if self.division:
            spread = positions.sum(axis=1) / self.division
        else:
            spread = np.zeros(len(positions))
        amount = np.asarray(self.wave.at(time, spread), dtype='d')
        return positions + np.asarray(normals, dtype='d').reshape(-1, 3) * amount[:, None]


@dataclass(frozen=True)
class DeformMove(Deform):
    """Displace the whole surface along one axis by a wave."""

    axis: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    wave: Wave = field(default_factory=Wave)

    def displace(self, points: Any, normals: Any, time: float) -> np.ndarray:
        positions = np.asarray(points, dtype='d').reshape(-1, 3)
        amount = float(self.wave.at(time))
        return positions + np.asarray(self.axis, dtype='d') * amount


@dataclass(frozen=True)
class DeformNormal(Deform):
    """Bend the normals rather than the positions.

    A flat surface then *lights* as though it were rippling, at no cost in
    geometry -- which is the whole point of the directive and why it is used for
    slow-moving liquids that need to catch the light without visibly heaving.
    """

    amplitude: float = 0.0
    frequency: float = 0.0

    def perturb(self, points: Any, normals: Any, time: float) -> np.ndarray:
        positions = np.asarray(points, dtype='d').reshape(-1, 3)
        base = np.asarray(normals, dtype='d').reshape(-1, 3)
        phase = positions.sum(axis=1) * TURB_SPATIAL_SCALE + time * self.frequency
        offset = np.stack([np.sin(2.0 * np.pi * phase),
                           np.cos(2.0 * np.pi * phase),
                           np.zeros(len(positions))], axis=1)
        bent = base + offset * self.amplitude
        lengths = np.linalg.norm(bent, axis=1, keepdims=True)
        return np.where(lengths > 0.0, bent / np.maximum(lengths, 1e-12), base)


def parse_deform(tokens: Sequence[str]) -> Optional[Deform]:
    """One ``deformVertexes`` directive as a deformation, or None.

    None for the forms that are a rendering technique rather than a property of
    the surface -- ``autosprite``, ``projectionShadow``, ``text0``..``text7`` --
    and for anything that does not parse.
    """
    if not tokens:
        return None
    form = tokens[0].lower()
    arguments = tokens[1:]
    if form == 'wave' and len(arguments) >= 6:
        try:
            division = float(arguments[0])
        except ValueError:
            return None
        wave = Wave.parse(arguments[1:6])
        return DeformWave(division, wave) if wave is not None else None
    if form == 'move' and len(arguments) >= 8:
        try:
            axis = tuple(float(token) for token in arguments[:3])
        except ValueError:
            return None
        wave = Wave.parse(arguments[3:8])
        return DeformMove(axis, wave) if wave is not None else None  # type: ignore[arg-type]
    if form == 'normal' and len(arguments) >= 2:
        try:
            return DeformNormal(float(arguments[0]), float(arguments[1]))
        except ValueError:
            return None
    return None


# ----------------------------------------------------------------------
# Colour generation (SPEC-Q3SHADER §2.4.4)
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class ColorGen:
    """A stage's colour over time: a wave, a constant, or plain white.

    Built through the three classmethods rather than by naming a mode, so an
    unrepresentable state -- a wave generator with no wave -- cannot be made.
    """

    wave_source: Optional[Wave] = None
    fixed: Optional[Tuple[float, float, float]] = None

    @classmethod
    def wave(cls, wave: Wave) -> 'ColorGen':
        """A grey level from ``wave``, on all three channels."""
        return cls(wave_source=wave)

    @classmethod
    def constant(cls, color: Sequence[float]) -> 'ColorGen':
        """A fixed colour."""
        return cls(fixed=(float(color[0]), float(color[1]), float(color[2])))

    @classmethod
    def identity(cls) -> 'ColorGen':
        """Full white, which is the default."""
        return cls()

    @property
    def animated(self) -> bool:
        """Whether the colour changes with time."""
        return self.wave_source is not None and self.wave_source.moving

    def at(self, time: float) -> Tuple[float, float, float]:
        """The colour at ``time``, each channel clamped into ``[0, 1]``."""
        if self.fixed is not None:
            return self.fixed
        if self.wave_source is None:
            return (1.0, 1.0, 1.0)
        level = min(1.0, max(0.0, float(self.wave_source.at(time))))
        return (level, level, level)


def _bracketed(tokens: Sequence[str]) -> List[str]:
    """``tokens`` with any parentheses dropped, as `rgbGen const ( r g b )`."""
    return [token for token in tokens if token not in ('(', ')')]


def parse_rgbgen(tokens: Sequence[str]) -> Optional[ColorGen]:
    """One ``rgbGen`` directive as a generator, or None.

    None for the forms whose source is outside the material -- ``vertex``,
    ``entity``, ``lightingDiffuse`` and the rest -- since a viewer drawing one
    PBR material has no such source to read.
    """
    if not tokens:
        return None
    form = tokens[0].lower()
    if form == 'wave':
        wave = Wave.parse(tokens[1:6])
        return ColorGen.wave(wave) if wave is not None else None
    if form == 'const':
        numbers = _bracketed(tokens[1:])
        if len(numbers) < 3:
            return None
        try:
            return ColorGen.constant([float(token) for token in numbers[:3]])
        except ValueError:
            return None
    if form == 'identity':
        return ColorGen.identity()
    return None


@dataclass(frozen=True)
class AlphaGen:
    """A stage's opacity over time."""

    wave_source: Optional[Wave] = None
    fixed: Optional[float] = None

    @property
    def animated(self) -> bool:
        return self.wave_source is not None and self.wave_source.moving

    def at(self, time: float) -> float:
        """The opacity at ``time``, clamped into ``[0, 1]``."""
        if self.fixed is not None:
            return self.fixed
        if self.wave_source is None:
            return 1.0
        return min(1.0, max(0.0, float(self.wave_source.at(time))))


def parse_alphagen(tokens: Sequence[str]) -> Optional[AlphaGen]:
    """One ``alphaGen`` directive as a generator, or None."""
    if not tokens:
        return None
    form = tokens[0].lower()
    if form == 'wave':
        wave = Wave.parse(tokens[1:6])
        return AlphaGen(wave_source=wave) if wave is not None else None
    if form == 'const':
        numbers = _bracketed(tokens[1:])
        try:
            return AlphaGen(fixed=float(numbers[0]))
        except (ValueError, IndexError):
            return None
    return None


# ----------------------------------------------------------------------
# Frame animation (SPEC-Q3SHADER §2.4.5)
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class AnimMap:
    """A stage's texture cycling through frames at a fixed rate."""

    frequency: float = 0.0
    frames: Tuple[str, ...] = ()

    @property
    def animated(self) -> bool:
        return self.frequency > 0.0 and len(self.frames) > 1

    def frame(self, time: float) -> Optional[str]:
        """The frame showing at ``time``, or None where there are none."""
        if not self.frames:
            return None
        if self.frequency <= 0.0:
            return self.frames[0]
        return self.frames[int(time * self.frequency) % len(self.frames)]


def parse_animmap(tokens: Sequence[str]) -> Optional[AnimMap]:
    """One ``animMap`` directive as a cycle, or None."""
    if len(tokens) < 2:
        return None
    try:
        frequency = float(tokens[0])
    except ValueError:
        return None
    return AnimMap(frequency, tuple(tokens[1:]))


# ----------------------------------------------------------------------
# Everything one material animates
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class SurfaceAnimation:
    """Every animation directive one material carries, gathered.

    Frozen and hashable, because a surface style is a batching key: two surfaces
    that animate identically must group into one draw, and two that do not must
    not.
    """

    tcmods: Tuple[TCMod, ...] = ()
    deforms: Tuple[Deform, ...] = ()
    rgbgen: Optional[ColorGen] = None
    alphagen: Optional[AlphaGen] = None
    animmap: Optional[AnimMap] = None

    @property
    def animated(self) -> bool:
        """Whether anything here changes with time.

        A constant `scale` or `transform` is a property of the surface rather
        than an animation, so a material carrying only those is not animated and
        costs nothing per frame.
        """
        return bool(
            any(modifier.moving for modifier in self.tcmods)
            or self.deforms
            or (self.rgbgen is not None and self.rgbgen.animated)
            or (self.alphagen is not None and self.alphagen.animated)
            or (self.animmap is not None and self.animmap.animated))

    @property
    def transforming(self) -> bool:
        """Whether the texture matrix differs from the identity at all."""
        return bool(self.tcmods)

    @property
    def deforming(self) -> bool:
        """Whether this costs *vertices* each frame rather than a uniform."""
        return bool(self.deforms)

    @property
    def turbulent(self) -> bool:
        """Whether any modifier offsets coordinates per *vertex*.

        Asked rather than discovered by evaluating: turbulence is the one
        coordinate modifier that cannot be folded into the material's texture
        matrix, so whether a surface has any decides whether it needs a vertex
        pass at all -- and that is decided once, when the scene is built.
        """
        return any(isinstance(modifier, TCModTurb) for modifier in self.tcmods)

    def transform_at(self, time: float) -> np.ndarray:
        """The composed texture-coordinate transform at ``time``."""
        return coordinate_transform(self.tcmods, time)

    def turbulence_at(self, points: Any, time: float) -> Optional[np.ndarray]:
        """Per-vertex coordinate offsets at ``time``, or None if there are none.

        Every turbulence modifier the material carries is summed, since they
        compose the same way the affine ones do.
        """
        modifiers = [m for m in self.tcmods if isinstance(m, TCModTurb)]
        if not modifiers:
            return None
        total = modifiers[0].offsets(points, time)
        for modifier in modifiers[1:]:
            total = total + modifier.offsets(points, time)
        return total

    def displace(self, points: Any, normals: Any, time: float) -> np.ndarray:
        """``points`` moved by every deformation, in the order written."""
        moved = np.asarray(points, dtype='d').reshape(-1, 3)
        for deform in self.deforms:
            moved = deform.displace(moved, normals, time)
        return moved

    def perturb(self, points: Any, normals: Any, time: float) -> np.ndarray:
        """``normals`` bent by every deformation, in the order written."""
        bent = np.asarray(normals, dtype='d').reshape(-1, 3)
        for deform in self.deforms:
            bent = deform.perturb(points, bent, time)
        return bent

    def color_at(self, time: float) -> Tuple[float, float, float]:
        """The material's generated colour at ``time``; white if none is."""
        if self.rgbgen is None:
            return (1.0, 1.0, 1.0)
        return self.rgbgen.at(time)

    def alpha_at(self, time: float) -> float:
        """The material's generated opacity at ``time``; 1.0 if none is."""
        if self.alphagen is None:
            return 1.0
        return self.alphagen.at(time)

    def frame_at(self, time: float) -> Optional[str]:
        """The texture showing at ``time``, or None where none cycles."""
        if self.animmap is None:
            return None
        return self.animmap.frame(time)


#: How fast a version 38 `SURF_FLOWING` surface slides, in texture widths per
#: second.  That family has no script and no number: the flag says *that* the
#: surface flows and nothing more (``SPEC-BSP38 §8.1``), so the rate is **a
#: choice**, picked to read as a conveyor rather than as a blur.
FLOWING_RATE = -0.25


def flowing_animation() -> SurfaceAnimation:
    """The animation a version 38 flowing surface gets.

    One scroll along S.  Expressing it as the same value object the scripts
    produce is what keeps everything downstream -- batching, materials, the
    renderer -- free of any knowledge of which family a map came from.
    """
    return SurfaceAnimation(tcmods=(TCModScroll(FLOWING_RATE, 0.0),))
