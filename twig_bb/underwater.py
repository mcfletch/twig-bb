"""Being *inside* a liquid: what the view and the mix do about it.

The liquid volumes have been read out of the BSP for as long as swimming has
worked, and being in one has meant only that the movement mode changed.  This
is the rest of it — the part that makes a pool feel like a place rather than a
region where the controls behave oddly:

* **the view fogs** to the liquid's own colour, through OpenGLContext's
  ``Fog`` node, which the render pass binds like any other;
* **the mix muffles**, through the whole-mix low-pass the audio engine already
  carries.

Being under water is *not* a coloured pane over the screen.  It is a medium
with depth in it: the weapon in your hands is clear, the wall across the room
is not, and a flat tint would treat them alike.  That is the whole reason this
is a ``Fog`` and not an overlay, and why it uses the exponential curve —
clear close up, then closing in.  See
:mod:`OpenGLContext.scenegraph.fog`.

**The colour is a warning, not decoration.** It is nearly all a player gets
before lava starts hurting them, so the three liquids are three plainly
different colours and lava is the one you cannot see through.

The numbers below are this game's, not format facts: nothing in any
specification says how far you can see through slime.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

from OpenGLContext.scenegraph.fog import Fog

from . import liquids

__all__ = ['LIQUIDS', 'apply', 'liquid_fog', 'muffle_for', 'update']


class LiquidLook:
    """How one liquid looks and sounds from inside it."""

    __slots__ = ('color', 'visibility', 'muffle')

    def __init__(self, color: Tuple[float, float, float], visibility: float,
                 muffle: float) -> None:
        #: What the view fades to, linear RGB.
        self.color = color
        #: Metres at which it fades completely.
        self.visibility = visibility
        #: How much of the mix's high end goes, 0 clear to 1 fully damped.
        self.muffle = muffle


#: What each liquid does to the view and the mix.
#:
#: **Water is dark and close, not a pale haze.**  A long range and a light
#: colour give fog — air with something in it — and the difference between fog
#: and water is that water *absorbs*: it takes the light out of what you are
#: looking at rather than adding a veil in front of it.  So the colours here
#: are much darker than the surface of water looks from outside, and the range
#: is a few metres rather than a room's width.  Slime is thicker and sicklier
#: still; lava is opaque and closer than arm's length, because you cannot see
#: through molten rock and a player who has fallen into it should be in no
#: doubt which of the three they are in.
#:
#: **These are linear values and are much smaller than they look.**  The fog is
#: blended in linear HDR *before* tone mapping, so a colour that reads as a
#: pleasant mid-blue when written down arrives on screen far brighter than a
#: dark map — and a fog that makes distant walls *brighter* is a fog lamp, not
#: a body of water.  The rule of thumb: the fog colour has to sit at or below
#: what the level itself averages, or depth reads as glow.
#:
#: They are this game's numbers.  No specification says how far you can see
#: through slime, and they are meant to be looked at and adjusted.
LIQUIDS: Dict[str, LiquidLook] = {
    liquids.WATER: LiquidLook(color=(0.004, 0.022, 0.030), visibility=9.0,
                              muffle=0.75),
    liquids.SLIME: LiquidLook(color=(0.012, 0.030, 0.006), visibility=4.5,
                              muffle=0.85),
    liquids.LAVA: LiquidLook(color=(0.55, 0.12, 0.03), visibility=2.0,
                             muffle=0.90),
}

#: What an unrecognised liquid looks like.  A map may name one this table has
#: no entry for, and reading that as dry air would be the one wrong answer:
#: whatever it is, the camera is inside something.
UNKNOWN = LIQUIDS[liquids.WATER]


def liquid_fog() -> Fog:
    """A fog node for a viewer to hold, starting switched off.

    One node, reused: it is bound into the scene once and its fields are
    written as the camera goes in and out, so entering water is a field change
    rather than a scenegraph edit.  ``visibilityRange`` 0 is the specification's
    own way of saying "no fog", which is what dry land wants.
    """
    return Fog(visibilityRange=0.0, fogType='EXPONENTIAL')


def look_for(kind: str) -> Optional[LiquidLook]:
    """How ``kind`` looks, or None for dry air."""
    if not kind:
        return None
    return LIQUIDS.get(kind, UNKNOWN)


def apply(fog: Fog, kind: str) -> None:
    """Set a fog node to what being inside ``kind`` looks like.

    An empty ``kind`` is dry air and switches the fog off; nothing else does,
    so a liquid this game has no entry for still fogs.
    """
    look = look_for(kind)
    if look is None:
        fog.visibilityRange = 0.0
        return
    fog.color = look.color
    fog.visibilityRange = look.visibility


def muffle_for(kind: str) -> float:
    """How much of the mix's high end ``kind`` takes, 0 for dry air.

    Never 1.0: total silence reads as the sound having broken rather than as
    being under water, and a player still needs to hear what is shooting at
    them.
    """
    look = look_for(kind)
    return look.muffle if look is not None else 0.0


def update(context: Any, volumes: Any, point: Sequence[float]) -> str:
    """Put the view and the mix into whatever the camera is standing in.

    Called once a frame with the camera's position; returns the liquid it found
    so a caller can report it.  Every part is optional — a viewer between maps
    has no volumes and a machine with no sound has no engine — and none of them
    is a reason for a frame to fail.
    """
    from OpenGLContext.audio import scene as audioscene

    kind = volumes.kind_at(point) if volumes is not None else ''
    fog = getattr(context, 'fog', None)
    if fog is not None:
        apply(fog, kind)
    # The engine the context already has, and never a new one: opening a device
    # in order to muffle a silence would turn walking into a pool on a machine
    # with no sound into the one thing that starts the audio thread.
    engine = audioscene.existing_engine(context)
    if engine is not None:
        engine.muffle = muffle_for(kind)
    return kind
