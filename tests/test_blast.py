"""What a burst does to everybody near it: damage, cover, and the shove.

The shove is the interesting one.  A rocket that pushes the person who fired it
is what a rocket jump *is*, so self-damage and self-knockback are the feature
rather than a case to guard against — and both are asserted here.
"""

from __future__ import annotations

import numpy as np
import pytest

from omi_physics import model
from omi_physics.world import PhysicsWorld

from twig_bb import arena, blast, projectiles, weapons


def world():
    return PhysicsWorld(gravity=model.Gravity(gravity=9.81, direction=(0, -1, 0)))


def wall(w, x, extent=30.0):
    e = extent
    points = np.array([(x, -e, -e), (x, e, -e), (x, e, e), (x, -e, e)], dtype='d')
    indices = np.array([(0, 1, 2), (0, 2, 3)], dtype='i')
    shape = w.add_shape(model.Shape.trimesh(points, indices))
    return w.add_body(model.Motion(type=model.STATIC),
                      collider=model.Collider(shape=shape), position=(0, 0, 0))


def match(*places):
    """A match with the player at the origin and bots at ``places``."""
    made = arena.Arena(weapons=weapons.default_table(), fragLimit=15,
                       timeLimit=10.0)
    made.add('player', position=(0.0, 0.0, 0.0), name='You')
    for index, where in enumerate(places):
        made.add('bot%d' % index, position=where, bot=True,
                 name='Bot %d' % index)
    return made


@pytest.fixture
def rocket():
    return projectiles.default_table().by_key(projectiles.ROCKET)


def hurt(found, id):
    return arena.STARTING_HEALTH - found.combatant(id).health


class TestFallingOffWithDistance:

    def test_a_burst_at_their_chest_does_the_most(self, rocket):
        """Measured against where a burst is *aimed*, which is the chest.

        The number here is the splash damage undiminished, so the point has to
        be the one the falloff measures from; a literal that happened to match
        it when a body was a different size would quietly become a test of the
        falloff curve instead.
        """
        found = match((0.0, 0.0, 0.0))
        blast.burst(world(), found, point=(0, blast.CHEST_HEIGHT, 0),
                    kind=rocket, by='player')
        assert hurt(found, 'bot0') == pytest.approx(float(rocket.splashDamage),
                                                    abs=2)

    def test_further_away_does_less(self, rocket):
        near = match((1.0, 0.0, 0.0))
        far = match((3.0, 0.0, 0.0))
        for found in (near, far):
            blast.burst(world(), found, point=(0, 0.9, 0), kind=rocket,
                        by='player')
        assert 0 < hurt(far, 'bot0') < hurt(near, 'bot0')

    def test_beyond_the_radius_does_nothing(self, rocket):
        found = match((float(rocket.splashRadius) + 2.0, 0.0, 0.0))
        blast.burst(world(), found, point=(0, 0.9, 0), kind=rocket, by='player')
        assert hurt(found, 'bot0') == 0

    def test_the_curve_is_the_one_the_table_declares(self, rocket):
        """The numbers are ours, so the table is where the design is written."""
        rocket.splashFalloff = 1.0              # linear
        # Half the radius away, measured chest to burst: the bot stands on the
        # floor and the burst is at chest height, so the offset is horizontal.
        found = match((float(rocket.splashRadius) * 0.5, 0.0, 0.0))
        blast.burst(world(), found, point=(0, blast.CHEST_HEIGHT, 0),
                    kind=rocket, by='player')
        assert hurt(found, 'bot0') == pytest.approx(
            float(rocket.splashDamage) * 0.5, abs=2)


class TestABurstBeingWorthDodging:
    """How much a *near miss* costs, which is the whole of what splash is for.

    A launcher whose burst has to land on somebody to matter is a launcher
    that is only a slow rifle: what the weapon actually asks of a player is to
    aim at the floor beside them, and that trade is only worth taking if the
    floor beside them hurts.  The numbers here are the design, so they are
    stated as what a player experiences -- a share of a life, and a shove
    bigger than a jump -- rather than as whatever the table currently says.
    """

    def near_miss(self, kind, metres):
        """What a burst ``metres`` from somebody's chest takes off them."""
        found = match((float(metres), 0.0, 0.0))
        blast.burst(world(), found, point=(0, blast.CHEST_HEIGHT, 0),
                    kind=kind, by='player')
        return hurt(found, 'bot0')

    def test_a_rocket_two_metres_off_costs_a_third_of_a_life(self, rocket):
        assert self.near_miss(rocket, 2.0) >= arena.STARTING_HEALTH / 3.0

    def test_a_grenade_two_metres_off_does_too(self):
        grenade = projectiles.default_table().by_key(projectiles.GRENADE)
        assert self.near_miss(grenade, 2.0) >= arena.STARTING_HEALTH / 3.0

    def test_a_grenade_at_your_feet_throws_you_higher_than_a_jump(self):
        """The same claim the rocket carries, because it is the same burst.

        A grenade that went off underfoot and left the player standing where
        they were reads as a dud, however much health it took.
        """
        grenade = projectiles.default_table().by_key(projectiles.GRENADE)
        jump = float(np.sqrt(2.0 * 9.81 * 64 * 0.0254))
        found = match()
        blast.burst(world(), found, point=(0, 0.0, 0), kind=grenade,
                    by='player')
        assert float(found.combatant('player').push[1]) > jump

    def test_a_grenade_jump_is_survivable_at_full_health(self):
        grenade = projectiles.default_table().by_key(projectiles.GRENADE)
        found = match()
        blast.burst(world(), found, point=(0, 0.0, 0), kind=grenade,
                    by='player')
        assert found.combatant('player').alive


class TestCover:
    """A rocket round a corner must not kill."""

    def test_a_wall_between_the_burst_and_a_target_stops_it(self, rocket):
        w = world()
        wall(w, x=1.0)
        found = match((2.0, 0.0, 0.0))
        blast.burst(w, found, point=(0, 0.9, 0), kind=rocket, by='player')
        assert hurt(found, 'bot0') == 0

    def test_a_wall_past_the_target_does_not(self, rocket):
        w = world()
        wall(w, x=3.0)
        found = match((2.0, 0.0, 0.0))
        blast.burst(w, found, point=(0, 0.9, 0), kind=rocket, by='player')
        assert hurt(found, 'bot0') > 0

    def test_only_those_in_range_are_tested_against_geometry(self, rocket):
        """B11: bound the candidate set by distance before casting anything.

        Twenty bots across the level and one person at the burst: a cast each
        would be O(n^2) over a firefight, and the cheap test is a subtraction.
        """
        found = match(*[(50.0 + index, 0.0, 0.0) for index in range(20)])
        casts = []
        w = world()
        original = blast.raycast.line_of_sight

        def counted(*args, **named):
            casts.append(args)
            return original(*args, **named)

        blast.raycast.line_of_sight = counted
        try:
            blast.burst(w, found, point=(0, 0.9, 0), kind=rocket, by='player')
        finally:
            blast.raycast.line_of_sight = original
        assert len(casts) == 1              # the player, who is standing in it


class TestTheShove:

    def test_a_burst_pushes_what_it_hurts(self, rocket):
        found = match((2.0, 0.0, 0.0))
        blast.burst(world(), found, point=(0, 0.9, 0), kind=rocket, by='player')
        assert float(np.linalg.norm(found.combatant('bot0').push)) > 0.0

    def test_it_pushes_away_from_the_burst(self, rocket):
        found = match((2.0, 0.0, 0.0))
        blast.burst(world(), found, point=(0, 0.9, 0), kind=rocket, by='player')
        assert float(found.combatant('bot0').push[0]) > 0.0

    def test_a_burst_underfoot_pushes_upward(self, rocket):
        """The whole of a rocket jump: the ground below you throws you up."""
        found = match()
        blast.burst(world(), found, point=(0, -0.2, 0), kind=rocket,
                    by='player')
        push = found.combatant('player').push
        assert float(push[1]) > 0.0
        assert float(push[1]) > abs(float(push[0]))

    def test_a_nearer_burst_pushes_harder(self, rocket):
        near = match((1.0, 0.0, 0.0))
        far = match((3.0, 0.0, 0.0))
        for found in (near, far):
            blast.burst(world(), found, point=(0, 0.9, 0), kind=rocket,
                        by='player')
        assert float(np.linalg.norm(far.combatant('bot0').push)) \
            < float(np.linalg.norm(near.combatant('bot0').push))

    def test_two_bursts_add_up(self, rocket):
        """Nothing may quietly replace a push somebody has not yet spent."""
        found = match((2.0, 0.0, 0.0))
        blast.burst(world(), found, point=(0, 0.9, 0), kind=rocket, by='player')
        once = found.combatant('bot0').push.copy()
        blast.burst(world(), found, point=(0, 0.9, 0), kind=rocket, by='player')
        assert float(np.linalg.norm(found.combatant('bot0').push)) \
            > float(np.linalg.norm(once))


class TestRocketJumps:
    """Why this genre exists.  Self-damage is what makes it a decision."""

    def test_a_shooter_is_hurt_by_their_own_burst(self, rocket):
        found = match()
        blast.burst(world(), found, point=(0, 0.2, 0), kind=rocket, by='player')
        assert hurt(found, 'player') > 0

    def test_they_are_hurt_less_than_somebody_else_standing_there(self, rocket):
        """Survivable, or it is not a move; not free, or it is not a decision."""
        found = match((0.0, 0.0, 0.0))      # a bot standing where the player is
        blast.burst(world(), found, point=(0, 0.2, 0), kind=rocket, by='player')
        assert 0 < hurt(found, 'player') < hurt(found, 'bot0')

    def test_a_rocket_jump_is_survivable_at_full_health(self, rocket):
        found = match()
        blast.burst(world(), found, point=(0, 0.0, 0), kind=rocket, by='player')
        assert found.combatant('player').alive

    def test_killing_yourself_with_it_costs_a_frag(self, rocket):
        """The rule already in the arena, and this is what most exercises it."""
        found = match()
        found.combatant('player').player.health = 5
        blast.burst(world(), found, point=(0, 0.0, 0), kind=rocket, by='player')
        assert not found.combatant('player').alive
        assert found.score('player') == -1


class TestWhoIsInIt:

    def test_the_dead_are_not_blown_up_again(self, rocket):
        found = match((1.0, 0.0, 0.0))
        found.damage('bot0', 500, by='player')
        found.drain()
        blast.burst(world(), found, point=(0, 0.9, 0), kind=rocket, by='player')
        assert not [event for event in found.events
                    if isinstance(event, arena.Damaged)
                    and event.target == 'bot0']

    def test_a_direct_hit_is_not_splashed_as_well(self, rocket):
        """The direct damage already says "that hit you squarely"."""
        found = match((1.0, 0.0, 0.0))
        blast.burst(world(), found, point=(1, 0.9, 0), kind=rocket, by='player',
                    direct='bot0')
        assert hurt(found, 'bot0') == 0

    def test_everybody_else_in_range_still_is(self, rocket):
        found = match((1.0, 0.0, 0.0), (1.5, 0.0, 0.0))
        blast.burst(world(), found, point=(1, 0.9, 0), kind=rocket, by='player',
                    direct='bot0')
        assert hurt(found, 'bot1') > 0

    def test_a_kind_with_no_splash_does_nothing(self, rocket):
        rocket.splashRadius = 0.0
        found = match((0.5, 0.0, 0.0))
        assert blast.burst(world(), found, point=(0, 0.9, 0), kind=rocket,
                           by='player') == []


class TestAnsweringWhatFlew:
    """The seam: a projectile says it went off, and this is what that costs."""

    def test_every_detonation_bursts(self, rocket):
        found = match((1.0, 0.0, 0.0))
        table = projectiles.default_table()
        blast.answer(world(), found, table, [projectiles.Detonation(
            point=np.array([0.0, 0.9, 0.0]), kind=projectiles.ROCKET,
            by='player')])
        assert hurt(found, 'bot0') > 0

    def test_the_direct_hit_is_carried_through(self, rocket):
        found = match((1.0, 0.0, 0.0))
        table = projectiles.default_table()
        blast.answer(world(), found, table, [projectiles.Detonation(
            point=np.array([1.0, 0.9, 0.0]), kind=projectiles.ROCKET,
            by='player', target='bot0')])
        assert hurt(found, 'bot0') == 0

    def test_a_kind_the_table_does_not_have_costs_a_bang_not_a_frame(self):
        found = match((1.0, 0.0, 0.0))
        assert blast.answer(world(), found, projectiles.default_table(),
                            [projectiles.Detonation(
                                point=np.array([0.0, 0.9, 0.0]),
                                kind='nothing-like-this', by='player')]) == []


class TestSpendingAShove:

    def test_an_unspent_shove_is_handed_over_once(self, rocket):
        found = match((1.0, 0.0, 0.0))
        blast.burst(world(), found, point=(0, 0.9, 0), kind=rocket, by='player')
        assert blast.spend(found, 'bot0') is not None
        assert blast.spend(found, 'bot0') is None

    def test_nobody_pushed_has_nothing_to_spend(self):
        assert blast.spend(match((1.0, 0.0, 0.0)), 'bot0') is None

    def test_an_unknown_id_has_nothing_to_spend(self):
        assert blast.spend(match(), 'nobody-here') is None



class TestWhatSelfDamageScalesAndWhatItDoesNot:
    """It is the *damage* a shooter is spared, never the shove.

    A rocket jump is the push; the reduced damage is what makes taking one a
    decision rather than free movement. Scaling the push by the same number
    would make a shooter's own rocket lift them less than a plain jump does,
    which is not a rocket jump at all.
    """

    def test_a_shooter_is_pushed_as_hard_as_anybody_else_there(self, rocket):
        found = match((0.0, 0.0, 0.0))      # a bot standing where the player is
        blast.burst(world(), found, point=(0, -0.2, 0), kind=rocket,
                    by='player')
        mine = float(np.linalg.norm(found.combatant('player').push))
        theirs = float(np.linalg.norm(found.combatant('bot0').push))
        assert mine == pytest.approx(theirs)

    def test_and_is_still_hurt_less(self, rocket):
        found = match((0.0, 0.0, 0.0))
        blast.burst(world(), found, point=(0, -0.2, 0), kind=rocket,
                    by='player')
        assert hurt(found, 'player') < hurt(found, 'bot0')

    def test_a_rocket_at_your_feet_lifts_you_higher_than_a_jump(self, rocket):
        """The whole point: it has to be worth the health it costs.

        A jump reaches 64 map units, which is the speed below; a rocket jump
        that cleared less than that would be a worse jump that also hurt.
        """
        jump = float(np.sqrt(2.0 * 9.81 * 64 * 0.0254))
        found = match()
        blast.burst(world(), found, point=(0, 0.0, 0), kind=rocket,
                    by='player')
        assert float(found.combatant('player').push[1]) > jump
