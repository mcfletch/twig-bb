"""A map's ``target_speaker`` entities as sound in the scene.

29 of the 50 shipped maps place at least one and one places sixty, so this is
what makes a level sound like itself: wind over a courtyard, a furnace, water,
the hum of a light.  Each becomes a ``Transform`` at the entity's origin
holding one ``AudioEmitter``, and that is the whole of the wiring — the engine
needs nothing else, because the render pass already finds emitters and already
knows where the camera is.

The entity's keys are specified in ``SPEC-Q3ENTITIES §1``, which is where every
constant below comes from and where the two keys we deliberately *do not* act
on are recorded as unknown rather than guessed at.

**Three things are left out on purpose**, and each is a case where doing
something would be worse than doing nothing:

* a speaker with a ``targetname`` is fired by something else (``§1.6``), and
  playing it as ambience turns a sound that should answer an event into a
  constant;
* ``angle`` and ``light`` have no established meaning here (``§1.7``), so no
  cone is made from an angle however plausible that reading is;
* ``spawnflags`` bits 4 and 8 occur in real content and mean nothing we know
  (``§1.4.3``), so they are ignored — but only the *bits* are ignored, never
  the entity: 22 real speakers carry only those and must still be heard.

A ``noise`` that resolves to nothing is a silence and a warning, never a failed
load; see :mod:`twig_bb.sounds`.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

import numpy as np

from OpenGLContext.scenegraph.audio import AudioEmitter, AudioSource
from OpenGLContext.scenegraph.group import Group
from OpenGLContext.scenegraph.transform import Transform

from .entities import Entity
from .worldgeometry import to_scene_points

log = logging.getLogger(__name__)

#: ``SPEC-Q3ENTITIES §1``: the classname a level editor writes for a placed
#: sound.
SPEAKER_CLASSNAME = 'target_speaker'

#: ``SPEC-Q3ENTITIES §1.4.2``: the one ``spawnflags`` bit whose meaning is
#: established.  Bits 4 and 8 also occur and are deliberately unread (``§1.4.3``).
LOOP_FLAG = 1

#: Metres within which a speaker is at full level.  Map ambience is a property
#: of a *place* — a room, a pool, a machine — so the plateau is about the size
#: of one, and beyond it the sound fades.
REF_DISTANCE = 3.0

#: Metres at which a speaker contributes nothing.  A curve that merely tends to
#: zero is not good enough here: `ctf_inyard` places 60 speakers, and sixty
#: sounds that never quite stop are a wash rather than a level.
MAX_DISTANCE = 40.0

#: Level relative to whatever the game itself is making.  Ambience is the floor
#: of a mix and not a part of it; a wind loop that competes with a weapon is a
#: wind loop turned up too far.
AMBIENT_GAIN = 0.6

#: ``SPEC-Q3ENTITIES §1.5.3`` asks an implementation to say which reading of
#: `random` it chose.  Ours is a **symmetric** spread: the wait may fall either
#: side of `wait` by up to `random` seconds, and is never negative.  Chosen
#: because it leaves the author's `wait` as the average rather than shortening
#: every gap, which is what a mapper writing `wait 30` appears to mean.
RANDOM_IS_SYMMETRIC = True


def from_map(loaded: Any, library: Optional[Any] = None) -> Group:
    """Every speaker of a loaded map, as one group to put in the scene."""
    if library is None:
        from .sounds import SoundLibrary
        library = SoundLibrary(loaded.roots)
    return from_entities(loaded.entities, library)


def from_entities(entities: Iterable[Entity], library: Any) -> Group:
    """The speakers among ``entities``, resolved against ``library``."""
    children = [built for built in
                (_speaker(entity, library) for entity in entities)
                if built is not None]
    return Group(children=children)


def count(group: Any) -> int:
    """How many speakers a built group holds, for the debug overlay."""
    return len(group.children)


def _speaker(entity: Entity, library: Any) -> Optional[Transform]:
    """One entity as a placed emitter, or None if it makes no sound.

    Returning None rather than an empty emitter keeps the group's length the
    count of things that will actually be heard, which is the number worth
    putting on a debug overlay.
    """
    if entity.classname != SPEAKER_CLASSNAME:
        return None
    noise = entity.get('noise', '')
    if not noise:
        log.warning('a %s has no noise key; it will be silent',
                    SPEAKER_CLASSNAME)
        return None
    if 'targetname' in entity:
        # SPEC-Q3ENTITIES §1.6.2: fired by something else, and there is nothing
        # here to fire it.
        log.debug('%s %s is triggered rather than ambient; leaving it out',
                  SPEAKER_CLASSNAME, entity['targetname'])
        return None
    path = library.resolve(noise)
    if path is None:
        return None
    return Transform(
        translation=_position(entity),
        children=[AudioEmitter(
            gain=AMBIENT_GAIN,
            distanceModel='linear',
            refDistance=REF_DISTANCE,
            maxDistance=MAX_DISTANCE,
            sources=[_source(entity, path)],
        )],
    )


def _source(entity: Entity, path: str) -> AudioSource:
    """The clip and how it recurs (``SPEC-Q3ENTITIES §1.4``, ``§1.5``)."""
    loop = bool(int(entity.number('spawnflags', 0.0)) & LOOP_FLAG)
    # A loop has no gaps to time, so `wait` is read only for a speaker that
    # does not loop -- which is exactly the population that carries one.
    interval = 0.0 if loop else entity.number('wait', 0.0)
    variance = entity.number('random', 0.0) if interval else 0.0
    return AudioSource(url=[path], loop=loop, repeatInterval=interval,
                       repeatVariance=variance)


def _position(entity: Entity) -> Any:
    """The entity's origin in scene space (``SPEC-Q3ENTITIES §1.3.2``)."""
    point = to_scene_points(np.array([entity.vector('origin')]))[0]
    return tuple(float(value) for value in point)
