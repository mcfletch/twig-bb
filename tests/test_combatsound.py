"""What a fight sounds like: the table, the bank, and who is placed where.

None of this opens a device.  What is asserted is the decision — which sound,
at what level, from where — because that is the part that is a design, and a
test that needed a sound card would be a test nobody runs.
"""

from __future__ import annotations

import numpy as np
import pytest

from omi_audio import model as audiomodel

from twig_bb import arena, combatsound, game, weapons


class FakeEngine:
    """An engine that remembers what it was asked to play."""

    def __init__(self, resolves=True):
        self.played = []
        self.listened = None
        self.resolves = resolves

    def clip(self, source):
        return source if self.resolves else None

    def listen(self, platform):
        self.listened = platform
        return platform

    def play(self, source, emitter=None, position=None, forward=(0, 0, -1),
             gain=1.0, priority=0.0, loop=False, rate=1.0):
        if not self.resolves:
            return None
        self.played.append({
            'source': source, 'emitter': emitter, 'position': position,
            'gain': gain, 'priority': priority, 'loop': loop,
        })
        return object()


@pytest.fixture
def table():
    return combatsound.default_table()


@pytest.fixture
def engine():
    return FakeEngine()


@pytest.fixture
def match():
    made = arena.Arena(weapons=weapons.default_table(), fragLimit=15,
                       timeLimit=10.0)
    made.add(game.PLAYER_ID, position=(0.0, 0.0, 0.0), name='You')
    made.add('bot1', position=(10.0, 0.0, 0.0), bot=True, name='Bot 1')
    return made


@pytest.fixture
def sounds(table, engine, match):
    """As the game builds it: with the weapon table, which names the voices."""
    return combatsound.CombatSound(match, table=table, engine=lambda: engine,
                                   weapons=weapons.default_table())


class TestTheTable:
    """The sounds are declared, and every one of them is ours."""

    def test_it_names_the_three_a_fight_needs(self, table):
        """Did my input register, where did that go, and did I hit them."""
        for key in (combatsound.FIRE, combatsound.WORLD, combatsound.FLESH):
            assert table.by_key(key) is not None

    def test_it_names_death_too(self, table):
        assert table.by_key(combatsound.DEATH) is not None

    def test_a_hit_on_a_person_is_louder_than_one_on_a_wall(self, table):
        """It is the one that carries information the player acts on."""
        assert table.by_key(combatsound.FLESH).gain \
            > table.by_key(combatsound.WORLD).gain

    def test_a_hit_on_a_person_outranks_a_wall_for_a_voice(self, table):
        """A firefight runs out of voices; the informative sound must survive."""
        assert table.by_key(combatsound.FLESH).priority \
            > table.by_key(combatsound.WORLD).priority

    def test_every_sound_is_synthesised_unless_a_file_is_named(self, table):
        """Ours by arithmetic, so there is no licence to ship and none to check."""
        assert all(not str(voice.file) for voice in table.voices)

    def test_an_unknown_key_is_no_sound_rather_than_an_error(self, table):
        assert table.by_key('nothing-like-this') is None

    def test_every_weapon_in_the_loadout_has_a_voice(self, table):
        """Switching weapon that changed nothing you could hear is no switch."""
        for weapon in weapons.default_table().weapons:
            assert table.by_key(str(weapon.fireSound)) is not None

    def test_the_weapons_sound_different_from_each_other(self, table):
        heard = {(float(voice.duration), float(voice.decay))
                 for voice in (table.by_key(str(weapon.fireSound))
                               for weapon in weapons.default_table().weapons)}
        assert len(heard) == len(weapons.default_table().weapons)


class TestTheBank:

    def test_a_sound_is_made_once_and_then_kept(self, table, engine):
        bank = combatsound.SoundBank(table)
        first = bank.clip(engine, combatsound.FIRE)
        assert first is not None
        assert bank.clip(engine, combatsound.FIRE) is first

    def test_an_unknown_sound_is_silence_rather_than_a_crash(self, table, engine):
        """A game must not die because content is absent."""
        assert combatsound.SoundBank(table).clip(engine, 'nothing') is None

    def test_a_named_file_that_is_not_there_is_silence(self, table, engine, tmp_path):
        """The same rule the texture resolver follows."""
        table.voices[0].file = 'weapons/not-here.wav'
        bank = combatsound.SoundBank(table, assets=str(tmp_path))
        assert bank.clip(engine, str(table.voices[0].key)) is None

    def test_a_missing_sound_is_looked_for_once(self, table, engine, tmp_path):
        table.voices[0].file = 'weapons/not-here.wav'
        bank = combatsound.SoundBank(table, assets=str(tmp_path))
        key = str(table.voices[0].key)
        bank.clip(engine, key)
        assert key in bank.resolved


class TestWhatIsHeardAndFromWhere:

    def test_the_players_own_weapon_is_not_positional(self, sounds, engine, match):
        """It is in their hands; panning it would put their own gun beside them."""
        match.fired(game.PLAYER_ID, 'rifle', origin=(0, 0, 0), direction=(1, 0, 0))
        sounds.show(match.drain())
        assert engine.played[0]['emitter'].type == audiomodel.GLOBAL

    def test_somebody_elses_weapon_is_placed_where_they_fired_from(self, sounds,
                                                                   engine, match):
        """One of the few sounds a player genuinely locates an opponent by."""
        match.fired('bot1', 'rifle', origin=(9, 1, 0), direction=(-1, 0, 0))
        sounds.show(match.drain())
        assert engine.played[0]['emitter'].type == audiomodel.POSITIONAL
        assert tuple(engine.played[0]['position']) == (9.0, 1.0, 0.0)

    def test_an_impact_on_a_wall_is_placed_where_it_landed(self, sounds, engine,
                                                           match):
        match.impact(point=(4, 1, 2), normal=(0, 1, 0), surface='stone')
        sounds.show(match.drain())
        assert tuple(engine.played[0]['position']) == (4.0, 1.0, 2.0)

    def test_a_hit_on_a_person_sounds_different_from_one_on_a_wall(self, sounds,
                                                                    engine, match):
        match.impact(point=(1, 0, 0), normal=(0, 1, 0), surface='stone')
        match.impact(point=(2, 0, 0), normal=(0, 1, 0), target='bot1')
        sounds.show(match.drain())
        assert engine.played[0]['source'] is not engine.played[1]['source']

    def test_a_death_is_heard_where_it_happened(self, sounds, engine, match):
        match.combatant('bot1').position = np.array([7.0, 0.0, 0.0])
        match.damage('bot1', 500, by=game.PLAYER_ID)
        sounds.show(match.drain())
        placed = [one for one in engine.played if one['position'] is not None]
        assert placed and tuple(placed[-1]['position'])[0] == 7.0

    def test_nothing_loops(self, sounds, engine, match):
        """A one-shot that looped would be a gunshot that never stopped."""
        match.fired('bot1', 'rifle', origin=(0, 0, 0), direction=(1, 0, 0))
        match.impact(point=(1, 0, 0), normal=(0, 1, 0))
        sounds.show(match.drain())
        assert engine.played and not any(one['loop'] for one in engine.played)

    def test_a_shotgun_blast_is_one_report_not_eight(self, sounds, engine, match):
        """Eight pellets are eight impacts and one trigger pull."""
        match.fired(game.PLAYER_ID, 'shotgun', origin=(0, 0, 0),
                    direction=(1, 0, 0))
        for index in range(8):
            match.impact(point=(index, 0, 0), normal=(0, 1, 0), surface='stone')
        sounds.show(match.drain())
        fired = [one for one in engine.played
                 if one['emitter'].type == audiomodel.GLOBAL]
        assert len(fired) == 1


class TestNotHavingSound:

    def test_no_engine_is_silence_rather_than_a_crash(self, table, match):
        sounds = combatsound.CombatSound(match, table=table, engine=lambda: None)
        match.fired('bot1', 'rifle', origin=(0, 0, 0), direction=(1, 0, 0))
        assert sounds.show(match.drain()) == 0

    def test_no_events_opens_no_device(self, table, match):
        """Silence costs nothing: the engine is not even asked for."""
        asked = []
        sounds = combatsound.CombatSound(
            match, table=table, engine=lambda: asked.append(1))
        assert sounds.show([]) == 0
        assert not asked

    def test_a_sound_that_will_not_resolve_is_a_silent_shot(self, table, match):
        engine = FakeEngine(resolves=False)
        sounds = combatsound.CombatSound(match, table=table,
                                         engine=lambda: engine)
        match.fired('bot1', 'rifle', origin=(0, 0, 0), direction=(1, 0, 0))
        assert sounds.show(match.drain()) == 0


class TestTheListener:

    def test_the_camera_is_the_ear(self, sounds, engine, match):
        """Placement is meaningless until the engine knows where the head is."""
        platform = object()
        match.fired('bot1', 'rifle', origin=(0, 0, 0), direction=(1, 0, 0))
        sounds.show(match.drain(), platform=platform)
        assert engine.listened is platform

    def test_with_no_platform_the_sound_still_plays(self, sounds, engine, match):
        match.fired('bot1', 'rifle', origin=(0, 0, 0), direction=(1, 0, 0))
        assert sounds.show(match.drain()) == 1
        assert engine.listened is None


class TestABurst:
    """A rocket that goes off silently is a rocket nobody takes cover from."""

    def test_a_detonation_is_heard(self, sounds, engine, match):
        match.detonated(point=(3, 1, 0), kind='rocket', by='bot1')
        assert sounds.show(match.drain()) == 1

    def test_it_is_placed_where_it_went_off(self, sounds, engine, match):
        match.detonated(point=(3, 1, 0), kind='rocket', by='bot1')
        sounds.show(match.drain())
        assert tuple(engine.played[0]['position']) == (3.0, 1.0, 0.0)

    def test_it_is_positional_even_when_it_is_your_own(self, sounds, engine,
                                                       match):
        """Unlike your weapon: a burst happens *somewhere*, and that is the point."""
        match.detonated(point=(3, 1, 0), kind='rocket', by=game.PLAYER_ID)
        sounds.show(match.drain())
        assert engine.played[0]['emitter'].type == audiomodel.POSITIONAL

    def test_it_is_louder_than_a_gunshot(self, table):
        assert table.by_key(combatsound.EXPLOSION).gain \
            > table.by_key(combatsound.FIRE).gain

    def test_it_outranks_everything_for_a_voice(self, table):
        assert table.by_key(combatsound.EXPLOSION).priority == max(
            float(voice.priority) for voice in table.voices)


def centroid(clip):
    """The centre of gravity of a clip's spectrum, in hertz.

    One number for how bright a sound is, which is the whole of the difference
    between a crack and a boom and the thing a listener names first.

    Weighted by **power** rather than by magnitude.  The difference is not
    academic here: a rolled-off noise still carries a very quiet tail across
    ten kilohertz of bandwidth, and weighting by magnitude lets all that
    inaudible width drag the answer up — by which measure the shotgun, whose
    body is at 70 Hz and which puts three fifths of its energy below 100, reads
    as *brighter* than the rifle.  Power weighting agrees with what a listener
    would say, which is the only thing these numbers are standing in for.
    """
    spectrum = np.abs(np.fft.rfft(clip.samples)) ** 2
    freqs = np.fft.rfftfreq(clip.frames, 1.0 / clip.sample_rate)
    return float((freqs * spectrum).sum() / max(spectrum.sum(), 1e-12))


def power_below(clip, hertz):
    """The share of a clip's energy under ``hertz``, from 0 to 1.

    What "has weight" means when it is measured rather than described: a
    bright sound with a charge under it and a bright sound with nothing under
    it have similar centroids and are not remotely the same sound.
    """
    spectrum = np.abs(np.fft.rfft(clip.samples)) ** 2
    freqs = np.fft.rfftfreq(clip.frames, 1.0 / clip.sample_rate)
    return float(spectrum[freqs < hertz].sum() / max(spectrum.sum(), 1e-12))


def comes_back(clip, window=0.02, after=0.2):
    """How much louder a clip gets again after it has begun to die away.

    1 is a sound that only ever falls, which is every report on its own; an
    echo is the one thing that makes a later moment louder than the one before
    it, so this is what "it answers" is when it is measured rather than heard.
    The first fifth is skipped because that is the sound itself arriving.

    Level is the **root mean square** of each window rather than its peak, and
    the window is long enough to hold several cycles of the lowest thing here.
    A peak over five milliseconds of seventy-hertz noise is mostly luck about
    where the window fell, which reads as a shotgun echoing when it does not.
    """
    step = max(1, int(window * clip.sample_rate))
    level = [float(np.sqrt((clip.samples[at:at + step].astype('d') ** 2).mean()))
             for at in range(0, clip.frames - step, step)]
    start = max(1, int(len(level) * after))
    rises = [level[at] / level[at - 1] for at in range(start, len(level))
             if level[at - 1] > 1e-6]
    return max(rises) if rises else 1.0


def level_at(clip, when, window=0.03):
    """How loud a clip still is ``when`` seconds in, in dB below its peak."""
    at = int(when * clip.sample_rate)
    part = clip.samples[at:at + int(window * clip.sample_rate)]
    if not len(part):
        return -99.0
    loud = float(np.sqrt((part.astype('d') ** 2).mean()))
    top = float(np.abs(clip.samples).max())
    return 20.0 * float(np.log10(max(loud, 1e-9) / max(top, 1e-9)))


def colour_at(clip, when, window=0.06):
    """The centre of a clip's spectrum over a window part-way through it."""
    at = int(when * clip.sample_rate)
    part = clip.samples[at:at + int(window * clip.sample_rate)]
    spectrum = np.abs(np.fft.rfft(part)) ** 2
    freqs = np.fft.rfftfreq(len(part), 1.0 / clip.sample_rate)
    return float((freqs * spectrum).sum() / max(spectrum.sum(), 1e-20))


def at_its_pitch(table, clip, key):
    """The share of a voice's power sitting at the pitch it declares.

    How much of a sound is a *note* rather than the noise around it, which is
    the difference between a boom and a roar and cannot be read off brightness
    — the two are equally low.  The band is the voice's own ``pitch`` and
    ``pitchEnd`` with a little room either side, because a rumble's body
    sweeps between them as it goes.
    """
    voice = table.by_key(key)
    spectrum = np.abs(np.fft.rfft(clip.samples)) ** 2
    freqs = np.fft.rfftfreq(clip.frames, 1.0 / clip.sample_rate)
    body = ((freqs >= float(voice.pitchEnd) * 0.85)
            & (freqs < float(voice.pitch) * 1.15))
    return float(spectrum[body].sum() / max(spectrum.sum(), 1e-12))


class TestTheWeightOfTheBigWeapons:
    """A launcher and a burst are heard at the bottom of the range.

    Everything else in the table is noise under a decay, which is bright
    however long it is left to ring: it makes a crack, a snap and a hiss, and
    a detonation built out of it is a very loud version of a rifle.  These two
    are :func:`omi_audio.synth.rumble` instead, and what is asserted is
    the only thing that matters about that -- that they are *low*, and lower
    than the small arms firing beside them.
    """

    def clip(self, table, engine, key):
        return combatsound.SoundBank(table).clip(engine, key)

    def test_the_launcher_rumbles_where_a_report_cracks(self, table, engine):
        """Against the table's generic report, which is still noise and a decay.

        Every weapon in the loadout names a voice of its own now and all of
        them are low, so the thing to hold this against is the sound a weapon
        that has named nothing gets.
        """
        assert centroid(self.clip(table, engine, 'fire-rocket')) \
            < centroid(self.clip(table, engine, combatsound.FIRE)) * 0.25

    def test_a_burst_is_deeper_than_any_weapon_firing(self, table, engine):
        """It is the loudest thing in the game; it must not be the shrillest."""
        burst = centroid(self.clip(table, engine, combatsound.EXPLOSION))
        assert burst < min(centroid(self.clip(table, engine, str(weapon.fireSound)))
                           for weapon in weapons.default_table().weapons)

    def test_a_burst_rings_on_longer_than_a_shot(self, table):
        """The tail is what makes it read as a detonation and not as a hit."""
        assert float(table.by_key(combatsound.EXPLOSION).duration) > max(
            float(table.by_key(str(weapon.fireSound)).duration)
            for weapon in weapons.default_table().weapons)

    def test_a_grenade_and_a_rocket_go_off_as_one_sound(self, sounds, engine,
                                                         match):
        """One burst, whatever threw it: the bang is the burst's, not the gun's."""
        match.detonated(point=(3, 1, 0), kind='rocket', by='bot1')
        match.detonated(point=(3, 1, 0), kind='grenade', by='bot1')
        sounds.show(match.drain())
        assert engine.played[0]['source'] is engine.played[1]['source']


class TestPickingSomethingUp:
    """The one sound in the table that is not a fight, and it pops.

    A player who cannot hear that they took the armour has, as far as they can
    tell, not taken it — and the thing they walked into was a bubble, so what
    it does when it goes is pop.  Bright on purpose: everything else here is
    low, so a pickup cuts through a firefight without having to be loud.
    """

    def taken(self, sounds, engine, match, where=(4.0, 1.0, 2.0)):
        match.picked_up(game.PLAYER_ID, key='armour', title='ARMOUR',
                        point=where)
        sounds.show(match.drain())
        return engine.played[-1]

    def test_it_is_heard(self, sounds, engine, match):
        assert self.taken(sounds, engine, match)['source'] is not None

    def test_it_comes_from_the_thing_that_was_taken(self, sounds, engine,
                                                     match):
        """Somebody else taking the armour is worth knowing, and worth placing."""
        assert tuple(self.taken(sounds, engine, match)['position']) \
            == (4.0, 1.0, 2.0)

    def test_one_with_nowhere_to_be_still_sounds(self, sounds, engine, match):
        """A pickup that named no place is still a pickup, and never silence."""
        match.picked_up(game.PLAYER_ID, key='armour', title='ARMOUR')
        assert sounds.show(match.drain()) == 1

    def test_it_is_a_pop_rather_than_a_thump(self, sounds, engine, match,
                                             table):
        """Bright, where every weapon in the game is low."""
        clip = sounds.bank.clip(engine, combatsound.PICKUP)
        assert centroid(clip) > 1000.0
        assert clip.duration < 0.25

    def test_it_rises_the_way_a_bubble_does(self, sounds, engine, table):
        """What tells a pop from a click: the pitch goes *up* as it goes.

        A bubble collapsing gets smaller as it closes, and a cavity that is
        getting smaller rings higher — which is why a rising chirp reads as a
        bubble and a falling one reads as a drop of water.
        """
        clip = sounds.bank.clip(engine, combatsound.PICKUP)
        half = clip.frames // 2
        freqs = np.fft.rfftfreq(half, 1.0 / clip.sample_rate)
        first = np.abs(np.fft.rfft(clip.samples[:half]))
        second = np.abs(np.fft.rfft(clip.samples[half:]))
        assert freqs[second.argmax()] > freqs[first.argmax()]

    def test_it_does_not_outrank_being_shot_at(self, table):
        """Good news can wait; a hit on a person cannot."""
        assert float(table.by_key(combatsound.PICKUP).priority) \
            < float(table.by_key(combatsound.FLESH).priority)


class TestWhatTheSmallArmsSoundLike:
    """Three weapons, three *characters*, and none of them a hiss.

    Noise under a decay is the same sound at every setting -- it can be longer
    or shorter and that is all -- so a table made entirely of it gives three
    weapons that differ only in how long they last.  Each of these is a claim
    about what the weapon *is*, and the numbers in the table are whatever makes
    it true.
    """

    def clip(self, table, engine, key):
        return combatsound.SoundBank(table).clip(engine, key)

    def fire(self, table, engine, key):
        weapon = weapons.default_table().by_key(key)
        return self.clip(table, engine, str(weapon.fireSound))

    def test_no_weapon_in_the_loadout_is_a_hiss(self, table, engine):
        """Every one of them has weight; not one is the bare noise it started as.

        The whole table rather than the three, because a weapon left on the
        generic noise is the one a player notices — it does not sound like a
        quieter version of the others, it sounds like a different game.  Held
        as *power down where a charge is* rather than as brightness.

        **The rifle is exempt and that is a decision, not an oversight.**  It
        is the one weapon whose sound is the round rather than the charge, so
        it is bright by design; what it has instead of weight is the tail
        below, and it would fail this rule for exactly the reason it is right.
        """
        for weapon in weapons.default_table().weapons:
            if str(weapon.key) == 'rifle':
                continue
            assert power_below(self.fire(table, engine, str(weapon.key)),
                               400.0) > 0.1, weapon.key

    def test_the_shotgun_is_the_lowest_of_the_three(self, table, engine):
        low = centroid(self.fire(table, engine, 'shotgun'))
        assert low < centroid(self.fire(table, engine, 'pistol'))
        assert low < centroid(self.fire(table, engine, 'rifle'))

    def test_the_shotgun_barely_holds_together(self, table, engine):
        """An explosion with no pitch in it, which is what a roar is.

        Held against the burst, which is the same bottom of the range done the
        other way round: nine tenths of a detonation sits at the pitch it
        declares, and it reads as one deep note.  Less than half of this does,
        so what is left is the noise around it -- and that is the difference
        between a boom and a rattle.

        *How* rattly is not a number, and the last word on it is listening;
        what a test can hold is that it has not quietly become a boom.
        """
        assert at_its_pitch(table, self.fire(table, engine, 'shotgun'),
                            'fire-shotgun') < 0.5
        assert at_its_pitch(table, self.clip(table, engine, combatsound.EXPLOSION),
                            combatsound.EXPLOSION) > 0.8

    def test_the_rifle_is_the_sharpest_and_highest_of_them(self, table, engine):
        """A crack, and the one weapon in the game that is meant to be one.

        Everything else here is a body: the round is what a rifle is *about*,
        it leaves faster than sound, and what a listener hears is the whip of
        that rather than the charge behind it.  Pitched low it does not read as
        powerful, it reads as a drum.
        """
        rifle = centroid(self.fire(table, engine, 'rifle'))
        for other in ('pistol', 'shotgun', 'grenade', 'rocket'):
            assert rifle > centroid(self.fire(table, engine, other)) * 2.0, other

    def test_what_it_has_instead_of_weight_is_a_room(self, table, engine):
        """It goes on long after it has stopped, which is what makes it big.

        The crack itself is over in fifty milliseconds — that is what "sharp"
        costs — so everything that says *high-powered* about it arrives
        afterwards, off the walls.  The generic report is the control: the same
        sharpness with nowhere to be, and by a third of a second it is gone.
        """
        assert level_at(self.fire(table, engine, 'rifle'), 0.3) > -40.0
        assert level_at(self.clip(table, engine, combatsound.FIRE), 0.3) < -60.0

    def test_the_room_is_a_wash_and_not_a_clap(self, table, engine):
        """The fault this replaced, and the reason it is asserted backwards.

        Three discrete returns are heard as *repeats* — a clap, and then
        another clap — which over a short bright burst is a drum being played
        rather than a rifle in a valley.  What a hard sound in a large place
        gives back is one sound going on, so the level must only ever fall:
        anything that gets louder again is a repeat.
        """
        assert comes_back(self.fire(table, engine, 'rifle')) < 2.0

    def test_and_the_tail_darkens_as_it_goes(self, table, engine):
        """Air takes the top first, which is the difference between a room and
        static held under a fader."""
        clip = self.fire(table, engine, 'rifle')
        assert colour_at(clip, 0.45) < colour_at(clip, 0.02) * 0.6

    def test_the_pistol_is_a_bang_and_not_a_ping(self, table, engine):
        assert centroid(self.fire(table, engine, 'pistol')) \
            < centroid(self.clip(table, engine, combatsound.WORLD)) * 0.5

    def test_the_pistol_sits_between_the_other_two(self, table, engine):
        """Above the shotgun's roar and a long way under the rifle's crack.

        Which is what it is: a charge with very little round in front of it,
        where the shotgun is all charge and the rifle is nearly all round.
        """
        pistol = centroid(self.fire(table, engine, 'pistol'))
        assert centroid(self.fire(table, engine, 'shotgun')) < pistol
        assert pistol < centroid(self.fire(table, engine, 'rifle'))


class TestWhatAWeaponSoundsLikeWhenItLands:
    """The other half of a shot, and the half that says what it *did*.

    A rifle round arriving has to be a chunk and a pistol round a ping, so the
    impact is the weapon's as much as the report is: a weapon may name its own
    and falls back to the table's generic pair when it does not.  The generic
    pair stays what it always was -- a ping on stone, a brighter ring on a
    person -- which is what an unnamed weapon and every future one get.
    """

    def clip(self, sounds, engine, key):
        """Through the same bank the match plays from, so identity means something."""
        return sounds.bank.clip(engine, key)

    def landed(self, sounds, engine, match, key, on='', surface='stone'):
        """Play one impact from ``key``'s shot; returns the clip it chose."""
        match.impact(point=(1, 0, 0), normal=(0, 1, 0), surface=surface,
                     target=on, by=game.PLAYER_ID, weapon=key)
        sounds.show(match.drain())
        return engine.played[-1]['source']

    def test_a_rifle_round_lands_with_a_chunk(self, sounds, engine, match):
        """Low and short: what a heavy round arriving in something sounds like."""
        assert centroid(self.landed(sounds, engine, match, 'rifle')) \
            < centroid(self.clip(sounds, engine, combatsound.WORLD)) * 0.5

    def test_and_so_does_a_rifle_round_that_lands_on_somebody(self, sounds,
                                                              engine, match):
        """Where it matters most: you hit them, and you can hear that you did."""
        on_stone = self.landed(sounds, engine, match, 'rifle')
        on_them = self.landed(sounds, engine, match, 'rifle', on='bot1')
        assert on_them is not on_stone

    def test_a_pistol_round_still_pings(self, sounds, engine, match):
        """It is the weapon with no weight; the report carries it instead."""
        assert self.landed(sounds, engine, match, 'pistol') \
            is self.clip(sounds, engine, combatsound.WORLD)

    def test_a_weapon_that_names_nothing_gets_the_generic_pair(self, sounds,
                                                               engine, match):
        assert self.landed(sounds, engine, match, 'nothing-like-this') \
            is self.clip(sounds, engine, combatsound.WORLD)

    def test_an_impact_from_no_weapon_at_all_still_sounds(self, sounds, engine,
                                                          match):
        """A hit that named nothing is still a hit; a silent one is a bug."""
        match.impact(point=(1, 0, 0), normal=(0, 1, 0), surface='stone')
        assert sounds.show(match.drain()) == 1

    def test_hitting_a_person_always_outranks_hitting_a_wall(self, table):
        """The rule the whole table is arranged around, held per weapon.

        A firefight runs the voice pool dry and *did I hit them* is the sound
        a player acts on, so a weapon naming its own pair may not quietly
        invert that for itself.
        """
        bank = combatsound.SoundBank(table)
        for weapon in weapons.default_table().weapons:
            flesh = bank.voice(str(weapon.fleshSound) or combatsound.FLESH)
            world = bank.voice(str(weapon.impactSound) or combatsound.WORLD)
            assert float(flesh.gain) > float(world.gain), weapon.key
            assert float(flesh.priority) > float(world.priority), weapon.key
