"""A body for everybody the rules move.

A bot used to be a position with one ray cast ahead of it, which is not a body:
it walked into corners the line missed, sank through floors it was never tested
against, and stood a metre inside the ground it spawned in. These are the
tests for it having the same capsule the player does — measured against
geometry the physics world actually holds, not against a rule.
"""

from __future__ import annotations

import numpy as np
import pytest

from omi_physics import model
from omi_physics.character import CharacterCapabilities
from omi_physics.world import PhysicsWorld

from twig_bb import avatar, walkers


def capabilities():
    """The player's own proportions, which is the point of the whole module."""
    return CharacterCapabilities(radius=avatar.RADIUS,
                                 standHeight=avatar.HEIGHT,
                                 crouchHeight=avatar.HEIGHT * 0.5,
                                 eyeHeight=avatar.EYE_HEIGHT,
                                 stepHeight=0.45, walkSpeed=3.6)


def world():
    return PhysicsWorld(gravity=model.Gravity(gravity=9.81, direction=(0, -1, 0)))


def slab(w, low, high):
    """A solid box of the given corners, as two triangles per face."""
    low, high = np.asarray(low, dtype='d'), np.asarray(high, dtype='d')
    points = np.array([[low[0], low[1], low[2]], [high[0], low[1], low[2]],
                       [high[0], low[1], high[2]], [low[0], low[1], high[2]],
                       [low[0], high[1], low[2]], [high[0], high[1], low[2]],
                       [high[0], high[1], high[2]], [low[0], high[1], high[2]]],
                      dtype='d')
    faces = [(0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6), (0, 4, 5), (0, 5, 1),
             (1, 5, 6), (1, 6, 2), (2, 6, 7), (2, 7, 3), (3, 7, 4), (3, 4, 0)]
    shape = w.add_shape(model.Shape.trimesh(points, np.array(faces, dtype='i')))
    return w.add_body(model.Motion(type=model.STATIC),
                      collider=model.Collider(shape=shape), position=(0, 0, 0))


def floor(w, y=0.0, reach=40.0):
    # Thicker than a body is tall, as a level's floor is: a slab thinner than
    # the capsule is one it is through *both* faces of, which has no nearest
    # way out and is not a case any map presents.
    slab(w, (-reach, y - 4.0, -reach), (reach, y, reach))
    return w


def made(w):
    return walkers.Walkers(w, capabilities(), gravity=9.81)


def run(group, id, feet, heading, seconds=1.0, step=1.0 / 60.0):
    where = np.asarray(feet, dtype='d')
    for _ in range(int(round(seconds / step))):
        where = group.walk(id, where, heading, step)
    return where


class TestBeingPutInTheWorld:

    def test_somebody_placed_inside_the_floor_is_stood_on_top_of_it(self):
        """The bug as reported: capsules stuck in the floor, not walking.

        Nothing used to test a bot against the level at all, so a spawn a
        little under the floor stayed a little under the floor for the whole
        match.  A step height is the tolerance, and is the same statement this
        game already makes about how far off the ground a body may be.
        """
        group = made(floor(world()))
        group.place('bot1', (0.0, -0.2, 0.0))
        assert group.of('bot1').base()[1] == pytest.approx(0.0, abs=0.05)

    def test_somebody_placed_above_the_floor_is_seated_on_it(self):
        group = made(floor(world()))
        group.place('bot1', (0.0, 2.0, 0.0))
        run(group, 'bot1', (0.0, 2.0, 0.0), None, seconds=1.0)
        assert group.of('bot1').base()[1] == pytest.approx(0.0, abs=0.05)

    def test_a_body_is_made_on_the_first_step_without_being_asked_for(self):
        """A match is built before there is a world to put anybody in."""
        group = made(floor(world()))
        assert 'bot1' not in group
        group.walk('bot1', (0.0, 0.0, 0.0), None, 1.0 / 60.0)
        assert 'bot1' in group

    def test_placing_again_replaces_the_body(self):
        """A respawn is a fresh body, not the old one teleported still falling."""
        group = made(floor(world()))
        first = group.place('bot1', (0.0, 0.0, 0.0))
        assert group.place('bot1', (5.0, 0.0, 5.0)) is not first
        assert len(group) == 1

    def test_a_body_can_be_taken_back_out(self):
        group = made(floor(world()))
        group.place('bot1', (0.0, 0.0, 0.0))
        group.forget('bot1')
        assert group.of('bot1') is None and len(group) == 0

    def test_forgetting_somebody_who_was_never_there_is_harmless(self):
        made(floor(world())).forget('nobody')

    def test_who_is_walking_can_be_enumerated(self):
        group = made(floor(world()))
        group.place('bot1', (0.0, 0.0, 0.0))
        group.place('bot2', (5.0, 0.0, 0.0))
        assert sorted(group) == ['bot1', 'bot2']


class TestWalking:

    def test_walking_across_open_floor_gets_somewhere(self):
        group = made(floor(world()))
        where = run(group, 'bot1', (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
        assert where[0] > 2.0

    def test_it_does_not_sink_while_it_walks(self):
        group = made(floor(world()))
        where = run(group, 'bot1', (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), seconds=3.0)
        assert where[1] == pytest.approx(0.0, abs=0.05)

    def test_a_wall_head_on_stops_it(self):
        w = floor(world())
        slab(w, (4.0, 0.0, -10.0), (5.0, 4.0, 10.0))
        group = made(w)
        where = run(group, 'bot1', (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), seconds=3.0)
        assert where[0] < 4.0

    def test_it_does_not_end_up_inside_the_wall(self):
        w = floor(world())
        slab(w, (4.0, 0.0, -10.0), (5.0, 4.0, 10.0))
        group = made(w)
        run(group, 'bot1', (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), seconds=3.0)
        assert not group.of('bot1').stuck

    def test_a_wall_met_at_an_angle_is_slid_along(self):
        """What the old probe could not do: it refused the step outright, and
        a bot pressed into a corner buzzed there for the rest of the match."""
        w = floor(world())
        slab(w, (4.0, 0.0, -20.0), (5.0, 4.0, 20.0))
        group = made(w)
        where = run(group, 'bot1', (0.0, 0.0, 0.0), (1.0, 0.0, 1.0), seconds=3.0)
        assert where[2] > 2.0

    def test_a_step_is_climbed(self):
        w = floor(world())
        slab(w, (3.0, 0.0, -10.0), (20.0, 0.3, 10.0))
        group = made(w)
        where = run(group, 'bot1', (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), seconds=4.0)
        assert where[0] > 4.0
        assert where[1] == pytest.approx(0.3, abs=0.05)

    def test_walking_off_a_ledge_falls(self):
        w = world()
        slab(w, (-10.0, -1.0, -10.0), (2.0, 0.0, 10.0))
        group = made(w)
        where = run(group, 'bot1', (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), seconds=2.0)
        assert where[1] < -1.0

    def test_standing_still_is_still_stepped(self):
        """Gravity does not wait for somebody to decide to move."""
        group = made(floor(world()))
        where = run(group, 'bot1', (0.0, 3.0, 0.0), None, seconds=2.0)
        assert where[1] == pytest.approx(0.0, abs=0.05)


class TestBeingThrown:

    def test_a_shove_moves_them(self):
        group = made(floor(world()))
        group.place('bot1', (0.0, 0.0, 0.0))
        assert group.shove('bot1', (8.0, 0.0, 0.0)) is True
        where = run(group, 'bot1', (0.0, 0.0, 0.0), None, seconds=1.0)
        assert where[0] > 1.0

    def test_a_shove_can_throw_them_upward_as_well(self):
        """The old rule flattened knockback, so a rocket at the feet did not lift."""
        group = made(floor(world()))
        group.place('bot1', (0.0, 0.0, 0.0))
        group.shove('bot1', (0.0, 6.0, 0.0))
        highest = 0.0
        where = np.zeros(3)
        for _ in range(30):
            where = group.walk('bot1', where, None, 1.0 / 60.0)
            highest = max(highest, float(where[1]))
        assert highest > 0.3

    def test_shoving_somebody_with_no_body_says_so(self):
        assert made(floor(world())).shove('nobody', (1.0, 0.0, 0.0)) is False


class TestWhatItReportsToTheOverlay:

    def test_it_counts_the_bodies_and_the_stuck_ones(self):
        group = made(floor(world()))
        group.place('bot1', (0.0, 0.0, 0.0))
        assert group.describe() == {'walkers': 1, 'stuck': 0}
