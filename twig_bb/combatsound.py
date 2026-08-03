"""What a fight sounds like: a declared table, and where each sound is heard.

**Three sounds carry three different questions**, and that is why there are
three rather than one: the weapon firing answers *did my input register*, an
impact on the level answers *where did that go*, and an impact on a person
answers **did I hit them**.  The third is the one a player acts on, so it is
louder, it is brighter, and it outranks the others when a firefight runs the
voice pool dry.

**The player's own weapon is not positional; everybody else's is.**  A gun held
at the camera has no direction to come from, and panning it would put the
player's own weapon somewhere beside them.  Another player's gunshot, placed
where they fired it from, is one of the very few sounds in this genre that a
player genuinely locates an opponent by — so it is placed, and it is placed at
the muzzle rather than at the impact.

**The sounds are ours, made out of arithmetic.**  Every voice in the table is
synthesised through :mod:`omi_audio.synth` from numbers stated here,
so the game ships with a full complement of sound and no audio files, no
licences to carry and nothing to check under
[CLEAN-ROOM](../../CLEAN-ROOM.md).  A voice may instead name a ``file`` under
:mod:`twig_bb.assets`, which is how commissioned or CC0 content replaces a
synthesised stand-in: an edit to the table rather than a change to any code.

**A sound that is not there is a silent shot, never a crash.**  A game must not
die because content is absent, which is the rule the texture resolver already
follows.

The engine is :mod:`omi_audio` and does the hard part: the voice pool, the
stealing rule, the distance curve and the pan.  What is here is only which
sound, how loud, and from where — which is the half that is a design.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, Optional, Sequence

from vrml import field, node

from omi_audio import model as audiomodel
from omi_audio import synth

from . import arena as arenamod
from . import game as gamemod

log = logging.getLogger(__name__)

__all__ = [
    'CombatSound', 'SoundBank', 'SoundTable', 'Voice', 'default_table',
    'DEATH', 'EXPLOSION', 'FIRE', 'FLESH', 'WORLD', 'ASSETS',
]

#: Where sound content that ships with this package would live.  Shared with
#: :mod:`twig_bb.weapons`, because a weapon's model and a weapon's sound are
#: the same kind of thing: art named by the table.
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')

#: The keys the game asks for by name.  A weapon may name its own fire sound
#: instead of :data:`FIRE`, which is what makes a shotgun sound unlike a rifle.
FIRE = 'fire'
WORLD = 'impact-world'
FLESH = 'impact-flesh'
DEATH = 'death'
EXPLOSION = 'explosion'

#: How far a combat sound is at full level, and how far it carries at all, in
#: metres.  Much further than map ambience (:mod:`twig_bb.speakers`): a
#: gunshot across a level is information, and a gunshot that faded out at the
#: end of a corridor would take that information away.
REF_DISTANCE = 6.0
MAX_DISTANCE = 120.0


class Voice(node.Node):
    """One sound the game can make, as data.

    ``file`` names content under :data:`ASSETS` and wins when it is set.  With
    none, the sound is synthesised from the numbers below, which is what ships:
    ``duration`` seconds of noise under an exponential ``decay`` (larger is
    drier and shorter), at ``amplitude``.  ``seed`` fixes the noise so a
    reference recording is reproducible.

    ``gain`` is the level it is played at, relative to everything else the game
    makes, and ``priority`` is which sounds survive when there are more of them
    than there are voices — 1.0 is the most important.
    """

    PROTO = 'Voice'
    key = field.newField('key', 'SFString', 1, '')
    file = field.newField('file', 'SFString', 1, '')

    #: Seconds long, and how sharply it decays.
    duration = field.newField('duration', 'SFFloat', 1, 0.18)
    decay = field.newField('decay', 'SFFloat', 1, 20.0)
    amplitude = field.newField('amplitude', 'SFFloat', 1, 0.9)
    seed = field.newField('seed', 'SFInt32', 1, 0)

    #: Level and importance, both 0 to 1.
    gain = field.newField('gain', 'SFFloat', 1, 0.6)
    priority = field.newField('priority', 'SFFloat', 1, 0.3)


class SoundTable(node.Node):
    """Every sound a fight can make."""

    PROTO = 'SoundTable'
    voices = field.newField('voices', 'MFNode', 1, list)

    def by_key(self, key: str) -> Optional[Voice]:
        """The voice with that key, or None -- an unknown key is not fatal."""
        for voice in self.voices:
            if str(voice.key) == key:
                return voice
        return None


def default_table() -> SoundTable:
    """The sounds this game ships with.

    Chosen so the three that matter are told apart with the eyes shut: the
    weapon is the loudest and the shortest, an impact on stone is duller and
    quieter than either, and a hit on a person is brighter and rings a little
    longer — which is what makes "did I hit them" answerable at a glance across
    a room.

    A function rather than a constant, because a table is authored data with
    every field writable: a game (or a test) retuning one sound should not
    retune it for every other table in the process.
    """
    return SoundTable(voices=[
        Voice(key=FIRE, duration=0.16, decay=26.0, amplitude=0.95,
              gain=0.55, priority=0.5, seed=1),
        # The stand-in loadout's three, differing the way the weapons do: a
        # pistol cracks, a shotgun booms, a rifle is dry and fast.  Switching
        # weapon has to change something a player can hear, or it is not a
        # switch.
        Voice(key='fire-pistol', duration=0.15, decay=30.0, amplitude=0.9,
              gain=0.5, priority=0.5, seed=11),
        Voice(key='fire-shotgun', duration=0.34, decay=11.0, amplitude=1.0,
              gain=0.7, priority=0.6, seed=12),
        Voice(key='fire-rifle', duration=0.09, decay=48.0, amplitude=0.8,
              gain=0.45, priority=0.45, seed=13),
        # The launchers: a long whoosh rather than a report, so that hearing
        # one is a warning rather than a note that somebody shot at something.
        Voice(key='fire-rocket', duration=0.45, decay=6.0, amplitude=0.85,
              gain=0.65, priority=0.7, seed=14),
        Voice(key='fire-grenade', duration=0.2, decay=16.0, amplitude=0.6,
              gain=0.5, priority=0.5, seed=15),
        Voice(key=WORLD, duration=0.13, decay=34.0, amplitude=0.55,
              gain=0.35, priority=0.2, seed=2),
        # Louder and longer than either, because it is the one a player acts
        # on and the one that must survive voice stealing in a firefight.
        Voice(key=FLESH, duration=0.22, decay=18.0, amplitude=0.85,
              gain=0.7, priority=0.8, seed=3),
        Voice(key=DEATH, duration=0.55, decay=7.0, amplitude=0.8,
              gain=0.6, priority=0.9, seed=4),
        Voice(key=EXPLOSION, duration=0.9, decay=4.0, amplitude=1.0,
              gain=0.9, priority=0.95, seed=5),
    ])


class SoundBank:
    """The table's sounds, made or decoded once and played many times.

    Every answer is kept, **including the misses**: a sound that is not there
    must not be looked for again on the next shot, and a firefight asks for a
    dozen a second.
    """

    def __init__(self, table: Optional[SoundTable] = None,
                 assets: str = ASSETS) -> None:
        self.table = table if table is not None else default_table()
        self.assets = assets
        #: What each key resolved to, by key.  None is a remembered miss.
        self.resolved: Dict[str, Any] = {}

    def clip(self, engine: Any, key: str) -> Any:
        """The clip for a key, or None if there is nothing to play."""
        if key in self.resolved:
            return self.resolved[key]
        found = self._make(engine, self.table.by_key(key))
        self.resolved[key] = found
        return found

    def voice(self, key: str) -> Optional[Voice]:
        """The table entry for a key, for its gain and its priority."""
        return self.table.by_key(key)

    def _make(self, engine: Any, voice: Optional[Voice]) -> Any:
        """One voice as a clip: its file if it names one, else arithmetic."""
        if voice is None:
            return None
        named = str(voice.file)
        if named:
            path = os.path.join(self.assets, named)
            if not os.path.exists(path):
                log.warning('no sound file at %s; %s will be silent',
                            path, voice.key)
                return None
            return engine.clip(path)
        return synth.impact(duration=float(voice.duration),
                            amplitude=float(voice.amplitude),
                            decay=float(voice.decay),
                            seed=int(voice.seed))


class CombatSound:
    """One match's events, played through a context's audio engine.

    ``engine`` is a callable rather than an engine, so that a match with
    nothing to say never opens a device: OpenGLContext gives a context its
    engine on first ask, and asking is what starts an audio thread.
    """

    def __init__(self, match: Any, table: Optional[SoundTable] = None,
                 engine: Optional[Callable[[], Any]] = None,
                 weapons: Any = None) -> None:
        self.match = match
        self.bank = SoundBank(table)
        self.weapons = weapons
        self._engine = engine if engine is not None else (lambda: None)
        #: An emitter record per placement, rewritten in place: a firefight
        #: asks for a dozen sounds a second and allocating two records for
        #: each of them is a stutter nobody can point at.
        self._here = _emitter(audiomodel.GLOBAL)
        self._there = _emitter(audiomodel.POSITIONAL)

    def show(self, events: Sequence[Any], platform: Any = None) -> int:
        """Play what ``events`` sound like; returns how many voices started.

        ``platform`` is the view platform, and the camera is the ear: without
        it the sounds still play, because being unable to place a gunshot is
        better than not hearing one.
        """
        wanted = [what for what in (self._sound(event) for event in events)
                  if what is not None]
        if not wanted:
            return 0
        engine = self._engine()
        if engine is None:
            return 0
        if platform is not None:
            engine.listen(platform)
        return sum(self._play(engine, key, position) for key, position in wanted)

    # -- what an event sounds like ---------------------------------------
    def _sound(self, event: Any) -> Optional[tuple]:
        """``(key, position)`` for one event, or None if it makes no sound.

        A position of None is a sound with no place -- the player's own weapon
        -- and is what makes it non-positional further down.
        """
        if isinstance(event, arenamod.Fired):
            return (self._fireKey(event),
                    None if event.shooter == gamemod.PLAYER_ID else event.origin)
        if isinstance(event, arenamod.Impact):
            return (FLESH if event.on_somebody else WORLD, event.point)
        if isinstance(event, arenamod.Detonated):
            # Placed even when it is the player's own: a burst happens
            # *somewhere*, which is the whole of what a player has to know
            # about it, and a rocket that went off silently is a rocket nobody
            # takes cover from.
            return (EXPLOSION, event.point)
        if isinstance(event, arenamod.Death):
            return (DEATH, self._where(event.target))
        return None

    def _fireKey(self, event: arenamod.Fired) -> str:
        """Which sound a weapon makes: its own if the table names one.

        A weapon naming its own sound is what makes a shotgun sound unlike a
        rifle, and it is a field on the weapon table rather than a branch here
        for the same reason its model is.
        """
        weapon = (self.weapons.by_key(event.weapon)
                  if self.weapons is not None else None)
        named = str(getattr(weapon, 'fireSound', '') or '')
        return named if named and self.bank.voice(named) is not None else FIRE

    def _where(self, id: str) -> Optional[tuple]:
        """Where a combatant is, or None if they are no longer in the match."""
        one = self.match.combatant(id)
        if one is None:
            return None
        return tuple(float(value) for value in one.position)

    # -- playing it -------------------------------------------------------
    def _play(self, engine: Any, key: str,
              position: Optional[Sequence[float]]) -> int:
        """Start one sound; returns 1 if a voice took it and 0 otherwise."""
        clip = self.bank.clip(engine, key)
        voice = self.bank.voice(key)
        if clip is None or voice is None:
            return 0
        emitter = self._here if position is None else self._there
        started = engine.play(clip, emitter=emitter, position=position,
                              gain=float(voice.gain),
                              priority=float(voice.priority), loop=False)
        return 1 if started is not None else 0


def _emitter(kind: str) -> audiomodel.AudioEmitter:
    """One reusable emitter record, positional or not.

    The distance curve is a combat one rather than the ambience one in
    :mod:`twig_bb.speakers`: a shot across a level has to be audible,
    because hearing it is how a player knows where the fight is.
    """
    record = audiomodel.AudioEmitter(type=kind, gain=1.0)
    if kind == audiomodel.POSITIONAL:
        record.positional = audiomodel.PositionalProperties(
            distanceModel='linear', refDistance=REF_DISTANCE,
            maxDistance=MAX_DISTANCE)
    else:
        record.positional = None
    return record
