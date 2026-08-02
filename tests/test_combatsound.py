"""What a fight sounds like: the table, the bank, and who is placed where.

None of this opens a device.  What is asserted is the decision — which sound,
at what level, from where — because that is the part that is a design, and a
test that needed a sound card would be a test nobody runs.
"""

from __future__ import annotations

import numpy as np
import pytest

from omi_audio import model as audiomodel

from twitchoglc import arena, combatsound, game, weapons


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
    return combatsound.CombatSound(match, table=table, engine=lambda: engine)


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
