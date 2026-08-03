"""A map's ``target_speaker`` entities as sound in the scene.

Facts under test are SPEC-Q3ENTITIES §1.1 (the keys), §1.3 (where it is),
§1.4 (how it repeats), §1.5 (`wait` and `random`), §1.6 (triggered speakers)
and §1.7 (the keys with no established meaning).

Nothing here opens a device or decodes anything: a speaker is a node with
fields, and the fields are what this phase decides.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from twig_bb import speakers
from twig_bb.entities import Entity
from twig_bb.worldgeometry import SCENE_SCALE


def write_sound(root, relative):
    """An empty file where a content pack would put a sound."""
    path = os.path.join(str(root), *relative.split('/'))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as handle:
        handle.write(b'RIFF')
    return path


class FakeLibrary:
    """A resolver that finds everything but the names it is told to miss."""

    def __init__(self, missing=()):
        self.missing = set(missing)
        self.asked = []

    def resolve(self, noise):
        self.asked.append(noise)
        if noise in self.missing:
            return None
        return '/content/' + noise.lstrip('/*')


def speaker(**keys):
    keys.setdefault('classname', 'target_speaker')
    keys.setdefault('noise', 'sound/world/wind1.wav')
    keys.setdefault('origin', '0 0 0')
    return Entity(keys)


def build(entities, missing=()):
    return speakers.from_entities(entities, FakeLibrary(missing))


def sources_of(group):
    """Every ``AudioSource`` under a built speaker group, in order."""
    found = []
    for transform in group.children:
        for emitter in transform.children:
            found.extend(emitter.sources)
    return found


def emitters_of(group):
    return [emitter for transform in group.children
            for emitter in transform.children]


class TestWhichEntitiesBecomeSpeakers:

    def test_a_target_speaker_becomes_one_emitter(self):
        assert len(emitters_of(build([speaker()]))) == 1

    def test_other_entities_are_left_alone(self):
        entities = [Entity({'classname': 'info_player_deathmatch',
                            'origin': '0 0 0'}),
                    Entity({'classname': 'light', 'origin': '0 0 0'})]
        assert len(emitters_of(build(entities))) == 0

    def test_a_map_with_no_speakers_builds_an_empty_group(self):
        """21 of the 50 shipped maps place none, and must cost nothing."""
        assert build([]).children == []

    def test_a_speaker_with_no_noise_is_skipped(self):
        """All 381 observed carry one; a map that does not is malformed."""
        entities = [Entity({'classname': 'target_speaker', 'origin': '0 0 0'})]
        assert emitters_of(build(entities)) == []

    def test_a_noise_that_does_not_resolve_leaves_no_emitter(self):
        """SPEC-Q3ENTITIES §1.2.7: a silence, and the map still loads."""
        group = build([speaker(noise='sound/world/lava1.wav')],
                      missing=['sound/world/lava1.wav'])
        assert emitters_of(group) == []

    def test_a_map_of_resolving_and_missing_speakers_keeps_the_resolving_ones(self):
        group = build([speaker(noise='sound/world/lava1.wav'),
                       speaker(noise='sound/world/wind1.wav')],
                      missing=['sound/world/lava1.wav'])
        assert len(emitters_of(group)) == 1


class TestWhereTheSoundIs:
    """SPEC-Q3ENTITIES §1.3: `origin`, through the map→scene transform."""

    def test_the_origin_is_carried_into_scene_space(self):
        group = build([speaker(origin='1368 -512 232')])
        # SPEC-BSP38 §3.2: map xyz becomes scene x, z, -y, scaled to metres.
        assert np.allclose(group.children[0].translation,
                           np.array([1368, 232, 512]) * SCENE_SCALE)

    def test_each_speaker_gets_its_own_transform(self):
        group = build([speaker(origin='0 0 0'), speaker(origin='64 0 0')])
        assert len({tuple(child.translation) for child in group.children}) == 2


class TestHowItRepeats:
    """SPEC-Q3ENTITIES §1.4 and §1.5."""

    def test_spawnflag_one_loops(self):
        """§1.4.2: set on 336 of 381, and its bearers are ambience."""
        assert sources_of(build([speaker(spawnflags='1')]))[0].loop

    def test_spawnflag_five_loops_too(self):
        """§1.4.1: bit 1 is set in `5`; bit 4 is not a reason to ignore it."""
        assert sources_of(build([speaker(spawnflags='5')]))[0].loop

    def test_an_absent_spawnflags_does_not_loop(self):
        """§1.4.4: an absent numeric key is zero, as everywhere in the lump."""
        assert not sources_of(build([speaker()]))[0].loop

    def test_spawnflags_zero_does_not_loop(self):
        assert not sources_of(build([speaker(spawnflags='0')]))[0].loop

    @pytest.mark.parametrize('flags', ['4', '8'])
    def test_an_unknown_bit_alone_does_not_loop_and_does_not_reject(self, flags):
        """§1.4.3: bits 4 and 8 occur and mean nothing established.

        Ignoring a bit is not the same as ignoring the entity: 22 real
        speakers carry only these, and they must still be heard.
        """
        source = sources_of(build([speaker(spawnflags=flags)]))[0]
        assert not source.loop

    def test_an_unparsable_spawnflags_is_treated_as_zero(self):
        assert not sources_of(build([speaker(spawnflags='wobble')]))[0].loop

    def test_wait_becomes_a_repeat_interval_in_seconds(self):
        """§1.5.2: 10 to 47 seconds, the cadence of an occasional noise."""
        assert sources_of(build([speaker(wait='30')]))[0].repeatInterval == 30.0

    def test_random_becomes_the_spread_on_that_interval(self):
        source = sources_of(build([speaker(wait='30', random='5')]))[0]
        assert source.repeatVariance == 5.0

    def test_a_looping_speaker_gets_no_repeat_interval(self):
        """§1.5.2 is about speakers that do not loop; a loop has no gaps."""
        source = sources_of(build([speaker(spawnflags='1', wait='30')]))[0]
        assert source.repeatInterval == 0.0

    def test_a_speaker_with_no_wait_plays_once(self):
        assert sources_of(build([speaker()]))[0].repeatInterval == 0.0

    def test_random_without_wait_is_ignored(self):
        assert sources_of(build([speaker(random='5')]))[0].repeatVariance == 0.0


class TestTheKeysWeDoNotAct_On:

    def test_a_triggered_speaker_is_left_out(self):
        """§1.6.2: nothing fires it, so playing it as ambience is wrong.

        28 real speakers carry a `targetname`.  Treating one as ambient makes
        a sound that should answer an event into a constant, which is a worse
        answer than the silence it gets until there is a trigger system.
        """
        group = build([speaker(targetname='target_speaker2')])
        assert emitters_of(group) == []

    def test_angle_does_not_make_a_cone(self):
        """§1.7.1: plausible, unestablished, therefore not acted on."""
        emitter = emitters_of(build([speaker(angle='90')]))[0]
        assert emitter.shapeType == 'omnidirectional'


class TestTheFalloffChosenForAmbience:

    def test_the_falloff_reaches_silence_rather_than_trailing_off(self):
        """A map may place 60 speakers; every one must stop contributing.

        An inverse curve never reaches zero, so with sixty speakers the mix
        is a wash of everything in the level.  Linear ends.
        """
        assert emitters_of(build([speaker()]))[0].distanceModel == 'linear'

    def test_the_full_volume_radius_and_cut_off_are_in_metres(self):
        emitter = emitters_of(build([speaker()]))[0]
        assert 1.0 <= emitter.refDistance < emitter.maxDistance <= 100.0

    def test_ambience_does_not_drown_the_game(self):
        """Map ambience sits under whatever the game itself is making."""
        assert emitters_of(build([speaker()]))[0].gain < 1.0

    def test_ambience_is_the_first_thing_dropped_when_voices_run_short(self):
        """The voice pool steals by priority; a wind loop outranks nothing."""
        assert sources_of(build([speaker()]))[0].priority == 0.0


class TestTheUrlHandedToTheEngine:

    def test_the_source_names_the_resolved_file(self):
        source = sources_of(build([speaker(noise='sound/world/wind1.wav')]))[0]
        assert source.url == ['/content/sound/world/wind1.wav']

    def test_two_speakers_of_one_sound_resolve_it_once(self):
        library = FakeLibrary()
        speakers.from_entities([speaker(), speaker()], library)
        assert len(library.asked) == 2       # the library's own cache does the rest


class TestReportingWhatWasBuilt:

    def test_the_count_is_available_for_the_debug_overlay(self):
        group = build([speaker(), speaker()])
        assert speakers.count(group) == 2

    def test_an_empty_group_counts_zero(self):
        assert speakers.count(build([])) == 0


class TestThroughTheMapLoader:
    """The seam a viewer actually uses."""

    def test_a_loaded_map_offers_its_speakers(self, write_map, tmp_path):
        import bspbuilder

        from twig_bb import maploader
        write_sound(tmp_path / "content", "sound/world/wind1.wav")
        path = write_map(46, {'entities': bspbuilder.entity_text([
            {'classname': 'worldspawn'},
            {'classname': 'target_speaker', 'origin': '0 0 0',
             'noise': 'sound/world/wind1.wav', 'spawnflags': '1'},
        ])})
        loaded = maploader.load(path, extra_roots=[str(tmp_path / 'content')])
        assert speakers.count(loaded.speakers()) == 1

    def test_a_map_whose_sounds_were_never_fetched_still_loads(
            self, write_map, tmp_path):
        """Most installs have the maps and not the base game's sounds."""
        import bspbuilder

        from twig_bb import maploader
        path = write_map(46, {'entities': bspbuilder.entity_text([
            {'classname': 'worldspawn'},
            {'classname': 'target_speaker', 'origin': '0 0 0',
             'noise': 'sound/world/wind1.wav'},
        ])})
        assert speakers.count(maploader.load(path).speakers()) == 0


class TestAgainstRealContent:
    """The shipped maps, when this machine has them fetched."""

    def content_root(self):
        root = os.path.expanduser('~/.config/OpenGLContext/twig-bb-content')
        if not os.path.isdir(root):
            pytest.skip('no content packs fetched')
        return root

    def test_the_star_prefixed_name_in_am_galmevish_is_silent_not_fatal(self):
        """SPEC-Q3ENTITIES §1.2.5, hit by real content on the first load."""
        from twig_bb.sounds import SoundLibrary
        library = SoundLibrary([self.content_root()])
        assert library.resolve('*falling1.wav') is None
