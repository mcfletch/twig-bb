"""Being *inside* a liquid: what the view and the mix do about it.

All of it is the engine's now --
:mod:`OpenGLContext.scenegraph.water.medium` holds what each substance does to
a body in it, and :mod:`OpenGLContext.scenegraph.water.submersion` spends that
on the fog node the render pass already binds and on the whole-mix low-pass the
audio engine already carries. What is left here is the map's own vocabulary:
this game names its liquids after a Quake III shader's ``surfaceparm``, and
this is where those names meet the engine's media.

The numbers moved with the code, and the reasoning with them: water is dark and
close rather than a pale haze, because water *absorbs* where fog veils; lava is
opaque and closer than arm's length, because a player who has fallen into it
should be in no doubt which of the three they are in.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from OpenGLContext.scenegraph.fog import Fog
from OpenGLContext.scenegraph.water import medium as water_medium
from OpenGLContext.scenegraph.water import submersion

from . import liquids

__all__ = ['LIQUIDS', 'apply', 'liquid_fog', 'muffle_for', 'update']

#: What each liquid does to the view and the mix. The engine's table, under
#: this game's names for the same three substances -- which are the same names,
#: because the engine took its spelling from the shader parameter this game
#: reads them out of.
LIQUIDS: Dict[str, water_medium.Medium] = {
    liquids.WATER: water_medium.MEDIA[water_medium.WATER],
    liquids.SLIME: water_medium.MEDIA[water_medium.SLIME],
    liquids.LAVA: water_medium.MEDIA[water_medium.LAVA],
}

#: What an unrecognised liquid looks like. A map may name one this table has no
#: entry for, and reading that as dry air would be the one wrong answer:
#: whatever it is, the camera is inside something.
UNKNOWN = water_medium.UNKNOWN


def liquid_fog() -> Fog:
    """A fog node for a viewer to hold, starting switched off."""
    return submersion.medium_fog()


def look_for(kind: str) -> Optional[water_medium.Medium]:
    """How ``kind`` looks, or None for dry air."""
    return water_medium.medium_for(kind)


def apply(fog: Fog, kind: str) -> None:
    """Set a fog node to what being inside ``kind`` looks like."""
    submersion.apply(fog, kind)


def muffle_for(kind: str) -> float:
    """How much of the mix's high end ``kind`` takes, 0 for dry air."""
    return submersion.muffle_for(kind)


def update(context: Any, volumes: Any, point: Sequence[float]) -> str:
    """Put the view and the mix into whatever the camera is standing in.

    Called once a frame with the camera's position; returns the liquid it found
    so a caller can report it. The volumes are this game's --
    :class:`twig_bb.liquids.LiquidVolumes`, read out of the BSP -- and are asked
    the same question the engine asks its own.
    """
    return submersion.submerge(context, volumes, point)
