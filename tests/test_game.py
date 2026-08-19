"""Putting a match into a map, and driving it from a frame loop.

The wiring between the rules and the window.  It has a window at one end and is
tested with none, which is the point of it being its own module: what a frame
loop does each tick is a function of what it is given, so it can be given
something constructed.
"""

from __future__ import annotations

import random
from unittest import mock

import numpy as np
import pytest

from omi_physics import model
from omi_physics.character import CharacterCapabilities
from omi_physics.world import PhysicsWorld

from OpenGLContext.scenegraph.box import Box

from twig_bb import (arena, art, avatar, game, match as matchmod, walkers,
                        weapons)


class FakeSpawn:
    def __init__(self, position):
        self.position = np.asarray(position, dtype='d')


class FakeMap:
    def __init__(self, *positions):
        self._spawns = [FakeSpawn(one) for one in positions]

    def spawn_points(self):
        return self._spawns


def floor():
    world = PhysicsWorld(gravity=model.Gravity(gravity=9.81, direction=(0, -1, 0)))
    e = 60.0
    points = np.array([(-e, 0.0, -e), (e, 0.0, -e), (e, 0.0, e), (-e, 0.0, e)],
                      dtype='d')
    indices = np.array([(0, 1, 2), (0, 2, 3)], dtype='i')
    shape = world.add_shape(model.Shape.trimesh(points, indices))
    world.add_body(model.Motion(type=model.STATIC),
                   collider=model.Collider(shape=shape), position=(0, 0, 0))
    return world


def bodies(world):
    """Capsules for the bots: the player's proportions, at a bot's pace."""
    return walkers.Walkers(world, CharacterCapabilities(
        radius=avatar.RADIUS, standHeight=avatar.HEIGHT,
        crouchHeight=avatar.HEIGHT * 0.5, eyeHeight=avatar.EYE_HEIGHT,
        stepHeight=0.45, walkSpeed=game.BOT_SPEED))


def drive(world, found, minds, gun, times=30, dt=0.1, walking=None, **named):
    """Run the bots for a while, as a frame loop would."""
    walking = bodies(world) if walking is None else walking
    for _ in range(times):
        game.step_bots(world, found, minds, dt, gun, walking=walking, **named)
    return walking


def setup(**named):
    return matchmod.MatchSetup(**named)


def started(bots=2, spawns=((0, 0, 0), (10, 0, 0), (0, 0, 10)), **named):
    return game.start_match(FakeMap(*spawns), setup(bots=bots, **named),
                            weapons.default_table())


class TestStartingAMatch:

    def test_the_player_is_in_it(self):
        assert started().combatant(game.PLAYER_ID) is not None

    def test_the_setup_decides_how_many_bots(self):
        assert len(started(bots=3).bots()) == 3

    def test_no_bots_is_allowed(self):
        """Walking a level with nothing shooting at you is a real thing to want."""
        assert started(bots=0).bots() == []

    def test_the_bots_take_the_maps_difficulty(self):
        found = started(bots=1, difficulty='hard')
        assert found.bots()[0].difficulty == 'hard'

    def test_the_limits_come_from_the_setup(self):
        found = started(fragLimit=7, timeLimit=3.0)
        assert (found.fragLimit, found.timeLimit) == (7, 3.0)

    def test_the_player_takes_the_first_spawn(self):
        found = started(spawns=((1, 2, 3), (9, 9, 9)))
        assert np.allclose(found.combatant(game.PLAYER_ID).position,
                           avatar.feet_of((1, 2, 3)))

    def test_the_bots_take_the_others(self):
        found = started(bots=1, spawns=((1, 2, 3), (9, 9, 9)))
        assert np.allclose(found.bots()[0].position, avatar.feet_of((9, 9, 9)))

    def test_a_spawn_puts_the_feet_down_rather_than_the_origin(self):
        """A map's spawn entity does not mark the floor, and the arena
        addresses feet: a capsule sits on them and a shot at the legs meets
        them.  The correction is the *same one the camera's spawn goes
        through*; dropping by a different amount here is what put every bot a
        metre inside the floor."""
        found = started(bots=1, spawns=((0, 10, 0), (5, 10, 5)))
        assert float(found.bots()[0].position[1]) \
            == pytest.approx(10.0 - avatar.SPAWN_LIFT)

    def test_two_matches_on_one_level_do_not_open_identically(self):
        """The opening is the part of a fight a player replays most, and it
        was the part that never changed."""
        spawns = tuple((index * 10.0, 0.0, 0.0) for index in range(6))
        openings = {tuple(tuple(one.position)
                          for one in started(bots=2, spawns=spawns).bots())
                    for _ in range(30)}
        assert len(openings) > 1

    def test_a_bot_is_not_placed_on_top_of_the_player(self):
        """Variety among the good points, not variety for its own sake."""
        spawns = tuple((index * 10.0, 0.0, 0.0) for index in range(6))
        for _ in range(30):
            found = started(bots=1, spawns=spawns)
            gap = np.linalg.norm(found.bots()[0].position
                                 - found.combatant(game.PLAYER_ID).position)
            assert gap > 20.0

    def test_the_opening_replays_when_the_caller_says_so(self):
        spawns = tuple((index * 10.0, 0.0, 0.0) for index in range(6))

        def opening():
            found = game.start_match(FakeMap(*spawns), setup(bots=3),
                                     weapons.default_table(),
                                     chooser=random.Random(11))
            return [tuple(one.position) for one in found.bots()]
        assert opening() == opening()

    def test_more_fighters_than_spawns_wraps_rather_than_failing(self):
        """Common on a small level, and better than refusing to start."""
        found = started(bots=4, spawns=((0, 0, 0), (5, 0, 0)))
        assert len(found.bots()) == 4

    def test_a_map_with_no_spawns_still_starts(self):
        found = game.start_match(FakeMap(), setup(bots=1),
                                 weapons.default_table())
        assert found.combatant(game.PLAYER_ID) is not None

    def test_no_map_at_all_still_starts(self):
        """The menu can build a match before a level has been loaded."""
        assert game.start_match(None, setup(bots=1),
                                weapons.default_table()) is not None


class TestGivingThemMinds:

    def test_there_is_one_mind_per_bot(self):
        found = started(bots=3)
        assert sorted(game.place_bots(found)) == ['bot1', 'bot2', 'bot3']

    def test_the_player_gets_none(self):
        assert game.PLAYER_ID not in game.place_bots(started())

    def test_each_mind_takes_its_bots_difficulty(self):
        minds = game.place_bots(started(bots=1, difficulty='nightmare'))
        assert minds['bot1'].difficulty == 'nightmare'


class TestDrivingThem:

    def test_a_bot_moves(self):
        found = started(bots=1, spawns=((0, 0, 0), (20, 0, 0)))
        minds = game.place_bots(found, seed=1)
        before = found.bots()[0].position.copy()
        world, gun = floor(), weapons.default_table().by_key('rifle')
        drive(world, found, minds, gun)
        assert not np.allclose(found.bots()[0].position, before)

    def test_a_bot_shoots_the_player_eventually(self):
        # Both on the floor: the spawn correction drops the feet below the
        # entity origin, and a floor at y=0 would leave them under it.
        lift = avatar.SPAWN_LIFT
        found = started(bots=1, difficulty='nightmare',
                        spawns=((0, lift, 0), (12, lift, 0)))
        minds = game.place_bots(found, seed=2)
        minds['bot1'].facing = np.array([-1.0, 0.0, 0.0])
        world, gun = floor(), weapons.default_table().by_key('rifle')
        drive(world, found, minds, gun, times=40)
        assert found.combatant(game.PLAYER_ID).health < arena.STARTING_HEALTH

    def test_a_bot_firing_says_so_on_the_same_stream_as_the_player(self):
        """Half a fight that emits nothing is half a fight nobody can hear."""
        lift = avatar.SPAWN_LIFT
        found = started(bots=1, difficulty='nightmare',
                        spawns=((0, lift, 0), (12, lift, 0)))
        minds = game.place_bots(found, seed=2)
        minds['bot1'].facing = np.array([-1.0, 0.0, 0.0])
        world, gun = floor(), weapons.default_table().by_key('rifle')
        drive(world, found, minds, gun, times=40)
        shots = [event for event in found.drain()
                 if isinstance(event, arena.Fired)]
        assert shots and {event.shooter for event in shots} == {'bot1'}

    def test_the_maps_surfaces_reach_a_bots_shot(self):
        """So an impact from a bot names its material exactly as the player's does.

        Checked at the seam rather than by arranging a bot to miss into a
        wall: what is being asserted is that the wiring carries it, and a
        bot's aim is not the thing under test.
        """
        given = []
        lift = avatar.SPAWN_LIFT
        found = started(bots=1, difficulty='nightmare',
                        spawns=((0, lift, 0), (12, lift, 0)))
        minds = game.place_bots(found, seed=2)
        minds['bot1'].facing = np.array([-1.0, 0.0, 0.0])
        world, gun = floor(), weapons.default_table().by_key('rifle')
        surfaces = object()
        with mock.patch.object(game.combat, 'fire',
                               side_effect=lambda *a, **k: given.append(k) or []):
            drive(world, found, minds, gun, times=40, surfaces=surfaces)
        assert given and all(call['surfaces'] is surfaces for call in given)

    def test_a_dead_bot_is_not_driven(self):
        found = started(bots=1)
        found.damage('bot1', 500, by=game.PLAYER_ID)
        before = found.bots()[0].position.copy()
        drive(floor(), found, game.place_bots(found),
              weapons.default_table().by_key('rifle'), times=1)
        assert np.allclose(found.bots()[0].position, before)

    def test_a_bot_does_not_walk_through_a_wall(self):
        """Not sliding along it — only not passing through it."""
        world = floor()
        e = 40.0
        points = np.array([(2.0, -e, -e), (2.0, e, -e), (2.0, e, e), (2.0, -e, e)],
                          dtype='d')
        indices = np.array([(0, 1, 2), (0, 2, 3)], dtype='i')
        shape = world.add_shape(model.Shape.trimesh(points, indices))
        world.add_body(model.Motion(type=model.STATIC),
                       collider=model.Collider(shape=shape), position=(0, 0, 0))
        found = started(bots=1, spawns=((0, 0, 0), (10, 0, 0)))
        minds = game.place_bots(found, seed=3)
        minds['bot1'].facing = np.array([-1.0, 0.0, 0.0])
        gun = weapons.default_table().by_key('rifle')
        drive(world, found, minds, gun, times=80)
        assert float(found.bots()[0].position[0]) > 2.0


class TestTheBodiesThatAreDrawn:

    def test_there_is_a_body_per_bot(self):
        _group, bodies = game.bot_bodies(started(bots=3))
        assert sorted(bodies) == ['bot1', 'bot2', 'bot3']

    def test_the_player_has_none(self):
        """You do not see your own body from inside your own eyes."""
        _group, bodies = game.bot_bodies(started(bots=1))
        assert game.PLAYER_ID not in bodies

    def test_the_group_holds_them_all(self):
        group, _bodies = game.bot_bodies(started(bots=2))
        assert len(group.children) == 2

    def test_a_body_starts_where_its_bot_is(self):
        found = started(bots=1, spawns=((0, 0, 0), (4, 5, 6)))
        _group, bodies = game.bot_bodies(found)
        assert np.allclose(bodies['bot1'].translation,
                           found.bots()[0].position)

    def test_moving_a_bot_moves_its_body(self):
        found = started(bots=1)
        _group, bodies = game.bot_bodies(found)
        found.bots()[0].position = np.array([7.0, 0.0, 8.0])
        game.move_bodies(found, bodies)
        assert np.allclose(bodies['bot1'].translation, (7.0, 0.0, 8.0))

    def test_a_dead_bot_is_taken_out_of_sight(self):
        found = started(bots=1)
        _group, bodies = game.bot_bodies(found)
        found.damage('bot1', 500, by=game.PLAYER_ID)
        game.move_bodies(found, bodies)
        assert float(bodies['bot1'].translation[1]) < -100.0

    def test_a_respawned_bot_comes_back_into_sight(self):
        found = started(bots=1)
        _group, bodies = game.bot_bodies(found)
        found.damage('bot1', 500, by=game.PLAYER_ID)
        game.move_bodies(found, bodies)
        found.respawn('bot1', position=(3.0, 0.0, 3.0))
        game.move_bodies(found, bodies)
        assert np.allclose(bodies['bot1'].translation, (3.0, 0.0, 3.0))

    def test_a_body_nobody_is_behind_is_left_alone(self):
        _group, bodies = game.bot_bodies(started(bots=1))
        game.move_bodies(started(bots=0), bodies)


class TestWhatThePlayerIsTold:

    def test_a_frag_by_the_player_reads_in_the_first_person(self):
        found = started(bots=1)
        found.damage('bot1', 500, by=game.PLAYER_ID)
        assert game.messages(found.drain(), found) == ['You fragged Bot 1']

    def test_being_fragged_reads_in_the_second_person(self):
        found = started(bots=1)
        found.damage(game.PLAYER_ID, 500, by='bot1')
        assert game.messages(found.drain(), found) == ['Bot 1 fragged you']

    def test_one_bot_fragging_another_names_both(self):
        found = started(bots=2)
        found.damage('bot2', 500, by='bot1')
        assert game.messages(found.drain(), found) == ['Bot 1 fragged Bot 2']

    def test_dying_to_the_world_names_nobody(self):
        found = started(bots=1)
        found.damage('bot1', 500, by='')
        assert game.messages(found.drain(), found) == ['Bot 1 died']

    def test_a_hit_is_not_a_message(self):
        """A line per bullet is a wall of text over the middle of a fight."""
        found = started(bots=1)
        found.damage('bot1', 5, by=game.PLAYER_ID)
        assert game.messages(found.drain(), found) == []

    def test_the_end_of_the_match_is_announced(self):
        found = started(bots=1, fragLimit=1)
        found.damage('bot1', 500, by=game.PLAYER_ID)
        lines = game.messages(found.drain(), found)
        assert any('MATCH OVER' in line for line in lines)


class TestTheScoreboard:

    def test_it_has_a_line_per_fighter_plus_a_heading(self):
        assert len(game.scoreboard_lines(started(bots=2))) == 4

    def test_the_leader_is_first(self):
        found = started(bots=2)
        found.damage('bot2', 500, by='bot1')
        assert 'Bot 1' in game.scoreboard_lines(found)[1]

    def test_it_shows_frags_and_deaths(self):
        heading = game.scoreboard_lines(started())[0]
        assert 'FRAGS' in heading and 'DEATHS' in heading


class TestWhereToComeBack:
    """Everybody respawning on the same square is not a spawn choice at all.

    The viewer asked for a *fixed* spawn index every time, so each death put
    the whole match back on one spot — players and bots standing inside one
    another, shot before the screen had settled.  A respawn wants the point
    that is furthest from the people already in the level, which is the whole
    reason a map ships a dozen of them.
    """

    def spawns(self):
        return [np.array([0.0, 0.0, 0.0]), np.array([10.0, 0.0, 0.0]),
                np.array([50.0, 0.0, 0.0])]

    def test_it_picks_the_point_furthest_from_everybody(self):
        match = arena.Arena(weapons=weapons.default_table(), fragLimit=1,
                            timeLimit=1.0)
        match.add('a', position=np.array([0.0, 0.0, 0.0]))
        match.add('b', position=np.array([11.0, 0.0, 0.0]))
        chosen = game.spawn_for(self.spawns(), match, 'c')
        assert np.allclose(chosen, [50.0, 0.0, 0.0])

    def test_the_one_coming_back_does_not_repel_itself(self):
        """Otherwise a lone player is pushed away from where they just died,
        which is right, and a lone player in an empty match has nowhere to be
        pushed away *from* — and must still get a spawn."""
        match = arena.Arena(weapons=weapons.default_table(), fragLimit=1,
                            timeLimit=1.0)
        match.add('a', position=np.array([50.0, 0.0, 0.0]))
        chosen = game.spawn_for(self.spawns(), match, 'a')
        assert chosen is not None

    def test_the_dead_do_not_crowd_a_spawn(self):
        """A corpse is not standing there; only the living take up room.

        A dead body lying on the far spawn must not push the next arrival away
        from it -- there is nobody there to arrive on top of.
        """
        match = arena.Arena(weapons=weapons.default_table(), fragLimit=1,
                            timeLimit=1.0)
        match.add('a', position=np.array([0.0, 0.0, 0.0]))
        match.add('b', position=np.array([50.0, 0.0, 0.0]))
        match.damage('b', 1000.0, by='a')
        assert np.allclose(game.spawn_for(self.spawns(), match, 'c'),
                           [50.0, 0.0, 0.0])

    def test_an_empty_match_still_gets_a_spawn(self):
        match = arena.Arena(weapons=weapons.default_table(), fragLimit=1,
                            timeLimit=1.0)
        assert game.spawn_for(self.spawns(), match, 'c') is not None

    def test_a_map_with_no_spawns_is_not_an_error(self):
        match = arena.Arena(weapons=weapons.default_table(), fragLimit=1,
                            timeLimit=1.0)
        assert game.spawn_for([], match, 'c') is None

    def test_two_respawns_running_do_not_both_go_to_one_point(self):
        """The case that was reported: everyone piling onto one square."""
        match = arena.Arena(weapons=weapons.default_table(), fragLimit=1,
                            timeLimit=1.0)
        match.add('a', position=np.array([0.0, 0.0, 0.0]))
        first = game.spawn_for(self.spawns(), match, 'b')
        match.add('b', position=first)
        second = game.spawn_for(self.spawns(), match, 'c')
        assert not np.allclose(first, second)


class TestSpawningSomewhereYouCannotPredict:
    """Furthest-from-everybody is *one* answer, and always the same one.

    A player who stands still can wait at the far end of the level and shoot
    each arrival as it appears, which is what was reported: bots turning up in
    the same place doing the same thing.  A respawn wants variety among the
    points that are safe rather than the single safest.
    """

    def spawns(self, count=6):
        return [np.array([index * 10.0, 0.0, 0.0]) for index in range(count)]

    def match(self, *positions):
        made = arena.Arena(weapons=weapons.default_table(), fragLimit=1,
                           timeLimit=1.0)
        for index, where in enumerate(positions):
            made.add('other%d' % index, position=np.asarray(where, dtype='d'))
        return made

    def chosen(self, times=40, **named):
        found = self.match((0.0, 0.0, 0.0))
        picker = random.Random(7)
        return {tuple(game.spawn_for(self.spawns(), found, 'me',
                                     chooser=picker, **named))
                for _ in range(times)}

    def test_a_stationary_player_does_not_see_the_same_square_every_time(self):
        assert len(self.chosen()) > 1

    def test_it_is_still_the_far_end_of_the_level(self):
        """Variety among the *good* points, not variety for its own sake: a
        spawn beside the person who just killed you is not a spawn."""
        near = {tuple(one) for one in self.spawns()[:2]}
        assert not (self.chosen() & near)

    def test_how_much_variety_is_declared_rather_than_hidden(self):
        assert 0.0 < game.SPAWN_SPREAD <= 1.0

    def test_all_of_them_at_once_is_a_choice_the_constant_can_make(self):
        """A variant that wants the old behaviour sets one number."""
        assert len(self.chosen(spread=1.0)) == 1

    def test_the_choice_is_the_callers_so_a_match_replays(self):
        one = game.spawn_for(self.spawns(), self.match((0.0, 0.0, 0.0)), 'me',
                             chooser=random.Random(3))
        two = game.spawn_for(self.spawns(), self.match((0.0, 0.0, 0.0)), 'me',
                             chooser=random.Random(3))
        assert np.allclose(one, two)

    def test_an_empty_match_is_spread_over_the_whole_level(self):
        """Nobody to be far from means every point is as good as every other."""
        picker = random.Random(5)
        found = self.match()
        assert len({tuple(game.spawn_for(self.spawns(), found, 'me',
                                         chooser=picker))
                    for _ in range(40)}) > 1


class TestDrawingWhatTheMapPlaced:
    """A map places fifty of these on average, so they are made once."""

    def pickups(self, count=2, colour=(1.0, 0.0, 0.0), key='test', **named):
        from twig_bb import items
        kind = items.ItemKind(key=key, title='TEST', health=25,
                              colour=colour, **named)
        return items.Pickups([
            items.Pickup(kind=kind,
                         position=np.array([index * 4.0, 1.0, 0.0]))
            for index in range(count)])

    def test_there_is_a_body_per_pickup(self):
        _group, bodies = game.item_bodies(self.pickups(3))
        assert len(bodies) == 3

    def test_they_are_all_in_one_group(self):
        group, bodies = game.item_bodies(self.pickups(2))
        assert list(group.children) == bodies

    def test_a_body_stands_where_its_pickup_is(self):
        _group, bodies = game.item_bodies(self.pickups(1))
        assert tuple(bodies[0].translation) == (0.0, 1.0, 0.0)

    def test_it_is_drawn_in_its_kinds_own_colour(self):
        _group, bodies = game.item_bodies(self.pickups(1, colour=(0.2, 0.9, 0.4)))
        material = bodies[0].children[0].appearance.material
        assert tuple(material.diffuseColor) == pytest.approx((0.2, 0.9, 0.4))

    def test_a_level_with_none_is_an_empty_group(self):
        group, bodies = game.item_bodies(None)
        assert list(group.children) == [] and bodies == []

    def test_one_that_has_been_taken_is_parked_out_of_sight(self):
        where = self.pickups(2)
        _group, bodies = game.item_bodies(where)
        where.items[0].waiting = 10.0
        game.move_items(where, bodies, now=0.0)
        assert tuple(bodies[0].translation) == game.OFFSTAGE
        assert tuple(bodies[1].translation) != game.OFFSTAGE

    def test_one_that_has_come_back_is_put_back(self):
        where = self.pickups(1)
        _group, bodies = game.item_bodies(where)
        where.items[0].waiting = 10.0
        game.move_items(where, bodies, now=0.0)
        where.items[0].waiting = None
        game.move_items(where, bodies, now=0.0)
        assert tuple(bodies[0].translation) == (0.0, 1.0, 0.0)

    def test_they_turn_so_they_can_be_seen_across_a_room(self):
        where = self.pickups(1)
        _group, bodies = game.item_bodies(where)
        game.move_items(where, bodies, now=0.0)
        first = tuple(bodies[0].rotation)
        game.move_items(where, bodies, now=0.5)
        assert tuple(bodies[0].rotation) != first

    def test_moving_a_level_with_none_is_harmless(self):
        game.move_items(None, [], now=0.0)


class TestDrawingAPickupAsItsModel:
    """A kind that names a model is drawn as one; anything else is a box."""

    def kind(self, **named):
        from twig_bb import items
        named.setdefault('key', 'test')
        named.setdefault('colour', (0.2, 0.55, 0.95))
        return items.ItemKind(title='TEST', health=25, **named)

    def medikit(self, **named):
        from twig_bb import items
        return self.kind(**dict(items.MEDPACK, **named))

    def test_a_kind_with_no_model_is_still_a_box(self):
        look = game.item_look(self.kind())
        assert isinstance(look.geometry, Box)

    def test_a_model_that_will_not_load_falls_back_to_the_box(self):
        look = game.item_look(self.kind(model='items/no-such-model.glb'))
        assert isinstance(look.geometry, Box)

    def test_a_kind_with_a_model_is_drawn_as_it(self):
        look = game.item_look(self.medikit())
        assert not isinstance(getattr(look, 'geometry', None), Box)
        assert list(art.shapes(look))

    def test_the_model_is_scaled_out_of_its_own_units(self):
        look = game.item_look(self.medikit(modelScale=0.5))
        assert tuple(look.scale) == pytest.approx((0.5, 0.5, 0.5))

    def test_its_middle_is_put_on_the_pickups_middle(self):
        """``modelOffset`` is in the model's units, so the scale applies to it."""
        look = game.item_look(self.medikit(modelScale=0.5,
                                           modelOffset=(0.0, -1.0, 0.0)))
        assert tuple(look.translation) == pytest.approx((0.0, -0.5, 0.0))

    def test_it_is_painted_in_the_kinds_colour(self):
        look = game.item_look(self.medikit(colour=(0.2, 0.55, 0.95)))
        for shape in art.shapes(look):
            assert tuple(shape.appearance.material.baseColor) == pytest.approx(
                (0.2, 0.55, 0.95))

    def test_it_carries_its_own_light_into_an_unlit_corner(self):
        look = game.item_look(self.medikit(colour=(0.2, 0.55, 0.95)))
        for shape in art.shapes(look):
            assert max(shape.appearance.material.emissiveColor) > 0.0

    def test_art_that_came_coloured_keeps_its_colours(self):
        """A launcher in a red bubble is a launcher, not a red launcher."""
        from twig_bb import items
        look = game.item_look(self.kind(colour=(0.9, 0.2, 0.15),
                                        **dict(items.LAUNCHER_PICKUP)))
        painted = {tuple(round(float(value), 3)
                         for value in shape.appearance.material.baseColor)
                   for shape in art.shapes(look)}
        assert len(painted) > 1, 'the whole model was painted one colour'

    def test_but_it_still_carries_its_own_light(self):
        """Unlit maps: art that is not repainted still may not be a silhouette."""
        from twig_bb import items
        look = game.item_look(self.kind(colour=(0.9, 0.2, 0.15),
                                        **dict(items.LAUNCHER_PICKUP)))
        assert any(max(shape.appearance.material.emissiveColor) > 0.0
                   for shape in art.shapes(look))

    def test_a_kind_that_asks_to_be_tinted_still_is(self):
        look = game.item_look(self.medikit(colour=(0.2, 0.55, 0.95)))
        for shape in art.shapes(look):
            assert tuple(shape.appearance.material.baseColor) == pytest.approx(
                (0.2, 0.55, 0.95))

    def test_one_kind_is_one_subtree_however_many_a_map_places(self):
        """Fifty pickups a map, several of a kind; one medikit, not eight."""
        from twig_bb import items
        kind = self.medikit()
        where = items.Pickups([
            items.Pickup(kind=kind, position=np.array([index * 4.0, 1.0, 0.0]))
            for index in range(4)])
        _group, bodies = game.item_bodies(where)
        assert len({id(body.children[0]) for body in bodies}) == 1

    def test_two_kinds_are_two_subtrees_so_they_can_differ_in_colour(self):
        from twig_bb import items
        where = items.Pickups([
            items.Pickup(kind=self.medikit(key='a', colour=(1.0, 0.0, 0.0)),
                         position=np.array([0.0, 1.0, 0.0])),
            items.Pickup(kind=self.medikit(key='b', colour=(0.0, 0.0, 1.0)),
                         position=np.array([4.0, 1.0, 0.0]))])
        _group, bodies = game.item_bodies(where)
        painted = [tuple(next(art.shapes(body.children[0]))
                         .appearance.material.baseColor)
                   for body in bodies]
        assert painted[0] == pytest.approx((1.0, 0.0, 0.0))
        assert painted[1] == pytest.approx((0.0, 0.0, 1.0))


class TestWhatABurstDoesToSomebodyStandingOnIt:
    """A rocket landing at somebody's feet, over a floor that is really there.

    The rest of the burst rules are tested against open space, which is the one
    place a rocket never goes off: every shot that is not a direct hit ends on
    a surface, and a burst centred *on* geometry has to be able to see out of
    it.  Fired rather than placed, so the point the rules are handed is the
    point flying produces.
    """

    def fire(self, at, standing, aim=None):
        from twig_bb import projectiles
        world = floor()
        found = arena.Arena(weapons=weapons.default_table(), fragLimit=15,
                            timeLimit=10.0)
        found.add(game.PLAYER_ID, position=(0.0, 0.0, 0.0), name='You')
        found.add('bot0', position=standing, bot=True, name='Bot')
        flight = projectiles.Projectiles(projectiles.default_table())
        eye = np.array([0.0, avatar.EYE_HEIGHT, 0.0])
        flight.launch(flight.table.by_key(projectiles.ROCKET), origin=eye,
                      direction=np.asarray(at, dtype='d') - eye,
                      owner=game.PLAYER_ID)
        for _ in range(300):
            if game.step_projectiles(world, found, flight, 1.0 / 60.0):
                break
        return found

    def test_it_hurts_them(self):
        found = self.fire(at=(2.0, 0.0, 0.0), standing=(2.0, 0.0, 1.2))
        assert found.combatant('bot0').health < arena.STARTING_HEALTH

    def test_it_throws_them(self):
        found = self.fire(at=(2.0, 0.0, 0.0), standing=(2.0, 0.0, 1.2))
        assert float(np.linalg.norm(found.combatant('bot0').push)) > 0.0

    def test_one_at_your_own_feet_throws_you_up(self):
        """A rocket jump: the whole of why this genre has a rocket launcher."""
        found = self.fire(at=(1.0, 0.0, 0.0), standing=(30.0, 0.0, 0.0))
        push = found.combatant(game.PLAYER_ID).push
        assert float(push[1]) > 0.0

    def test_and_costs_you_for_it(self):
        found = self.fire(at=(1.0, 0.0, 0.0), standing=(30.0, 0.0, 0.0))
        assert found.combatant(game.PLAYER_ID).health < arena.STARTING_HEALTH


class TestDrawingWhatIsInFlight:
    """A body per slot, parked out of sight when nothing is using it.

    A scenegraph edited every time a rocket is fired is a scenegraph rebuilt
    at the rate somebody holds the trigger down, and everything the render
    pass had gathered goes with it.
    """

    def flight(self, count=0):
        from twig_bb import projectiles
        table = projectiles.default_table()
        made = projectiles.Projectiles(table, capacity=4)
        for index in range(count):
            made.launch(table.by_key(projectiles.ROCKET),
                        origin=(float(index), 1.0, 0.0), direction=(1, 0, 0),
                        owner='player')
        return made

    def test_there_is_one_body_per_slot_of_each_kind(self):
        from twig_bb import projectiles
        group, bodies = game.projectile_bodies(4)
        assert all(len(row) == 4 for row in bodies.values())
        assert len(group.children) == 4 * len(bodies)
        assert projectiles.ROCKET in bodies

    def test_an_unused_body_is_out_of_sight(self):
        from twig_bb import projectiles
        _group, bodies = game.projectile_bodies(2)
        game.move_projectiles(self.flight(), bodies)
        assert tuple(bodies[projectiles.ROCKET][0].translation) == game.OFFSTAGE

    def test_a_flying_projectile_is_drawn_where_it_is(self):
        from twig_bb import projectiles
        _group, bodies = game.projectile_bodies(4)
        flight = self.flight(2)
        game.move_projectiles(flight, bodies)
        rockets = bodies[projectiles.ROCKET]
        assert tuple(rockets[0].translation) == pytest.approx((0.0, 1.0, 0.0))
        assert tuple(rockets[1].translation) == pytest.approx((1.0, 1.0, 0.0))
        assert tuple(rockets[2].translation) == game.OFFSTAGE

    def test_each_kind_of_projectile_gets_its_own_shape(self):
        """A grenade is not a rocket, and neither is a ball."""
        from twig_bb import projectiles
        _group, bodies = game.projectile_bodies(2)
        assert set(bodies) == {projectiles.ROCKET, projectiles.GRENADE}

    def test_a_grenade_in_the_air_is_drawn_as_a_grenade(self):
        from twig_bb import projectiles
        table = projectiles.default_table()
        flight = projectiles.Projectiles(table, capacity=4)
        flight.launch(table.by_key(projectiles.GRENADE), origin=(3, 1, 0),
                      direction=(1, 0, 0), owner='player')
        _group, bodies = game.projectile_bodies(4)
        game.move_projectiles(flight, bodies)
        assert tuple(bodies[projectiles.GRENADE][0].translation) \
            == pytest.approx((3.0, 1.0, 0.0))
        assert all(tuple(body.translation) == game.OFFSTAGE
                   for body in bodies[projectiles.ROCKET])

    def test_two_kinds_at_once_each_go_to_their_own_bodies(self):
        from twig_bb import projectiles
        table = projectiles.default_table()
        flight = projectiles.Projectiles(table, capacity=4)
        flight.launch(table.by_key(projectiles.ROCKET), origin=(1, 0, 0),
                      direction=(1, 0, 0), owner='player')
        flight.launch(table.by_key(projectiles.GRENADE), origin=(2, 0, 0),
                      direction=(1, 0, 0), owner='player')
        _group, bodies = game.projectile_bodies(4)
        game.move_projectiles(flight, bodies)
        assert tuple(bodies[projectiles.ROCKET][0].translation)[0] == pytest.approx(1.0)
        assert tuple(bodies[projectiles.GRENADE][0].translation)[0] == pytest.approx(2.0)

    def test_they_all_share_one_body_so_the_pass_can_batch_them(self):
        """Two hundred rockets are two hundred matrices, not two hundred models.

        The pass batches on the identity of the geometry, so every slot has to
        be handed the *same* subtree rather than its own copy of one.
        """
        from twig_bb import projectiles
        _group, bodies = game.projectile_bodies(3)
        held = {id(body.children[0]) for body in bodies[projectiles.ROCKET]}
        assert len(held) == 1

    def test_a_projectile_is_drawn_as_a_rocket(self):
        from twig_bb import projectiles
        _group, bodies = game.projectile_bodies(1)
        assert list(art.shapes(bodies[projectiles.ROCKET][0])), \
            'the rocket model brought no shapes'

    def test_a_missing_model_still_leaves_something_to_see(self):
        """Art that will not load is not a reason for an invisible rocket."""
        from twig_bb import projectiles
        table = projectiles.ProjectileTable(kinds=[
            projectiles.Projectile(key='ghost', model='weapons/absent.glb')])
        _group, bodies = game.projectile_bodies(2, table=table)
        assert len(bodies['ghost']) == 2
        assert list(art.shapes(bodies['ghost'][0]))

    def test_no_batch_at_all_parks_everything(self):
        _group, bodies = game.projectile_bodies(2)
        game.move_projectiles(None, bodies)
        assert all(tuple(body.translation) == game.OFFSTAGE
                   for row in bodies.values() for body in row)


class TestPointingARocketWhereItIsGoing:
    """A rocket is a shape with a nose, so which way it lies is visible.

    The model is authored along -Z, which is the way glTF calls forward and the
    way the view looks; turning it is therefore a rotation from there onto
    wherever the projectile is actually headed.
    """

    def turned(self, direction):
        """Where the model's nose ends up once ``direction`` has turned it."""
        axis = np.asarray(game.heading_rotation(direction)[:3], dtype=float)
        angle = game.heading_rotation(direction)[3]
        nose = np.asarray(game.MODEL_FORWARD, dtype=float)
        length = np.linalg.norm(axis)
        if length == 0.0:
            return nose
        axis = axis / length
        # Rodrigues, so the test does not lean on the same maths as the code.
        return (nose * np.cos(angle)
                + np.cross(axis, nose) * np.sin(angle)
                + axis * np.dot(axis, nose) * (1.0 - np.cos(angle)))

    def test_the_nose_ends_up_pointing_along_the_flight(self):
        for direction in ((1, 0, 0), (0, 0, 1), (0, 1, 0), (-1, 0, 0),
                          (0.3, 0.5, -0.8)):
            wanted = np.asarray(direction, dtype=float)
            wanted = wanted / np.linalg.norm(wanted)
            assert np.allclose(self.turned(direction), wanted, atol=1e-6), direction

    def test_flying_straight_backwards_turns_right_around(self):
        """The one direction with no unique axis to turn about."""
        assert np.allclose(self.turned((0, 0, 1)), (0, 0, 1), atol=1e-6)

    def test_going_nowhere_is_left_alone(self):
        assert game.heading_rotation((0.0, 0.0, 0.0))[3] == 0.0

    def test_a_flying_projectile_is_turned_to_face_its_flight(self):
        from twig_bb import projectiles
        table = projectiles.default_table()
        flight = projectiles.Projectiles(table, capacity=2)
        flight.launch(table.by_key(projectiles.ROCKET), origin=(0, 1, 0),
                      direction=(1, 0, 0), owner='player')
        _group, bodies = game.projectile_bodies(2)
        game.move_projectiles(flight, bodies)
        assert tuple(bodies[projectiles.ROCKET][0].rotation) == pytest.approx(
            game.heading_rotation((1, 0, 0)))


class TestSayingHowSomebodyDied:
    """A map's own hazards read better named than as a bare "died"."""

    def match(self):
        found = arena.Arena(weapons=weapons.default_table())
        found.add(game.PLAYER_ID, name='You')
        found.add('bot1', bot=True, name='Bot 1')
        return found

    def line(self, **named):
        found = self.match()
        return game.messages([arena.Death(**named)], found)[0]

    def test_lava_is_named(self):
        assert 'lava' in self.line(target=game.PLAYER_ID, by='', cause='lava')

    def test_slime_is_named(self):
        assert 'slime' in self.line(target=game.PLAYER_ID, by='', cause='slime')

    def test_falling_out_of_the_world_is_named(self):
        """The one death a player has no other way of understanding."""
        from twig_bb import falling
        assert 'fell' in self.line(target=game.PLAYER_ID, by='',
                                   cause=falling.FELL)

    def test_a_cause_nobody_has_phrased_still_reads(self):
        assert self.line(target='bot1', by='', cause='quicksand') \
            == 'Bot 1 died'

    def test_a_frag_still_names_the_killer(self):
        assert self.line(target='bot1', by=game.PLAYER_ID) == 'You fragged Bot 1'


class TestBodiesDrawnAsFigures:
    """A bot drawn as a character rather than as a capsule.

    The cast is what puts a figure under each body transform; without one the
    capsule is still what a bot is drawn as, which is what keeps §6 developable
    with no art at all.
    """

    def test_without_a_cast_a_bot_is_a_capsule(self):
        _group, bodies = game.bot_bodies(started(bots=1))
        assert len(bodies['bot1'].children) == len(game.capsule())

    def test_with_a_cast_a_bot_is_its_figure(self):
        from twig_bb import characters
        found = started(bots=1)
        cast = characters.Cast([one.id for one in found.bots()])
        _group, bodies = game.bot_bodies(found, cast=cast)
        assert list(bodies['bot1'].children) == [cast.subtree('bot1')]

    def test_a_cast_with_no_figure_falls_back_to_the_capsule(self):
        from twig_bb import characters
        found = started(bots=1)
        cast = characters.Cast([one.id for one in found.bots()],
                               builds=['nobody-by-that-name'])
        _group, bodies = game.bot_bodies(found, cast=cast)
        assert len(bodies['bot1'].children) == len(game.capsule())

    def test_moving_them_plays_a_clip_and_turns_them(self):
        from twig_bb import characters
        found = started(bots=1)
        cast = characters.Cast([one.id for one in found.bots()])
        _group, bodies = game.bot_bodies(found, cast=cast)

        class Walker:
            velocity = (6.0, 0.0, 0.0)
            grounded = True

        class Walking:
            def of(self, id):
                return Walker()

        game.move_bodies(found, bodies, cast=cast, walking=Walking(), dt=0.1)
        assert tuple(bodies['bot1'].rotation) != (0.0, 1.0, 0.0, 0.0)

    def test_a_dead_bot_keeps_its_body_where_it_fell(self):
        from twig_bb import characters
        found = started(bots=1)
        cast = characters.Cast([one.id for one in found.bots()])
        _group, bodies = game.bot_bodies(found, cast=cast)
        one = found.combatant('bot1')
        one.player.health = 0
        one.dead_for = 0.0
        placed = tuple(bodies['bot1'].translation)
        game.move_bodies(found, bodies, cast=cast, dt=0.1)
        assert tuple(bodies['bot1'].translation) == placed

    def test_without_a_cast_a_dead_bot_is_taken_out_of_sight(self):
        found = started(bots=1)
        _group, bodies = game.bot_bodies(found)
        one = found.combatant('bot1')
        one.player.health = 0
        one.dead_for = 0.0
        game.move_bodies(found, bodies)
        assert float(bodies['bot1'].translation[1]) < -100.0


class TestWhatABodyIsSeenDoing:
    """The state the drawing reads, and where the rules keep it.

    A figure plays what `twig_bb.characters` decides, and that decision is only
    as good as what it is told. Every one of these is a thing a player watches
    for and none of them was reaching the figure: the weapon in somebody's
    hands, the direction they are pointing it, and the moment they pull the
    trigger.
    """

    def _armed(self, weapon='rifle'):
        from twig_bb import characters
        found = started(bots=1)
        one = found.combatant('bot1')
        one.player.give(weapon)
        one.player.selected = weapon
        cast = characters.Cast([one.id for one in found.bots()])
        _group, bodies = game.bot_bodies(found, cast=cast)
        return found, cast, bodies

    def test_the_motion_carries_the_selected_weapon(self):
        found, cast, bodies = self._armed()
        seen = {}

        class Watching:
            def update(self, id, motion, dt):
                seen['motion'] = motion
                return ('idle', None)

            def subtree(self, id):
                return None

        game.move_bodies(found, bodies, cast=Watching(), dt=0.1)
        assert seen['motion'].weapon == 'rifle'

    def test_a_body_turns_to_where_it_is_looking(self):
        """Somebody standing still and shooting at you faces you."""
        found, cast, bodies = self._armed()
        one = found.combatant('bot1')
        one.facing = np.array([1.0, 0.0, 0.0])
        game.move_bodies(found, bodies, cast=cast, dt=0.1)
        turned = tuple(bodies['bot1'].rotation)
        one.facing = np.array([0.0, 0.0, 1.0])
        game.move_bodies(found, bodies, cast=cast, dt=0.1)
        assert tuple(bodies['bot1'].rotation) != turned

    def test_looking_beats_moving_for_which_way_a_body_faces(self):
        """A figure strafing across you keeps its front towards you."""
        found, cast, bodies = self._armed()
        one = found.combatant('bot1')
        one.facing = np.array([0.0, 0.0, -1.0])

        class Walker:
            velocity = (6.0, 0.0, 0.0)
            grounded = True

        class Walking:
            def of(self, id):
                return Walker()

        game.move_bodies(found, bodies, cast=cast, walking=Walking(), dt=0.1)
        facing = game.heading_rotation((0.0, 0.0, -1.0),
                                       forward=game.charactersmod.FORWARD)
        assert np.allclose(bodies['bot1'].rotation, facing)

    def test_a_body_with_nothing_in_view_faces_the_way_it_walks(self):
        found, cast, bodies = self._armed()

        class Walker:
            velocity = (6.0, 0.0, 0.0)
            grounded = True

        class Walking:
            def of(self, id):
                return Walker()

        game.move_bodies(found, bodies, cast=cast, walking=Walking(), dt=0.1)
        heading = game.heading_rotation((1.0, 0.0, 0.0),
                                        forward=game.charactersmod.FORWARD)
        assert np.allclose(bodies['bot1'].rotation, heading)

    def test_pulling_the_trigger_reaches_the_figure(self):
        found, cast, bodies = self._armed()
        seen = {}

        class Watching:
            def update(self, id, motion, dt):
                seen['motion'] = motion
                return ('idle', None)

            def subtree(self, id):
                return None

        found.combatant('bot1').firing = 0.2
        game.move_bodies(found, bodies, cast=Watching(), dt=0.05)
        assert seen['motion'].firing

    def test_the_trigger_is_only_down_for_as_long_as_the_shot(self):
        found, cast, bodies = self._armed()
        one = found.combatant('bot1')
        one.firing = 0.05
        game.move_bodies(found, bodies, cast=cast, dt=0.1)
        assert one.firing <= 0.0
