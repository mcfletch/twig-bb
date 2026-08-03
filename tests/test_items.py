"""What a map leaves lying about for players to pick up.

A level is a circuit, and the things placed around it are what give it a shape.
Every one of the 67 sample maps places at least one — 3561 in all — so a viewer
that ignores them is ignoring most of what the author placed, and a match
becomes a fixed loadout spent once and then a player with nothing to shoot
with. That is what was reported.
"""

from __future__ import annotations

import numpy as np
import pytest

from twig_bb import arena, avatar, items, weapons
from twig_bb.entities import Entity
from twig_bb.player import PlayerState


def match(where=(0.0, 0.0, 0.0), bots=0, health=10):
    """A match with the player *hurt*, because a full one refuses a medikit."""
    made = arena.Arena(weapons=weapons.default_table())
    made.add('player', position=np.asarray(where, dtype='d'), name='You')
    made.combatant('player').player.health = health
    for index in range(bots):
        made.add('bot%d' % (index + 1,), position=(50.0, 0.0, 50.0), bot=True,
                 name='Bot %d' % (index + 1,))
    return made


def kind(**named):
    named.setdefault('key', 'test')
    named.setdefault('title', 'TEST')
    return items.ItemKind(**named)


def placed(one, where=(0.0, 0.0, 0.0), respawn=10.0):
    return items.Pickups([items.Pickup(kind=one,
                                       position=np.asarray(where, dtype='d'),
                                       respawn=respawn)])


class TestWhatAKindGives:
    """Several fields at once, and a zero gives nothing: no type to branch on."""

    def player(self, **named):
        state = PlayerState(**named)
        return state

    def test_health_is_restored(self):
        hurt = self.player(health=40)
        assert kind(health=25).give_to(hurt) is True
        assert hurt.health == 65

    def test_health_never_goes_past_the_maximum(self):
        hurt = self.player(health=90)
        kind(health=50).give_to(hurt)
        assert hurt.health == 100

    def test_a_full_player_leaves_the_medikit_on_the_floor(self):
        """Or one player at full health destroys it for everybody and gains
        nothing, which is the worst possible outcome for both of them."""
        assert kind(health=25).give_to(self.player(health=100)) is False

    def test_armour_is_given_and_capped(self):
        one = self.player()
        assert kind(armour=150).give_to(one) is True
        assert one.armour == one.max_armour

    def test_a_full_set_of_armour_refuses(self):
        one = self.player(armour=100)
        assert kind(armour=50).give_to(one) is False

    def test_ammunition_goes_into_its_own_pool(self):
        one = self.player()
        assert kind(ammo=30, ammoType='bullets').give_to(one) is True
        assert one.ammo['bullets'] == 30

    def test_ammunition_with_no_pool_named_gives_nothing(self):
        assert kind(ammo=30).give_to(self.player()) is False

    def test_a_weapon_is_added_to_what_is_held(self):
        one = self.player()
        assert kind(weapon='rocket').give_to(one) is True
        assert one.has('rocket')

    def test_a_weapon_already_held_is_still_worth_its_ammunition(self):
        one = self.player(weapons=['rocket'])
        assert kind(weapon='rocket', ammo=5,
                    ammoType='rockets').give_to(one) is True
        assert one.ammo['rockets'] == 5

    def test_a_weapon_already_held_with_nothing_in_it_refuses(self):
        assert kind(weapon='rocket').give_to(
            self.player(weapons=['rocket'])) is False

    def test_several_things_at_once(self):
        one = self.player(health=50)
        assert kind(health=25, armour=50, weapon='rocket', ammo=5,
                    ammoType='rockets').give_to(one) is True
        assert (one.health, one.armour, one.has('rocket'),
                one.ammo['rockets']) == (75, 50, True, 5)


class TestTheTable:
    """The join between a map's names and this game's numbers, as data."""

    def table(self):
        return items.default_table()

    def test_a_classname_the_content_uses_is_answered(self):
        assert self.table().for_classname('item_health') is not None

    def test_the_case_a_map_wrote_it_in_does_not_matter(self):
        assert self.table().for_classname('ITEM_HEALTH') is not None

    def test_a_classname_nothing_declares_is_content_we_lack(self):
        """`SPEC-Q3ENTITIES §3.2.4`: the names are not a closed set."""
        assert self.table().for_classname('item_quad') is None

    def test_the_broken_classname_one_map_writes_is_not_an_error(self):
        """`SPEC-Q3ENTITIES §3.2.5`: 14 entities spelled `item_health_small (0 1 0`."""
        assert self.table().for_classname('item_health_small (0 1 0') is None

    def test_every_weapon_pickup_names_a_weapon_the_table_has(self):
        """A pickup granting a weapon nobody can select is a dead pickup."""
        held = set(weapons.default_table().keys())
        for one in self.table().kinds:
            if str(one.weapon):
                assert str(one.weapon) in held

    def test_every_ammunition_pickup_names_a_pool_some_weapon_eats(self):
        pools = {str(gun.ammoType) for gun in weapons.default_table().weapons}
        for one in self.table().kinds:
            if int(one.ammo) > 0:
                assert str(one.ammoType) in pools

    def test_every_weapon_pickup_arrives_with_something_in_it(self):
        """A weapon you cannot fire is not a pickup, it is a disappointment."""
        for one in self.table().kinds:
            if str(one.weapon):
                assert int(one.ammo) > 0

    def test_the_commonest_content_classnames_are_all_covered(self):
        """The ones that carry a level's circuit; see `SPEC-Q3ENTITIES §3.2.3`."""
        table = self.table()
        for name in ('item_health', 'item_health_small', 'item_health_large',
                     'item_armor_shard', 'item_armor_combat',
                     'item_armor_body', 'ammo_bullets', 'ammo_shells',
                     'ammo_cells', 'ammo_rockets', 'ammo_grenades',
                     'weapon_shotgun', 'weapon_rocketlauncher',
                     'weapon_grenadelauncher', 'weapon_railgun'):
                assert table.for_classname(name) is not None, name

    def test_a_key_can_be_looked_up(self):
        assert self.table().by_key('health') is not None
        assert self.table().by_key('nothing-like-this') is None


class TestReadingThemOutOfAMap:

    def entity(self, classname, origin='0 0 0', **named):
        return Entity(dict({'classname': classname, 'origin': origin}, **named))

    def test_a_pickup_is_found(self):
        found = items.from_entities([self.entity('item_health')])
        assert len(found) == 1

    def test_it_is_placed_in_scene_space(self):
        """The map's axes are not the scene's; `SPEC-BSP38 §3.2`."""
        found = items.from_entities([self.entity('item_health', '64 0 0')])
        assert not np.allclose(found[0].position, (64.0, 0.0, 0.0))

    def test_content_we_lack_is_skipped_rather_than_failing(self):
        assert items.from_entities([self.entity('item_quad')]) == []

    def test_what_was_skipped_can_be_reported(self):
        """A silent skip and a broken reader look identical from in the game."""
        missing = items.unknown_classnames([self.entity('item_quad'),
                                            self.entity('item_quad'),
                                            self.entity('item_health')])
        assert missing == {'item_quad': 2}

    def test_an_entity_that_is_not_a_pickup_at_all_is_not_reported(self):
        assert items.unknown_classnames([self.entity('target_speaker')]) == {}

    def test_the_navigation_hint_is_not_a_pickup(self):
        """`SPEC-Q3ENTITIES §3.2.6`: `item_botroam` is a hint for opponents."""
        assert items.from_entities([self.entity('item_botroam')]) == []

    def test_the_kinds_own_interval_is_used_by_default(self):
        found = items.from_entities([self.entity('item_health')])
        assert found[0].respawn == pytest.approx(
            float(items.default_table().for_classname('item_health').respawn))

    def test_the_entitys_wait_overrides_it(self):
        """`SPEC-Q3ENTITIES §3.5`: 133 entities carry one."""
        found = items.from_entities([self.entity('item_health', wait='40')])
        assert found[0].respawn == pytest.approx(40.0)

    def test_a_map_with_no_pickups_is_no_pickups(self):
        assert items.from_entities([]) == []


class TestWalkingIntoOne:

    def test_standing_on_it_takes_it(self):
        found = match()
        took = placed(kind(health=25)).advance(found, 0.1)
        assert [one.by for one in took] == ['player']

    def test_it_is_gone_afterwards(self):
        where = placed(kind(health=25))
        where.advance(match(), 0.1)
        assert where.available() == []

    def test_standing_across_the_room_does_not(self):
        found = match(where=(20.0, 0.0, 0.0))
        assert placed(kind(health=25)).advance(found, 0.1) == []

    def test_an_item_at_head_height_is_taken(self):
        """A body, not a point: anywhere a person occupies counts."""
        head = match(where=(0.0, -avatar.HEIGHT + 0.1, 0.0))
        assert placed(kind(health=25)).advance(head, 0.1)

    def test_one_on_a_balcony_is_not_taken_from_the_floor_below(self):
        below = match(where=(0.0, -avatar.HEIGHT - 1.0, 0.0))
        assert placed(kind(health=25)).advance(below, 0.1) == []

    def test_one_just_under_the_feet_is_still_taken(self):
        """A pickup on a step you are standing over is a pickup you took."""
        over = match(where=(0.0, items.REACH_HEIGHT * 0.5, 0.0))
        assert placed(kind(health=25)).advance(over, 0.1)

    def test_one_well_below_the_feet_is_not(self):
        over = match(where=(0.0, items.REACH_HEIGHT + 1.0, 0.0))
        assert placed(kind(health=25)).advance(over, 0.1) == []

    def test_what_it_gave_actually_reaches_the_player(self):
        found = match(health=40)
        placed(kind(health=25)).advance(found, 0.1)
        assert found.combatant('player').health == 65

    def test_one_nobody_can_use_stays_on_the_floor(self):
        found = match(health=100)
        where = placed(kind(health=25))
        assert where.advance(found, 0.1) == []
        assert where.available()

    def test_the_dead_do_not_pick_things_up(self):
        found = match()
        found.kill('player', cause='lava')
        assert placed(kind(health=25)).advance(found, 0.1) == []

    def test_a_bot_picks_things_up_too(self):
        """Or a level's circuit only exists for one of the people in it."""
        found = arena.Arena(weapons=weapons.default_table())
        found.add('bot1', position=(0.0, 0.0, 0.0), bot=True, name='Bot')
        found.combatant('bot1').player.health = 10
        took = placed(kind(health=25)).advance(found, 0.1)
        assert [one.by for one in took] == ['bot1']

    def test_only_one_person_gets_it(self):
        found = match()
        found.add('bot1', position=(0.0, 0.0, 0.0), bot=True, name='Bot')
        for one in found.ids():
            found.combatant(one).player.health = 10
        assert len(placed(kind(health=25)).advance(found, 0.1)) == 1


class TestComingBack:

    def taken(self, respawn=10.0):
        found = match()
        where = placed(kind(health=25), respawn=respawn)
        where.advance(found, 0.1)
        return found, where

    def test_it_is_not_there_while_it_waits(self):
        _found, where = self.taken()
        where.advance(match(where=(50.0, 0.0, 50.0)), 5.0)
        assert where.available() == []

    def test_it_comes_back_when_the_wait_is_over(self):
        # Nobody standing on it, or it is taken again in the tick it returns
        # -- which is its own test, just below.
        _found, where = self.taken()
        where.advance(match(where=(50.0, 0.0, 50.0)), 11.0)
        assert len(where.available()) == 1

    def test_somebody_standing_on_it_gets_it_the_moment_it_returns(self):
        """Which is what makes camping an item respawn a decision rather than
        a lottery about where the frame boundaries fall."""
        found, where = self.taken()
        found.combatant('player').player.health = 10
        assert where.advance(found, 11.0)

    def test_an_item_with_no_wait_at_all_returns_at_once(self):
        found, where = self.taken(respawn=0.0)
        found.combatant('player').player.health = 10
        assert where.advance(found, 0.001)


class TestWhatItSays:
    """§11: the rules emit and presentation consumes."""

    def test_taking_one_is_on_the_event_stream(self):
        found = match()
        placed(kind(health=25, key='health', title='HEALTH')).advance(found, 0.1)
        said = [event for event in found.events
                if isinstance(event, arena.PickedUp)]
        assert said and (said[0].target, said[0].key, said[0].title) \
            == ('player', 'health', 'HEALTH')

    def test_the_event_says_where_it_was(self):
        """So a sound comes from the thing rather than from the player."""
        found = match(where=(1.0, 0.0, 0.0))
        placed(kind(health=25), where=(1.0, 0.0, 0.0)).advance(found, 0.1)
        said = [event for event in found.events
                if isinstance(event, arena.PickedUp)]
        assert said[0].point == pytest.approx((1.0, 0.0, 0.0))

    def test_it_reports_itself_to_the_overlay(self):
        found = match()
        where = placed(kind(health=25))
        assert where.describe() == {'items': 1, 'items waiting': 0}
        where.advance(found, 0.1)
        assert where.describe() == {'items': 1, 'items waiting': 1}


class TestTellingTheHealthPickupsApart:
    """One model, four colours — so the colours are the whole signal.

    A player decides whether to cross a room for a pickup from the other side
    of it, and at that range the shape of the thing is a smudge.  These pin the
    design rather than the numbers: four medikits that share a model must not
    share a colour, and must not be four shades of one colour either, which is
    what the placeholder boxes were.
    """

    HEALTH = ('health-small', 'health', 'health-large', 'health-mega')

    def health_kinds(self):
        table = items.default_table()
        return [table.by_key(key) for key in self.HEALTH]

    def test_every_health_pickup_is_the_medikit(self):
        for one in self.health_kinds():
            assert str(one.model) == items.MEDPACK['model']

    def test_they_are_placed_the_same_way(self):
        """Colour-only variants: anything else differing is a second model."""
        placings = {(float(one.modelScale),
                     tuple(float(value) for value in one.modelOffset))
                    for one in self.health_kinds()}
        assert len(placings) == 1

    def test_no_two_of_them_are_the_same_colour(self):
        colours = {tuple(float(value) for value in one.colour)
                   for one in self.health_kinds()}
        assert len(colours) == len(self.HEALTH)

    def test_they_are_far_enough_apart_to_read_across_a_room(self):
        """Not four brightnesses of one hue: some channel has to move a lot."""
        colours = [tuple(float(value) for value in one.colour)
                   for one in self.health_kinds()]
        for index, first in enumerate(colours):
            for second in colours[index + 1:]:
                apart = max(abs(a - b)
                            for a, b in zip(first, second, strict=True))
                assert apart >= 0.4, '%r and %r differ by only %.2f' % (
                    first, second, apart)

    def test_the_middling_one_is_the_red_cross(self):
        """The universal meaning is spent on the pickup a map places most."""
        red = items.default_table().by_key('health')
        assert red.colour[0] > 0.6 and red.colour[1] < 0.4 and red.colour[2] < 0.4

    def test_every_kind_names_art_that_is_actually_there(self):
        """Every pickup now has a model, so a typo is the only way to lose one.

        The box fallback is still the designed answer for a kind whose art has
        not been made (``twig_bb.game.item_look``, and there is a test for it
        over there) -- but nothing in the shipped table wants it any more, and
        a misspelt filename would quietly take a pickup back to a box rather
        than failing.
        """
        import os

        from twig_bb import art
        for kind in items.default_table().kinds:
            named = str(kind.model)
            assert named, 'no model for %r' % (str(kind.key),)
            assert os.path.exists(art.path_for(named)), named


class TestNothingHereReadsAClock:

    def test_the_module_imports_no_clock(self):
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(items))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or '')
        assert not imported & {'time', 'datetime'}

    def test_an_empty_level_is_harmless(self):
        assert items.Pickups([]).advance(match(), 1.0) == []


def test_a_level_can_say_how_many_it_holds():
    assert len(placed(kind(health=25))) == 1


class TestTakingAWeaponPutsItInHand:
    """Walking over a weapon arms you with it.

    A player who starts with a pistol (`PlayerState.starting`) collects the
    level's weapons as they go. Adding one to the bar and leaving the pistol in
    hand means the pickup that mattered most is the one that changed nothing
    you can see, and the number key becomes a step the player has to remember
    in the middle of a fight.

    **Better only.** A weapon already beaten by what is held does not take the
    hand: being downgraded mid-firefight by walking over a pistol is worse than
    not switching at all. Which beats which is the table's `slot` order, the
    same order the number keys and the weapon bar use.
    """

    def _walk_over(self, weapon_key, holding=None, table=None):
        table = table or weapons.default_table()
        made = match()
        player = made.combatant('player').player
        if holding is not None:
            player.give(holding)
            player.selected = holding
        placed(kind(key='w', title='W', weapon=weapon_key, ammo=5,
                    ammoType='rockets'),
               where=(0.0, 0.0, 0.0)).advance(made, 0.0, table=table)
        return player

    def test_a_better_weapon_takes_the_hand(self):
        player = self._walk_over('rocket', holding='pistol')
        assert player.selected == 'rocket'

    def test_it_is_held_as_well_as_selected(self):
        player = self._walk_over('rocket', holding='pistol')
        assert player.has('rocket')

    def test_a_worse_weapon_does_not_take_the_hand(self):
        """Walking over a pistol while holding a rocket launcher."""
        player = self._walk_over('pistol', holding='rocket')
        assert player.selected == 'rocket'
        assert player.has('pistol')

    def test_one_already_held_does_not_take_the_hand(self):
        """Its ammunition is still worth taking; the hand is not disturbed."""
        table = weapons.default_table()
        made = match()
        player = made.combatant('player').player
        player.give('rocket')
        player.give('shotgun')
        player.selected = 'rocket'
        placed(kind(key='w', title='W', weapon='shotgun', ammo=5,
                    ammoType='shells')).advance(made, 0.0, table=table)
        assert player.selected == 'rocket'

    def test_with_no_table_the_hand_is_left_alone(self):
        """Slot order is the table's; without one there is no better or worse."""
        made = match()
        player = made.combatant('player').player
        player.give('pistol')
        player.selected = 'pistol'
        placed(kind(key='w', title='W', weapon='rocket', ammo=5,
                    ammoType='rockets')).advance(made, 0.0)
        assert player.selected == 'pistol'
        assert player.has('rocket')

    def test_an_empty_hand_takes_whatever_arrives(self):
        table = weapons.default_table()
        made = match()
        player = made.combatant('player').player
        player.weapons = []
        player.selected = ''
        placed(kind(key='w', title='W', weapon='shotgun', ammo=5,
                    ammoType='shells')).advance(made, 0.0, table=table)
        assert player.selected == 'shotgun'

    def test_a_medikit_never_touches_the_hand(self):
        table = weapons.default_table()
        made = match()
        player = made.combatant('player').player
        player.give('pistol')
        player.selected = 'pistol'
        placed(kind(key='h', title='H', health=25)).advance(made, 0.0,
                                                            table=table)
        assert player.selected == 'pistol'
