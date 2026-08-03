"""Where the level runs out.

Nothing in a map stops a fall, so stepping off the edge of one built as an
island falls for ever — which reads to a player as the game having hung rather
than as a mistake they made. These are the tests for the floor that ends it.
"""

from __future__ import annotations

import numpy as np
import pytest

from twig_bb import arena, falling, weapons


def match(*positions):
    made = arena.Arena(weapons=weapons.default_table())
    made.add('player', position=positions[0], name='You')
    for index, where in enumerate(positions[1:]):
        made.add('bot%d' % (index + 1,), position=where, bot=True,
                 name='Bot %d' % (index + 1,))
    return made


class _Bounded:
    """The one thing a kill floor asks of a loaded map."""

    class world:
        bounds = (np.array([-10.0, -4.0, -10.0]), np.array([10.0, 6.0, 10.0]))


class TestWhereTheFloorIs:

    def test_it_is_a_fixed_drop_below_the_maps_own_bounds(self):
        floor = falling.KillFloor.under(_Bounded(), margin=100.0)
        assert floor.height == pytest.approx(-104.0)

    def test_a_negative_margin_is_still_a_drop(self):
        """The margin is a distance, and a floor above the map is not one."""
        assert falling.KillFloor.under(_Bounded(), margin=-100.0).height \
            == pytest.approx(-104.0)

    def test_there_is_no_floor_without_a_map(self):
        assert falling.KillFloor.under(None) is None

    def test_the_default_margin_is_the_declared_one(self):
        assert falling.KillFloor.under(_Bounded()).height \
            == pytest.approx(-4.0 - falling.FALL_MARGIN)


class TestFallingOutOfTheWorld:

    def floor(self, height=-100.0):
        return falling.KillFloor(height)

    def test_somebody_below_it_dies(self):
        found = match((0.0, -200.0, 0.0))
        assert self.floor().advance(found) == 1
        assert not found.combatant('player').alive

    def test_somebody_above_it_does_not(self):
        found = match((0.0, 5.0, 0.0))
        assert self.floor().advance(found) == 0
        assert found.combatant('player').health == 100

    def test_it_is_a_death_rather_than_a_scratch(self):
        """Health left over would let a player fall on and on being hurt."""
        found = match((0.0, -200.0, 0.0))
        self.floor().advance(found)
        assert found.combatant('player').health == 0

    def test_armour_does_not_soften_it(self):
        """Armour is for being shot; the bottom of the world is not a hit."""
        found = match((0.0, -200.0, 0.0))
        found.combatant('player').player.give_armour(100)
        self.floor().advance(found)
        assert not found.combatant('player').alive

    def test_the_death_says_what_did_it(self):
        found = match((0.0, -200.0, 0.0))
        self.floor().advance(found)
        deaths = [event for event in found.events
                  if isinstance(event, arena.Death)]
        assert deaths and deaths[-1].cause == falling.FELL

    def test_bots_fall_out_of_the_world_too(self):
        """Which also bounds how far a bot walking into geometry can get."""
        found = match((0.0, 5.0, 0.0), (0.0, -200.0, 0.0))
        assert self.floor().advance(found) == 1
        assert not found.combatant('bot1').alive

    def test_the_dead_are_not_killed_again(self):
        """A corpse below the floor would emit a death a frame for ever."""
        found = match((0.0, -200.0, 0.0))
        self.floor().advance(found)
        found.drain()
        assert self.floor().advance(found) == 0
        assert not [event for event in found.events
                    if isinstance(event, arena.Death)]

    def test_it_reports_itself_to_the_overlay(self):
        assert self.floor(-42.0).describe() == {'kill floor (m)': -42.0}
