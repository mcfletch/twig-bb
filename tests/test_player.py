"""What the player has: health, armour, ammunition and a weapon in hand.

State is a record rather than attributes scattered over the scenegraph, because
[PROJECT-PLAN §11](../PROJECT-PLAN.md) needs it to be enumerable and copyable
long before there is a network to send it over.  All of it is arithmetic.
"""

from __future__ import annotations

import pytest

from twitchoglc import weapons
from twitchoglc.player import PlayerState


@pytest.fixture
def table():
    return weapons.default_table()


@pytest.fixture
def player(table):
    return PlayerState.starting(table)


class TestStartingOut:
    def test_a_new_player_is_at_full_health_with_no_armour(self, player):
        assert player.health == player.max_health
        assert player.armour == 0

    def test_a_new_player_holds_the_first_weapon_only(self, player, table):
        assert player.weapons == [table.by_slot(1).key]
        assert player.selected == table.by_slot(1).key

    def test_a_new_player_has_ammunition_for_what_they_hold(self, player):
        assert player.ammo['bullets'] > 0

    def test_the_state_can_be_copied_whole(self, player):
        """§11: a thing that can be copied can be snapshotted and compared."""
        import copy
        clone = copy.deepcopy(player)
        clone.health = 1
        assert player.health != 1


class TestDamage:
    def test_damage_comes_off_the_health(self, player):
        player.take_damage(30)
        assert player.health == 70

    def test_armour_takes_its_share_first(self, player):
        player.armour = 50
        player.take_damage(40)
        assert player.armour < 50
        assert player.health > 60

    def test_health_never_goes_below_nothing(self, player):
        player.take_damage(500)
        assert player.health == 0

    def test_a_player_at_no_health_is_dead(self, player):
        assert player.alive
        player.take_damage(500)
        assert not player.alive

    def test_healing_stops_at_the_maximum(self, player):
        player.take_damage(50)
        player.heal(500)
        assert player.health == player.max_health


class TestWeapons:
    def test_a_weapon_that_is_not_held_cannot_be_selected(self, player):
        assert player.select('shotgun') is False
        assert player.selected == 'pistol'

    def test_picking_one_up_makes_it_selectable(self, player):
        player.give('shotgun')
        assert player.select('shotgun') is True
        assert player.selected == 'shotgun'

    def test_picking_up_what_you_already_have_changes_nothing(self, player):
        assert player.give('pistol') is False
        assert player.weapons == ['pistol']

    def test_the_wheel_walks_the_weapons_that_are_held(self, player, table):
        player.give('shotgun')
        player.give('rifle')
        assert player.cycle(table, 1) == 'shotgun'
        assert player.cycle(table, 1) == 'rifle'

    def test_the_wheel_wraps_round(self, player, table):
        player.give('shotgun')
        assert player.cycle(table, 1) == 'shotgun'
        assert player.cycle(table, 1) == 'pistol'

    def test_the_wheel_turns_the_other_way_too(self, player, table):
        player.give('shotgun')
        assert player.cycle(table, -1) == 'shotgun'

    def test_the_wheel_on_one_weapon_stays_where_it_is(self, player, table):
        assert player.cycle(table, 1) == 'pistol'

    def test_a_number_key_selects_the_weapon_on_that_slot(self, player, table):
        player.give('shotgun')
        assert player.select_slot(table, 2) is True
        assert player.selected == 'shotgun'

    def test_a_number_key_for_a_weapon_you_lack_does_nothing(self, player,
                                                             table):
        assert player.select_slot(table, 2) is False
        assert player.selected == 'pistol'


class TestAmmunition:
    def test_ammunition_is_counted_per_type(self, player, table):
        assert player.ammo_for(table.by_key('pistol')) == player.ammo['bullets']

    def test_firing_costs_what_the_weapon_says(self, player, table):
        rifle = table.by_key('rifle')
        player.give('rifle')
        player.ammo['cells'] = 10
        assert player.spend(rifle) is True
        assert player.ammo['cells'] == 8

    def test_a_weapon_cannot_fire_without_the_ammunition(self, player, table):
        rifle = table.by_key('rifle')
        player.ammo['cells'] = 1
        assert player.can_fire(rifle) is False
        assert player.spend(rifle) is False
        assert player.ammo['cells'] == 1

    def test_ammunition_is_capped_when_it_is_picked_up(self, player):
        player.give_ammo('bullets', 10_000)
        assert player.ammo['bullets'] == PlayerState.AMMO_MAXIMUM

    def test_a_type_nobody_has_any_of_reads_as_none(self, player, table):
        assert player.ammo_for(table.by_key('shotgun')) == 0


class TestSpread:
    def test_firing_opens_the_cone_and_time_closes_it(self, player):
        player.fired(now=10.0)
        hot = player.spread_fraction(10.05)
        assert hot > 0
        assert player.spread_fraction(11.0) < hot

    def test_the_cone_is_shut_before_a_shot_is_fired(self, player):
        assert player.spread_fraction(0.0) == 0.0

    def test_firing_repeatedly_does_not_open_it_past_the_widest(self, player):
        for index in range(20):
            player.fired(now=10.0 + index * 0.01)
        assert player.spread_fraction(10.2) <= 1.0


class TestTheStandInLoadout:
    """Until §6 puts items in the map, nothing can hand a player a weapon.

    A player who starts with one weapon and no way to find another has two
    number keys that can never do anything, which reads as a broken key rather
    than as a missing feature.
    """

    def test_a_player_can_be_given_the_whole_table(self, table):
        player = PlayerState.carrying(table)
        assert player.weapons == table.keys()

    def test_every_weapon_they_carry_has_ammunition(self, table):
        player = PlayerState.carrying(table)
        for weapon in table.weapons:
            assert player.ammo_for(weapon) > 0

    def test_they_start_holding_the_first_one(self, table):
        assert PlayerState.carrying(table).selected == table.by_slot(1).key

    def test_every_number_key_in_the_table_now_selects(self, table):
        player = PlayerState.carrying(table)
        for weapon in table.weapons:
            assert player.select_slot(table, int(weapon.slot)) or \
                player.selected == str(weapon.key)

    def test_it_is_still_possible_to_spawn_with_one_weapon(self, table):
        """What a match with pickups in it actually starts a player on."""
        assert len(PlayerState.starting(table).weapons) == 1

    def test_the_starting_weapon_brings_its_own_ammunition(self, table):
        """The weapon's number, not one written a second time somewhere else:
        a spawn that handed out a flat fifty made ``startingAmmo`` a field
        nothing read."""
        table.by_key('pistol').startingAmmo = 23
        assert PlayerState.starting(table).ammo['bullets'] == 23

    def test_a_starting_player_has_no_armour(self, table):
        """Armour is picked up, and a spawn wearing it is a permanent upgrade."""
        assert PlayerState.starting(table).armour == 0


class TestHowMuchOfEachTheyStartWith:
    """The table says, because how many rockets is worth is a design decision.

    A stand-in loadout that handed out sixty of everything made a rocket
    launcher an assault rifle with a bigger bang, which is exactly the thing
    the weapon table exists to stop happening by accident.
    """

    def test_the_weapon_says_how_much_it_comes_with(self, table):
        table.by_key('pistol').startingAmmo = 7
        assert PlayerState.carrying(table).ammo['bullets'] == 7

    def test_a_launcher_comes_with_far_less_than_a_rifle(self, table):
        player = PlayerState.carrying(table)
        assert player.ammo_for(table.by_key('rocket')) \
            < player.ammo_for(table.by_key('rifle'))

    def test_weapons_sharing_a_pool_do_not_each_fill_it(self, table):
        """Two weapons that eat the same rounds hold one pile between them."""
        for weapon in table.weapons:
            weapon.ammoType = 'shared'
            weapon.startingAmmo = 10
        assert PlayerState.carrying(table).ammo['shared'] == 10
