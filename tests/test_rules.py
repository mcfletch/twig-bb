"""One tick of a match, played with no window in front of it.

This is the half of the frame loop that was untestable and therefore the half
that broke: the two worst bugs this game has had were both a line inside
`OnDraw`. Everything here runs against a constructed world of three boxes.
"""

from __future__ import annotations

import numpy as np
import pytest

from omi_physics import model
from omi_physics.world import PhysicsWorld

from twig_bb import (arena, avatar, bots, falling, game, liquids,
                        projectiles, rules, weapons)


def world():
    return PhysicsWorld(gravity=model.Gravity(gravity=9.81, direction=(0, -1, 0)))


def match(bots_in=1, **named):
    made = arena.Arena(weapons=weapons.default_table(), **named)
    made.add(game.PLAYER_ID, position=(0.0, 0.0, 0.0), name='You')
    for index in range(bots_in):
        made.add('bot%d' % (index + 1,), position=(10.0 + index * 5, 0.0, 0.0),
                 bot=True, difficulty='medium', name='Bot %d' % (index + 1,))
    return made


def played(found, spawns=((0.0, 1.6, 0.0),), **named):
    return rules.Rules(found, minds=game.place_bots(found, seed=1),
                       flight=projectiles.Projectiles(
                           projectiles.default_table()),
                       spawns=[np.asarray(one, dtype='d') for one in spawns],
                       **named)


def pistol():
    return weapons.default_table().by_key('pistol')


class TestATickOfAMatch:

    def test_it_returns_what_the_match_said(self):
        found = match()
        made = played(found)
        found.damage('bot1', 10, by=game.PLAYER_ID)
        tick = made.advance(world(), 0.1, pistol())
        assert [type(event).__name__ for event in tick.events] == ['Damaged']

    def test_it_drains_the_stream_so_nothing_is_shown_twice(self):
        found = match()
        made = played(found)
        found.damage('bot1', 10, by=game.PLAYER_ID)
        made.advance(world(), 0.1, pistol())
        assert made.advance(world(), 0.1, pistol()).events == []

    def test_the_clock_moves(self):
        found = match()
        played(found).advance(world(), 0.25, pistol())
        assert found.elapsed == pytest.approx(0.25)

    def test_a_match_with_no_weapon_in_hand_still_ticks(self):
        """Before a loadout exists there is nothing to hand the bots."""
        found = match()
        played(found).advance(world(), 0.1, None)
        assert found.elapsed == pytest.approx(0.1)

    def test_the_bots_act(self):
        """They are the one thing in a tick that moves on its own."""
        found = match()
        made = played(found)
        where = np.array(found.combatant('bot1').position)
        for _ in range(20):
            made.advance(world(), 0.1, pistol())
        assert not np.allclose(where, found.combatant('bot1').position)

    def test_what_is_in_the_air_flies(self):
        found = match()
        made = played(found)
        kind = made.flight.table.by_key(projectiles.ROCKET)
        made.flight.launch(kind, origin=(0.0, 1.6, 0.0), direction=(1, 0, 0),
                           owner=game.PLAYER_ID)
        made.advance(world(), 0.1, pistol())
        assert float(made.flight.position[0][0]) > 1.0


class TestWhatTheMapLeftLyingAbout:

    def pickups(self):
        from twig_bb import items
        return items.Pickups([items.Pickup(
            kind=items.ItemKind(key='health', title='HEALTH', health=25),
            position=np.zeros(3))])

    def test_walking_over_one_takes_it_through_the_tick(self):
        found = match(bots_in=0)
        found.combatant(game.PLAYER_ID).player.health = 40
        made = played(found)
        made.pickups = self.pickups()
        made.advance(world(), 0.1, pistol())
        assert found.combatant(game.PLAYER_ID).health == 65

    def test_it_is_reported_to_the_overlay_with_everything_else(self):
        made = played(match())
        made.pickups = self.pickups()
        assert made.describe()['items'] == 1


class TestTheMapsHazards:

    def test_lava_bites_through_the_tick(self):
        found = match(bots_in=0)
        made = played(found, harm=liquids.LiquidHarm(liquids.LiquidVolumes([
            liquids.LiquidVolume(mins=np.array((-5.0, -1.0, -5.0)),
                                 maxs=np.array((5.0, 5.0, 5.0)),
                                 kind=liquids.LAVA)])))
        for _ in range(10):
            made.advance(world(), 0.1, pistol())
        assert found.combatant(game.PLAYER_ID).health < 100

    def test_the_floor_of_the_world_kills_through_the_tick(self):
        found = match(bots_in=0)
        found.combatant(game.PLAYER_ID).position = np.array([0.0, -500.0, 0.0])
        made = played(found, floor=falling.KillFloor(-100.0))
        made.advance(world(), 0.1, pistol())
        assert not found.combatant(game.PLAYER_ID).alive

    def test_a_map_with_neither_ticks_perfectly_well(self):
        found = match()
        played(found).advance(world(), 0.1, pistol())
        assert found.combatant(game.PLAYER_ID).health == 100


class TestComingBack:
    """A respawn the camera is never told about is undone on the next frame.

    Everything here is about *where* somebody comes back.  When is
    :class:`TestComingBackWhenYouSaySo`, and it differs between the player and
    a bot, so the one tested here is the bot.
    """

    def dead(self, **named):
        found = match(bots_in=1, **named)
        found.kill('bot1', cause='lava')
        return found

    def test_nobody_comes_back_before_their_time(self):
        found = self.dead()
        made = played(found)
        assert made.advance(world(), 0.1, pistol()).respawned == {}

    def test_they_come_back_when_the_wait_is_over(self):
        found = self.dead()
        made = played(found)
        made.advance(world(), arena.RESPAWN_DELAY + 0.1, pistol())
        assert found.combatant('bot1').alive

    def test_where_they_came_back_is_reported_as_the_feet(self):
        """How the arena addresses everybody; a camera adds the eye height."""
        found = self.dead()
        made = played(found, spawns=[(7.0, 1.0, 3.0)])
        tick = made.advance(world(), arena.RESPAWN_DELAY + 0.1, pistol())
        assert tick.respawned['bot1'] == pytest.approx([7.0, 1.0, 3.0])

    def test_the_body_is_put_where_it_was_reported(self):
        found = self.dead()
        made = played(found, spawns=[(7.0, 1.0, 3.0)])
        made.advance(world(), arena.RESPAWN_DELAY + 0.1, pistol())
        assert found.combatant('bot1').position \
            == pytest.approx([7.0, 1.0, 3.0])

    def test_a_bot_that_comes_back_forgets_what_it_was_doing(self):
        """Still hunting a target across the level is a bot walking into a wall."""
        found = match()
        made = played(found)
        made.minds['bot1'].target = game.PLAYER_ID
        made.minds['bot1'].watching = 5.0
        found.kill('bot1', cause='lava')
        made.advance(world(), arena.RESPAWN_DELAY + 0.1, pistol())
        assert made.minds['bot1'].target == ''

    def test_a_match_with_nowhere_to_go_still_brings_them_back(self):
        """A loaded map always has a spawn; a constructed match may not."""
        found = self.dead()
        made = played(found, spawns=[])
        made.advance(world(), arena.RESPAWN_DELAY + 0.1, pistol())
        assert found.combatant('bot1').alive


class TestPublishingWhereTheCameraIs:
    """The player is the one combatant the rules do not move."""

    def test_the_body_stands_under_the_camera(self):
        found = match(bots_in=0)
        assert played(found).publish(game.PLAYER_ID, (2.0, 5.6, -3.0)) is True
        assert found.combatant(game.PLAYER_ID).position \
            == pytest.approx([2.0, 5.6 - avatar.EYE_HEIGHT, -3.0])

    def test_a_camera_of_four_numbers_is_accepted(self):
        """A view platform's position may arrive homogeneous."""
        found = match(bots_in=0)
        played(found).publish(game.PLAYER_ID, (2.0, 5.6, -3.0, 1.0))
        assert found.combatant(game.PLAYER_ID).position \
            == pytest.approx([2.0, 5.6 - avatar.EYE_HEIGHT, -3.0])

    def test_nothing_is_published_for_the_dead(self):
        """A corpse is not where the camera is, and a respawn has just chosen
        a position that this would overwrite."""
        found = match(bots_in=0)
        found.kill(game.PLAYER_ID, cause='lava')
        where = np.array(found.combatant(game.PLAYER_ID).position)
        assert played(found).publish(game.PLAYER_ID, (9.0, 9.0, 9.0)) is False
        assert found.combatant(game.PLAYER_ID).position == pytest.approx(where)

    def test_publishing_for_nobody_is_harmless(self):
        assert played(match()).publish('nobody', (0.0, 0.0, 0.0)) is False


class TestWhatItReportsToTheOverlay:

    def test_it_counts_the_spawns_and_the_minds(self):
        found = match(bots_in=3)
        assert played(found, spawns=[(0, 0, 0), (1, 0, 0)]).describe() \
            == {'spawn points': 2, 'minds': 3}


class TestNothingHereReadsAClock:
    """The rule that makes a match replayable from its inputs."""

    def test_the_module_imports_no_clock(self):
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(rules))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or '')
        assert not imported & {'time', 'datetime'}

    def test_two_identical_matches_play_out_identically(self):
        def play():
            found = match(bots_in=2)
            made = played(found)
            for _ in range(50):
                made.advance(world(), 1.0 / 60.0, pistol())
            return [tuple(found.combatant(id).position)
                    for id in sorted(found.ids())]
        assert play() == play()


def test_a_bot_that_has_been_killed_is_not_thought_for():
    """`step_bots` skips the dead; this is the tick-level statement of it."""
    found = match()
    made = played(found)
    found.kill('bot1', cause='lava')
    made.advance(world(), 0.1, pistol())
    assert not found.combatant('bot1').alive


def test_the_minds_are_the_ones_the_match_was_built_with():
    found = match(bots_in=2)
    made = played(found)
    assert sorted(made.minds) == ['bot1', 'bot2']
    assert all(isinstance(mind, bots.Bot) for mind in made.minds.values())


class TestComingBackWhenYouSaySo:
    """A countdown that returns you while you are reading the scoreboard puts
    you back in a corridor you were not looking at.

    The timer becomes the *shortest* a death may be rather than the trigger
    for its end. Bots are exempt: nobody is waiting for them to press a key.
    """

    def dead(self):
        found = match(bots_in=1)
        found.kill(game.PLAYER_ID, cause='lava')
        return found

    def test_the_player_does_not_come_back_on_the_timer_alone(self):
        found = self.dead()
        made = played(found)
        made.advance(world(), arena.RESPAWN_DELAY * 3, pistol())
        assert not found.combatant(game.PLAYER_ID).alive

    def test_asking_brings_them_back(self):
        found = self.dead()
        made = played(found)
        made.advance(world(), arena.RESPAWN_DELAY + 0.1, pistol())
        assert made.ask_to_respawn(game.PLAYER_ID) is True
        made.advance(world(), 0.01, pistol())
        assert found.combatant(game.PLAYER_ID).alive

    def test_asking_early_is_remembered_rather_than_swallowed(self):
        """An input a game ignores without saying so is an input the player
        believes they did not make."""
        found = self.dead()
        made = played(found)
        made.ask_to_respawn(game.PLAYER_ID)
        made.advance(world(), arena.RESPAWN_DELAY + 0.1, pistol())
        assert found.combatant(game.PLAYER_ID).alive

    def test_asking_while_alive_is_not_a_request(self):
        found = match(bots_in=0)
        assert played(found).ask_to_respawn(game.PLAYER_ID) is False

    def test_asking_for_somebody_who_is_not_in_the_match(self):
        assert played(match()).ask_to_respawn('nobody') is False

    def test_one_ask_is_one_respawn(self):
        """Or a held trigger would bring you back the frame after every death."""
        found = self.dead()
        made = played(found)
        made.ask_to_respawn(game.PLAYER_ID)
        made.advance(world(), arena.RESPAWN_DELAY + 0.1, pistol())
        found.kill(game.PLAYER_ID, cause='lava')
        made.advance(world(), arena.RESPAWN_DELAY + 0.1, pistol())
        assert not found.combatant(game.PLAYER_ID).alive

    def test_a_bot_still_comes_back_on_the_timer(self):
        found = match(bots_in=1)
        found.kill('bot1', cause='lava')
        made = played(found)
        made.advance(world(), arena.RESPAWN_DELAY + 0.1, pistol())
        assert found.combatant('bot1').alive

    def test_it_can_say_whether_somebody_is_still_waiting(self):
        found = self.dead()
        made = played(found)
        assert made.waiting_to_come_back(game.PLAYER_ID)
        made.ask_to_respawn(game.PLAYER_ID)
        assert not made.waiting_to_come_back(game.PLAYER_ID)

    def test_the_living_are_not_waiting(self):
        assert not played(match()).waiting_to_come_back(game.PLAYER_ID)
