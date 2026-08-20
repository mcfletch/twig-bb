"""Everything a match does at random comes from the session's own entropy.

A session recording is worth what it can be *run again*
(:mod:`OpenGLContext.telemetry`), and the same keys pressed against a different
sequence of random numbers give a different game: a bot that looked the other
way, a shotgun pattern that missed, a respawn at the other end of the map.  So
nothing in this game draws from nowhere in particular.  Every stream comes from
:mod:`OpenGLContext.entropy`, which owns one seed per session, records it, and
puts it back when the session is replayed.

The rule these hold: an explicit ``seed`` still means exactly what it says --
that is what a test pins a shot with -- and ``None`` means *the session's
stream* rather than the system's entropy.
"""

from __future__ import annotations

import numpy as np
import pytest

from omi_physics import model
from omi_physics.world import PhysicsWorld

from OpenGLContext import entropy

from twig_bb import arena, bots, combat, game, projectiles, rules, weapons


@pytest.fixture(autouse=True)
def forget_the_session_seed():
    """Leave the next test to choose its own randomness."""
    yield
    entropy.forget()


def world():
    return PhysicsWorld(gravity=model.Gravity(gravity=9.81, direction=(0, -1, 0)))


def wall(w, x=5.0):
    edge = 20.0
    points = np.array([(x, -edge, -edge), (x, edge, -edge),
                       (x, edge, edge), (x, -edge, edge)], dtype='d')
    indices = np.array([(0, 1, 2), (0, 2, 3)], dtype='i')
    shape = w.add_shape(model.Shape.trimesh(points, indices))
    return w.add_body(model.Motion(type=model.STATIC),
                      collider=model.Collider(shape=shape), position=(0, 0, 0))


def match(bot_count=1):
    made = arena.Arena(weapons=weapons.default_table())
    made.add(game.PLAYER_ID, position=(0.0, 0.0, 0.0), name='You')
    for index in range(bot_count):
        made.add('bot%d' % index, position=(0.0, 0.0, 100.0 + index),
                 bot=True, name='Bot %d' % index)
    return made


def shots(count=2, spread=8.0):
    """Where ``count`` shots from one weapon land on a wall in front."""
    where = []
    made = world()
    wall(made)
    for _each in range(count):
        hits = combat.fire(made, match(bot_count=0), game.PLAYER_ID,
                           weapons.default_table().by_key('rifle'),
                           origin=(0.0, 0.0, 0.0), direction=(1.0, 0.0, 0.0),
                           spread=spread)
        where.append([tuple(hit.point) for hit in hits])
    return where


class TestWhereAShotScatters:
    def test_two_shots_from_one_weapon_do_not_land_in_the_same_place(self):
        """A cone of fire whose every shot took the same path is a cone in
        name only: the reticule opens and nothing behind it moves."""
        first, second = shots()
        assert first != second

    def test_a_session_started_from_one_seed_scatters_them_the_same_way(self):
        entropy.reseed(4242)
        first = shots()
        entropy.forget()
        entropy.reseed(4242)
        assert shots() == first

    def test_a_shot_given_a_seed_of_its_own_still_answers_to_it(self):
        """What a test pins one shot with."""
        made = world()
        wall(made)

        def once():
            return [tuple(hit.point) for hit in combat.fire(
                made, match(bot_count=0), game.PLAYER_ID,
                weapons.default_table().by_key('rifle'),
                origin=(0.0, 0.0, 0.0), direction=(1.0, 0.0, 0.0),
                spread=8.0, seed=7)]

        assert once() == once()


class TestHowTheOpponentsStart:
    def test_a_match_staged_from_one_seed_gives_its_bots_the_same_minds(self):
        """Which way a bot faces when it arrives and how long it waits before
        its first decision are drawn as it is built."""
        entropy.reseed(99)
        first = [mind.facing.tolist()
                 for mind in game.place_bots(match(bot_count=3)).values()]
        entropy.forget()
        entropy.reseed(99)
        assert [mind.facing.tolist()
                for mind in game.place_bots(match(bot_count=3)).values()] == first

    def test_two_bots_in_one_match_do_not_arrive_facing_the_same_way(self):
        entropy.reseed(99)
        placed = game.place_bots(match(bot_count=3))
        facings = [tuple(mind.facing) for mind in placed.values()]
        assert len(set(facings)) == 3

    def test_a_bot_given_a_seed_of_its_own_still_answers_to_it(self):
        assert (bots.Bot('bot0', seed=3).facing.tolist()
                == bots.Bot('bot0', seed=3).facing.tolist())


class TestWhereSomebodyComesBack:
    def make(self):
        return rules.Rules(match(), minds={},
                           flight=projectiles.Projectiles(
                               projectiles.default_table()))

    def test_the_choice_between_spawn_points_is_the_session_s(self):
        entropy.reseed(11)
        first = [self.make().chance.random() for _each in range(3)]
        entropy.forget()
        entropy.reseed(11)
        assert [self.make().chance.random() for _each in range(3)] == first

    def test_two_matches_in_one_session_do_not_choose_the_same_points(self):
        """A match restarted is a new match, not the last one again."""
        entropy.reseed(11)
        assert self.make().chance.random() != self.make().chance.random()

    def test_rules_given_a_seed_of_their_own_still_answer_to_it(self):
        made = rules.Rules(match(), minds={}, flight=None, seed=5)
        again = rules.Rules(match(), minds={}, flight=None, seed=5)
        assert made.chance.random() == again.chance.random()
