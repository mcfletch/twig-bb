"""What a session recording is told about the game it is recording.

The engine records what the platform delivered and how long each frame took.
None of that says a level finished loading, that somebody picked up the rocket
launcher they were about to lose the match without, or that a bot saw the player
four seconds before it shot them -- and those are what a reader of a journal is
looking for.  :mod:`twig_bb.telemetry` turns the game's own event stream into
those lines.

It holds no window and no GL, which is what lets the whole of it be checked
here: hand it a stream of events and read the marks that came out.
"""

from __future__ import annotations

import numpy as np
import pytest

from twig_bb import arena, controls, game, items, telemetry, weapons


class Session:
    """A context that keeps what was marked on it, as the engine's does."""

    def __init__(self, recording=True):
        self.telemetry = object() if recording else None
        self.marks = []

    def mark(self, name, /, **fields):
        # Positional, exactly as the engine's own takes it, so a field may be
        # called ``name``.
        self.marks.append((name, fields))

    def named(self, name):
        return [fields for made, fields in self.marks if made == name]


@pytest.fixture
def session():
    return Session()


@pytest.fixture
def marks(session):
    return telemetry.GameMarks(session)


@pytest.fixture
def match():
    made = arena.Arena(weapons=weapons.default_table(), fragLimit=15,
                       timeLimit=10.0)
    made.add(game.PLAYER_ID, position=(0.0, 0.0, 0.0), name='You')
    made.add('bot1', position=(10.0, 0.0, 0.0), bot=True, name='Bot 1')
    return made


class TestWhatTheLevelSays:
    def test_a_level_being_loaded_is_marked_before_it_arrives(self, marks,
                                                              session):
        """Seconds pass between the two, and a session that died in them is
        a session whose last line says which map it was reading."""
        marks.loading('maps/ztn3dm1.bsp')
        assert session.named('level-loading') == [
            {'target': 'maps/ztn3dm1.bsp'}]

    def test_a_loaded_level_says_what_it_is(self, marks, session, match):
        marks.loaded(_Level(), match, title='Blood Run')
        found = session.named('level-loaded')[0]
        assert found['map'] == 'ztn3dm1'
        assert found['family'] == 'quake3'
        assert found['title'] == 'Blood Run'
        assert found['pickups'] == 3
        assert found['spawns'] == 2

    def test_the_match_in_it_is_its_own_mark(self, marks, session, match):
        marks.loaded(_Level(), match)
        assert session.named('match-started') == [
            {'bots': 1, 'combatants': 2, 'frag limit': 15, 'minutes': 10.0}]

    def test_a_level_that_would_not_load_says_why(self, marks, session):
        marks.failed('maps/nope.bsp', ValueError('no such map'))
        assert session.named('level-failed') == [
            {'target': 'maps/nope.bsp', 'error': 'no such map',
             'type': 'ValueError'}]


class TestWhatTheWeaponsSay:
    def test_choosing_a_weapon_is_marked(self, marks, session):
        marks.commands([controls.Event('select', 'Rocket Launcher')],
                       weapon='rocket')
        assert session.named('weapon-selected') == [
            {'weapon': 'rocket', 'title': 'Rocket Launcher'}]

    def test_an_empty_weapon_is_marked(self, marks, session):
        """The frame a player thinks they fired and did not."""
        marks.commands([controls.Event('empty', 'OUT OF ROCKETS')],
                       weapon='rocket')
        assert session.named('weapon-empty') == [{'weapon': 'rocket',
                                                  'said': 'OUT OF ROCKETS'}]

    def test_a_weapon_the_player_does_not_carry_is_marked(self, marks, session):
        marks.commands([controls.Event('refused', 'NO RAILGUN')],
                       weapon='pistol')
        assert session.named('weapon-refused') == [{'said': 'NO RAILGUN'}]

    def test_pulling_the_trigger_is_left_to_the_match(self, marks, session):
        """A shot reaches the stream as ``Fired``, for the player and for a
        bot alike; marking the command as well would say it twice."""
        marks.commands([controls.Event('fire')], weapon='pistol')
        assert session.marks == []


class TestWhatTheMatchSays:
    def test_a_shot_is_marked_with_who_fired_it(self, marks, session):
        marks.events([arena.Fired(shooter='bot1', weapon='rifle',
                                  origin=(1.0, 2.0, 3.0),
                                  direction=(0.0, 0.0, -1.0))])
        assert session.named('fired') == [
            {'by': 'bot1', 'weapon': 'rifle', 'at': [1.0, 2.0, 3.0]}]

    def test_a_hit_on_somebody_is_marked_and_a_wall_is_not(self, marks,
                                                           session):
        marks.events([
            arena.Impact(point=(1.0, 0.0, 0.0), normal=(0.0, 1.0, 0.0),
                         target='bot1', by=game.PLAYER_ID, weapon='rifle'),
            arena.Impact(point=(2.0, 0.0, 0.0), normal=(0.0, 1.0, 0.0),
                         surface='textures/base/wall'),
        ])
        assert session.named('hit') == [
            {'by': game.PLAYER_ID, 'target': 'bot1', 'weapon': 'rifle'}]

    def test_damage_is_marked_with_what_landed(self, marks, session):
        marks.events([arena.Damaged(target=game.PLAYER_ID, amount=35,
                                    by='bot1')])
        assert session.named('damaged') == [
            {'target': game.PLAYER_ID, 'by': 'bot1', 'amount': 35}]

    def test_the_map_hurting_somebody_says_what_did_it(self, marks, session):
        marks.events([arena.Damaged(target=game.PLAYER_ID, amount=10,
                                    by=arena.NOBODY, cause='lava')])
        assert session.named('damaged')[0]['cause'] == 'lava'

    def test_a_death_is_marked(self, marks, session):
        marks.events([arena.Death(target='bot1', by=game.PLAYER_ID)])
        assert session.named('death') == [{'target': 'bot1',
                                           'by': game.PLAYER_ID}]

    def test_a_pickup_is_marked_with_what_was_taken(self, marks, session):
        marks.events([arena.PickedUp(target=game.PLAYER_ID, key='armour',
                                     title='Armour', point=(4.0, 0.0, 8.0))])
        assert session.named('pickup') == [
            {'target': game.PLAYER_ID, 'item': 'armour',
             'at': [4.0, 0.0, 8.0]}]

    def test_a_burst_is_marked(self, marks, session):
        marks.events([arena.Detonated(point=(0.0, 1.0, 0.0), kind='rocket',
                                      by='bot1', target=game.PLAYER_ID)])
        assert session.named('detonated') == [
            {'kind': 'rocket', 'by': 'bot1', 'target': game.PLAYER_ID,
             'at': [0.0, 1.0, 0.0]}]

    def test_the_end_of_the_match_is_marked(self, marks, session):
        marks.events([arena.MatchOver(winner=game.PLAYER_ID, reason='frags')])
        assert session.named('match-over') == [{'winner': game.PLAYER_ID,
                                                'reason': 'frags'}]

    def test_a_respawn_says_where_somebody_came_back(self, marks, session):
        marks.respawned({'bot1': np.array([1.0, 2.0, 3.0])})
        assert session.named('spawned') == [{'who': 'bot1',
                                             'at': [1.0, 2.0, 3.0]}]

    def test_asking_to_come_back_is_marked(self, marks, session):
        """The trigger is what ends a death, so a death that went on is a
        death nobody asked to end."""
        marks.asked_to_respawn(game.PLAYER_ID)
        assert session.named('respawn-asked') == [{'who': game.PLAYER_ID}]

    def test_a_held_trigger_asks_once(self, marks, session):
        """It arrives every frame until the wait is over, and sixty marks a
        second saying the same thing bury the one that says it was first
        made."""
        for _each in range(20):
            marks.asked_to_respawn(game.PLAYER_ID)
        assert len(session.named('respawn-asked')) == 1

    def test_the_next_death_asks_again(self, marks, session):
        marks.asked_to_respawn(game.PLAYER_ID)
        marks.respawned({game.PLAYER_ID: np.zeros(3)})
        marks.asked_to_respawn(game.PLAYER_ID)
        assert len(session.named('respawn-asked')) == 2


class TestWhatTheSessionAroundTheGameSays:
    def test_changing_how_the_camera_is_steered_is_marked(self, marks, session):
        """Every input after it means something different."""
        marks.movement('fly')
        assert session.named('movement-mode') == [{'mode': 'fly'}]

    def test_walking_and_free_flying_are_marked(self, marks, session):
        marks.walking(True, mode='fps')
        assert session.named('walking') == [{'on': True, 'mode': 'fps'}]

    def test_a_screen_going_up_is_marked(self, marks, session):
        """While one is up nothing reaches the world, which otherwise reads
        in a journal like a session that has stopped answering."""
        marks.screen('start')
        assert session.named('screen') == [{'name': 'start'}]

    def test_a_download_is_marked_at_both_ends(self, marks, session):
        marks.downloading([_Pack('quake3-core')])
        marks.downloaded(_Job())
        assert session.named('download-started') == [
            {'packs': ['quake3-core']}]
        assert session.named('download-finished') == [
            {'roots': 1, 'cancelled': False, 'error': ''}]

    def test_a_download_that_would_not_finish_says_why(self, marks, session):
        marks.downloaded(_Job(failed=OSError('no route to host')))
        assert session.named('download-finished')[0]['error'] == (
            'no route to host')


class TestWhatTheBotsSay:
    def test_a_bot_finding_somebody_is_marked(self, marks, session):
        minds = {'bot1': _Mind('')}
        marks.minds(minds)
        minds['bot1'].target = game.PLAYER_ID
        marks.minds(minds)
        assert session.named('bot-target') == [{'bot': 'bot1',
                                                'target': game.PLAYER_ID}]

    def test_losing_them_again_is_marked(self, marks, session):
        minds = {'bot1': _Mind(game.PLAYER_ID)}
        marks.minds(minds)
        minds['bot1'].target = ''
        marks.minds(minds)
        assert session.named('bot-lost') == [{'bot': 'bot1',
                                              'target': game.PLAYER_ID}]

    def test_a_bot_that_goes_on_fighting_the_same_person_says_nothing(
            self, marks, session):
        """Sixty marks a second saying nothing happened would bury the one
        that says something did."""
        minds = {'bot1': _Mind(game.PLAYER_ID)}
        for _ in range(10):
            marks.minds(minds)
        assert len(session.named('bot-target')) == 1

    def test_a_new_match_forgets_what_the_last_one_s_bots_were_doing(
            self, marks, session, match):
        minds = {'bot1': _Mind(game.PLAYER_ID)}
        marks.minds(minds)
        marks.loaded(_Level(), match)
        marks.minds(minds)
        assert len(session.named('bot-target')) == 2


class TestWhatItCostsWhenNobodyIsListening:
    def test_a_game_nobody_is_recording_makes_no_marks(self):
        """The guard lives here, once, so every call site is unconditional."""
        quiet = Session(recording=False)
        made = telemetry.GameMarks(quiet)
        made.events([arena.Fired(shooter='bot1', weapon='rifle',
                                 origin=(0.0, 0.0, 0.0),
                                 direction=(0.0, 0.0, -1.0))])
        made.minds({'bot1': _Mind(game.PLAYER_ID)})
        assert quiet.marks == []

    def test_it_starts_saying_things_the_moment_recording_begins(self):
        """Recording can begin at any point in a session."""
        later = Session(recording=False)
        made = telemetry.GameMarks(later)
        made.loading('maps/ztn3dm1.bsp')
        later.telemetry = object()
        made.loading('maps/ztn3dm1.bsp')
        assert len(later.named('level-loading')) == 1


class _Pack:
    """A content pack, as much of one as a mark reads."""

    def __init__(self, key):
        self.key = key


class _Job:
    """A finished download, as much of one as a mark reads."""

    def __init__(self, failed=None, cancelled=False):
        self.roots = ['/tmp/quake3-core']
        self.failed = failed
        self.cancelled = cancelled


class _Mind:
    """A bot's mind, as much of one as a mark reads."""

    def __init__(self, target=''):
        self.target = target


class _Level:
    """A loaded map, as much of one as a mark reads."""

    name = 'ztn3dm1'
    family = 'quake3'
    title = 'Blood Run'

    def pickups(self):
        table = items.default_table()
        return [items.Pickup(kind=table.by_key('health'),
                             position=np.zeros(3))] * 3

    def spawn_points(self):
        return [object(), object()]
