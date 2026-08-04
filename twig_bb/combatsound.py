"""What a fight sounds like: a declared table, and where each sound is heard.

**Three sounds carry three different questions**, and that is why there are
three rather than one: the weapon firing answers *did my input register*, an
impact on the level answers *where did that go*, and an impact on a person
answers **did I hit them**.  The third is the one a player acts on, so it is
louder, it is brighter, and it outranks the others when a firefight runs the
voice pool dry.

**A weapon owns both ends of its shot.**  ``fireSound`` is the report and
``impactSound``/``fleshSound`` are the round arriving, all three named by
:mod:`twig_bb.weapons` and all three optional — a weapon that names none is
heard as the generic set, which is what makes a new one audible before anybody
has designed a sound for it.  Both ends, because half of what tells one weapon
from another is what it sounds like when it *lands*: a rifle round arrives with
a chunk and a pistol round with a ping, and a table with one impact in it makes
every weapon land the same way however differently they fire.

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
    'DEATH', 'EXPLOSION', 'FIRE', 'FLESH', 'IMPACT', 'PICKUP', 'RUMBLE',
    'WORLD', 'ASSETS',
]

#: The two ways a synthesised voice is made, named by :attr:`Voice.shape`.
#: An impact is noise under a decay, which is bright at any length: a crack, a
#: snap, a hiss.  A rumble is the bottom of the range -- noise with the top
#: taken off over a tone that falls as it goes -- which is what a motor and a
#: detonation are made of, and what noise alone can never be.
IMPACT = 'impact'
RUMBLE = 'rumble'

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
#: Walking into something a map left lying about.  The one sound here that is
#: not a fight, and the one piece of good news the game has.
PICKUP = 'pickup'

#: How far a combat sound is at full level, and how far it carries at all, in
#: metres.  Much further than map ambience (:mod:`twig_bb.speakers`): a
#: gunshot across a level is information, and a gunshot that faded out at the
#: end of a corridor would take that information away.
REF_DISTANCE = 6.0
MAX_DISTANCE = 120.0

#: How many returns a voice that declares an echo gets.  Three, because the
#: third is already two-thirds of the way to silence at any level worth
#: hearing, and because the tail wants to be over well before the weapon can
#: be fired again — an echo still arriving when the next shot goes off is a
#: mess rather than a place.  A constant rather than a field: it is the *level*
#: and the *delay* that say what kind of space this is, and a fourth repeat
#: says nothing a third did not.
ECHO_TAPS = 3


class Voice(node.Node):
    """One sound the game can make, as data.

    ``file`` names content under :data:`ASSETS` and wins when it is set.  With
    none, the sound is synthesised from the numbers below, which is what ships:
    ``duration`` seconds under an exponential ``decay`` (larger is drier and
    shorter), at ``amplitude``.  ``seed`` fixes the noise so a reference
    recording is reproducible.

    ``shape`` is which of the two generators makes it, :data:`IMPACT` or
    :data:`RUMBLE`, and the four fields below it are the rumble's — a shot and
    a detonation want the same envelope and a different half of the spectrum.

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

    #: Which generator, and the numbers only a :data:`RUMBLE` reads: where its
    #: noise starts to roll away in **hertz**, what its body tone falls from
    #: and to in **hertz**, how much of it is that tone rather than noise (0 to
    #: 1), and how hard the result is saturated — which is the difference
    #: between a round boom and a throaty one.
    shape = field.newField('shape', 'SFString', 1, IMPACT)
    cutoff = field.newField('cutoff', 'SFFloat', 1, 400.0)
    pitch = field.newField('pitch', 'SFFloat', 1, 70.0)
    pitchEnd = field.newField('pitchEnd', 'SFFloat', 1, 35.0)
    tone = field.newField('tone', 'SFFloat', 1, 0.5)
    drive = field.newField('drive', 'SFFloat', 1, 1.0)
    #: How far the noise leans toward the bottom, in **decibels per octave**;
    #: 0 is white.  **This is where weight should come from**, not from
    #: ``tone``: a low sine under a hard attack is a drum, and one that falls
    #: as it goes is a drum being tuned, which is what a listener hears
    #: whenever the tone is carrying the bottom end however quiet it is.
    #: Tilted noise is a thump with no pitch in it, which is what a blast is.
    tilt = field.newField('tilt', 'SFFloat', 1, 0.0)
    #: Where its noise rolls away *below*, in **hertz**, as ``cutoff`` is where
    #: it rolls away above; 0 leaves the bottom alone.  The two together are a
    #: **band**, which is what anything hollow is — a tube rings around a pitch
    #: and has very little underneath it, and that hollowness is the whole
    #: difference between the pop of a mortar and a thump.
    floor = field.newField('floor', 'SFFloat', 1, 0.0)
    #: Seconds to reach full level.  0 is a transient, which is a detonation;
    #: anything else is something spooling up, which is a motor lighting.
    attack = field.newField('attack', 'SFFloat', 1, 0.0)

    #: What comes back off the walls: how loud the first return is relative to
    #: the sound itself (0 for none, which is every voice that does not say
    #: otherwise), how many **seconds** behind it arrives, and where a return
    #: loses its top in **hertz**.  A hard, sharp sound in a large place
    #: answers, and that answer is most of how a listener knows it was hard —
    #: a crack with nothing behind it could have come from anywhere.
    echo = field.newField('echo', 'SFFloat', 1, 0.0)
    echoDelay = field.newField('echoDelay', 'SFFloat', 1, 0.11)
    #: The tail of a room instead: how loud it is against the sound itself, and
    #: roughly how long it takes to die.  **Not the same thing as an echo and
    #: not a stronger version of one** — discrete returns are heard as returns,
    #: a clap and then another clap, where a room is heard as one sound going
    #: on.  A report with no tail reads as a drum however its spectrum is
    #: arranged, which is what the rifle sounded like until it had one.
    reverb = field.newField('reverb', 'SFFloat', 1, 0.0)
    reverbSeconds = field.newField('reverbSeconds', 'SFFloat', 1, 0.8)
    #: Where a return loses its top and where it loses its bottom, both in
    #: **hertz**: air takes the high end away as the sound travels, and the
    #: near-field thump of a gunshot never comes back off anything at all.
    #: Without them a return is the same sound again, which reads as somebody
    #: firing twice rather than as the first shot answering.
    echoDamping = field.newField('echoDamping', 'SFFloat', 1, 5000.0)
    echoThinning = field.newField('echoThinning', 'SFFloat', 1, 0.0)

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

    Chosen so the three that matter are told apart with the eyes shut, and the
    axis they are told apart *on* is where each sits in the spectrum.  A weapon
    firing is the low end — a report is a small explosion, and every one in the
    loadout is a rumble for that reason.  A round arriving is the top: bright,
    short and quiet, so it never competes with the shot that caused it.  A hit
    on a person is brighter still and rings a little longer, which is what makes
    "did I hit them" answerable across a room without looking.

    A weapon may name its own pair of impacts as well as its own report, which
    is how a rifle round lands with a chunk where a pistol round pings; what may
    not change is that a hit on a person stays louder and higher-priority than a
    hit on stone, whatever named it.

    A function rather than a constant, because a table is authored data with
    every field writable: a game (or a test) retuning one sound should not
    retune it for every other table in the process.
    """
    return SoundTable(voices=[
        Voice(key=FIRE, duration=0.16, decay=26.0, amplitude=0.95,
              gain=0.55, priority=0.5, seed=1),
        # The loadout's three.  **Every one of them is a rumble**, because a
        # firearm is a small explosion and the thing a listener hears first is
        # how much of one: noise under a decay has no bottom to it at any
        # setting, so a table made of it gives three weapons that differ only
        # in how long they last.  What tells these apart is how much of each is
        # charge and how much is the round leaving.
        #
        # **The numbers here were aimed at two recordings.**  A pistol shot and
        # a rifle shot were measured for their *shape* -- how their energy is
        # shared between the bottom, the middle and the top at the crack and
        # again in the tail -- and these are what land near it.  Nothing was
        # copied: the recordings are somebody else's and are not in this
        # repository, and every sound here is still made out of arithmetic.
        #
        # The pistol is nearly all charge: a body at 78 Hz falling to 44, very
        # little above a kilohertz, and a tail that goes on for a moment.  It
        # is a bang, and the ping it used to make now belongs to the round
        # arriving, which is where a small calibre is actually heard.
        # (Measured: crack at 491 Hz against the recording's 475, with 64% of
        # its power below 400 Hz against 73%.)
        Voice(key='fire-pistol', shape=RUMBLE, duration=0.42, decay=14.0,
              cutoff=1100.0, pitch=78.0, pitchEnd=44.0, tone=0.26, drive=3.0,
              echo=0.32, echoDelay=0.085, echoDamping=3200.0,
              echoThinning=120.0,
              amplitude=0.9, gain=0.5, priority=0.5, seed=11),
        # The shotgun: the lowest thing any weapon does, and the least
        # focussed -- an explosion that barely holds together.  Mostly noise
        # (`tone` low) with the top rolled almost all the way off, which is
        # what makes it rattle rather than crack: at this cutoff the noise
        # itself moves slowly enough to hear as a rattle.
        Voice(key='fire-shotgun', shape=RUMBLE, duration=0.62, decay=5.5,
              cutoff=150.0, pitch=72.0, pitchEnd=27.0, tone=0.18, drive=5.5,
              amplitude=1.0, gain=0.7, priority=0.6, seed=12),
        # The rifle: a **crack**, and the only bright thing in the loadout.
        # The round leaves faster than sound and what a listener hears is the
        # whip of that rather than the charge behind it, so this is broadband
        # and over in a fifth of a second -- a third of its power above 4 kHz,
        # against the pistol's one per cent.
        #
        # **It has no tone in it at all**, and no weight to speak of either.
        # Both were tried and both made a drum: a low sine under a hard attack
        # *is* a drum, and so -- this is the less obvious one -- is a short
        # bottom-weighted noise burst with a hard attack and an exponential
        # decay, whatever its spectrum says.  A crack is the opposite shape.
        # `floor` takes the thud out of the very first millisecond, which is
        # otherwise a step and a step is a kick drum.
        #
        # **What makes it big is the room, and a room is not an echo.**  Three
        # discrete returns were tried too, and they are heard as *repeats* --
        # a clap, and then another clap -- over a burst this short.  What a
        # hard sound in a large place actually gives back is one sound going
        # on: dense, and darkening as the air takes the top out of it.  The
        # crack is over in fifty milliseconds and everything that says
        # *high-powered* about this arrives afterwards.
        # (Measured against the recording, slice by slice: it holds its
        # brightness for the first 60 ms and then darkens through 3.1 kHz at a
        # fifth of a second to 1.8 kHz at half a second, against the
        # recording's 2.3 and 1.6.  The recording holds its *level* far longer
        # than this does, which is what a stock effect's limiter does to one;
        # a shot that stayed at full level for a second would smother the
        # match.)
        Voice(key='fire-rifle', shape=RUMBLE, duration=0.10, decay=90.0,
              cutoff=9500.0, floor=120.0, tone=0.0, tilt=-0.9, drive=1.0,
              reverb=0.85, reverbSeconds=2.4,
              # Louder than the rest of the small arms: a crack is over in
              # twenty milliseconds where a roar goes on for half a second,
              # and at equal level the short one is the quieter of the two by
              # a long way.
              amplitude=0.95, gain=0.75, priority=0.6, seed=13),
        # The launchers: something long and low rather than a report, so that
        # hearing one is a warning rather than a note that somebody shot at
        # something.  The rocket is the **motor** and not the trigger -- it
        # takes a moment to light, it sits at the bottom of the range, and it
        # is the one sound in the game a player is meant to hear *behind* them
        # and turn round for.
        #
        # A **roar**, which means no tone in it at all: what a motor makes is
        # noise leaning hard toward the bottom (`tilt`) and driven until it
        # tears, and the falling sine this was built from before read as an
        # instrument playing a descending note rather than as a rocket.
        Voice(key='fire-rocket', shape=RUMBLE, duration=0.85, decay=3.4,
              attack=0.045, cutoff=900.0, tone=0.0, tilt=-2.5, drive=2.6,
              amplitude=0.85, gain=0.65, priority=0.7, seed=14),
        # And the grenade launcher: a **pop**, the way a mortar pops, because
        # what a 40 mm round leaving a tube does is cough rather than crack.
        # What makes it that rather than a thump is the `floor`: a tube rings
        # around a pitch and has almost nothing underneath it, so the bottom
        # is taken off as well as the top and what is left is hollow.  No tone
        # again -- this was the last voice in the table carrying its weight in
        # a falling sine, and it read as a drum for exactly that reason.
        # (Measured against a mortar recording: our bulk sits at 233 Hz
        # against its 300, with 95% of the power below a kilohertz against
        # 90%.)
        Voice(key='fire-grenade', shape=RUMBLE, duration=0.40, decay=12.0,
              cutoff=380.0, floor=150.0, tone=0.0, drive=1.8,
              amplitude=0.8, gain=0.5, priority=0.5, seed=15),
        Voice(key=WORLD, duration=0.13, decay=34.0, amplitude=0.55,
              gain=0.35, priority=0.2, seed=2),
        # Louder and longer than either, because it is the one a player acts
        # on and the one that must survive voice stealing in a firefight.
        Voice(key=FLESH, duration=0.22, decay=18.0, amplitude=0.85,
              gain=0.7, priority=0.8, seed=3),
        # The rifle's round arriving: a **chunk**, not a ping.  Short, hard
        # and low, which is a heavy round burying itself in something rather
        # than a small one glancing off it — and the one impact in the game
        # that has to carry as much weight as the report did.  Its pair on a
        # person keeps the generic's level and priority, because *did I hit
        # them* is the sound a player acts on whatever fired it.
        Voice(key='impact-rifle', shape=RUMBLE, duration=0.30, decay=17.0,
              cutoff=300.0, pitch=105.0, pitchEnd=44.0, tone=0.45, drive=3.0,
              amplitude=0.7, gain=0.4, priority=0.25, seed=6),
        Voice(key='flesh-rifle', shape=RUMBLE, duration=0.42, decay=11.0,
              cutoff=380.0, pitch=95.0, pitchEnd=36.0, tone=0.5, drive=3.6,
              amplitude=0.95, gain=0.7, priority=0.8, seed=7),
        Voice(key=DEATH, duration=0.55, decay=7.0, amplitude=0.8,
              gain=0.6, priority=0.9, seed=4),
        # Walking into something: a bubble going, which is what the pickups
        # are.  A rumble made of nothing but its tone (`tone` at one, so there
        # is no noise in it at all) and pitched *upward* -- a cavity that is
        # closing gets smaller, and something smaller rings higher, which is
        # the whole difference between a bubble popping and a drop falling.
        #
        # **Bright, and it is the only bright thing in the table.**  Every
        # weapon in the game is down at the bottom now, so the one piece of
        # good news it has cuts through a firefight without being loud.  It
        # does not outrank a hit on a person for a voice: good news can wait a
        # frame and *did I hit them* cannot.
        Voice(key=PICKUP, shape=RUMBLE, duration=0.12, decay=30.0,
              cutoff=6000.0, pitch=900.0, pitchEnd=2800.0, tone=1.0,
              drive=1.0, amplitude=0.55, gain=0.45, priority=0.55, seed=8),
        # The one sound that has to arrive in the chest rather than the ears:
        # deeper than anything a gun makes, saturated so it growls instead of
        # thumping, and left to fall away for a second so a burst has a tail to
        # take cover during.  Every burst is this one, whatever threw it.
        Voice(key=EXPLOSION, shape=RUMBLE, duration=1.15, decay=2.6,
              cutoff=180.0, pitch=78.0, pitchEnd=26.0, tone=0.4, drive=4.5,
              amplitude=1.0, gain=0.9, priority=0.95, seed=5),
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
        """One voice as a clip: its file if it names one, else arithmetic.

        A ``shape`` the generators do not answer to is made as an
        :data:`IMPACT`, for the reason a missing file is silence rather than a
        crash: a table edited to something nobody has written yet should cost
        the sound its character and not the match.
        """
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
        if str(voice.shape) == RUMBLE:
            made = synth.rumble(duration=float(voice.duration),
                                amplitude=float(voice.amplitude),
                                decay=float(voice.decay),
                                attack=float(voice.attack),
                                cutoff=float(voice.cutoff),
                                pitch=float(voice.pitch),
                                pitch_end=float(voice.pitchEnd),
                                tone=float(voice.tone),
                                tilt=float(voice.tilt),
                                floor=float(voice.floor),
                                drive=float(voice.drive),
                                seed=int(voice.seed))
        else:
            made = synth.impact(duration=float(voice.duration),
                                amplitude=float(voice.amplitude),
                                decay=float(voice.decay),
                                seed=int(voice.seed))
        # Whatever it was made from, because what comes back off the walls is
        # a property of the *place* rather than of the generator.  A voice may
        # ask for discrete returns, for the tail of a room, or for neither;
        # both are silent by default and cost nothing when they are not asked
        # for.
        made = synth.echoed(made, delay=float(voice.echoDelay),
                            level=float(voice.echo), taps=ECHO_TAPS,
                            damping=float(voice.echoDamping),
                            thinning=float(voice.echoThinning))
        return synth.reverberated(made, seconds=float(voice.reverbSeconds),
                                  level=float(voice.reverb),
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
            return (self._impactKey(event), event.point)
        if isinstance(event, arenamod.Detonated):
            # Placed even when it is the player's own: a burst happens
            # *somewhere*, which is the whole of what a player has to know
            # about it, and a rocket that went off silently is a rocket nobody
            # takes cover from.
            return (EXPLOSION, event.point)
        if isinstance(event, arenamod.Death):
            return (DEATH, self._where(event.target))
        if isinstance(event, arenamod.PickedUp):
            # Placed at the thing that was taken, which is why the event
            # carries where it was: somebody else picking the armour up is
            # worth knowing about and worth being able to point at.  A pickup
            # that named no place is still heard, from nowhere in particular.
            return (PICKUP, event.point)
        return None

    def _fireKey(self, event: arenamod.Fired) -> str:
        """Which sound a weapon makes: its own if the table names one.

        A weapon naming its own sound is what makes a shotgun sound unlike a
        rifle, and it is a field on the weapon table rather than a branch here
        for the same reason its model is.
        """
        return self._named(event.weapon, 'fireSound', FIRE)

    def _impactKey(self, event: arenamod.Impact) -> str:
        """What one of this weapon's rounds sounds like arriving.

        The same rule as the report, on the other end of the shot: a rifle
        round lands with a chunk and a pistol round with a ping, so which of
        the two it was is the weapon's business.  Which *kind* of impact it is
        stays this module's: a hit on a person and a hit on stone answer
        different questions for a player, and they are two fields of the
        weapon rather than one so that distinction survives whatever a weapon
        names.
        """
        if event.on_somebody:
            return self._named(event.weapon, 'fleshSound', FLESH)
        return self._named(event.weapon, 'impactSound', WORLD)

    def _named(self, key: str, wanted: str, generic: str) -> str:
        """The voice a weapon names in ``wanted``, or the generic one.

        A key naming nothing in the sound table falls back too, for the same
        reason a missing file does: a table half-edited should cost a sound
        its character and never a match.
        """
        weapon = (self.weapons.by_key(key)
                  if self.weapons is not None and key else None)
        named = str(getattr(weapon, wanted, '') or '')
        return named if named and self.bank.voice(named) is not None else generic

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
