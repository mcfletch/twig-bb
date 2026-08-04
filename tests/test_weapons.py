"""The weapon table, and the reticule each weapon brings with it.

The table is declared data, so nearly all of this is reading fields back; what
is worth pinning is the arithmetic that turns a cone of spread in degrees into
a gap in pixels, and the selection rules the number keys and the wheel drive.
"""

from __future__ import annotations

import math

import pytest

from twig_bb import weapons


class TestTable:
    def test_the_stand_in_loadout_is_not_empty(self):
        assert weapons.default_table().weapons

    def test_a_weapon_is_found_by_its_key(self):
        table = weapons.default_table()
        assert table.by_key('pistol').key == 'pistol'

    def test_an_unknown_key_is_not_an_error(self):
        assert weapons.default_table().by_key('lightsabre') is None

    def test_a_weapon_is_found_by_the_number_key_it_sits_on(self):
        table = weapons.default_table()
        first = table.by_slot(1)
        assert first is not None
        assert first.slot == 1

    def test_every_weapon_has_a_slot_of_its_own(self):
        slots = [int(weapon.slot) for weapon in weapons.default_table().weapons]
        assert len(slots) == len(set(slots))

    def test_every_weapon_names_a_reticule(self):
        for weapon in weapons.default_table().weapons:
            assert weapon.crosshair is not None

    def test_every_weapon_names_an_ammunition_type(self):
        for weapon in weapons.default_table().weapons:
            assert str(weapon.ammoType)

    def test_the_stand_in_weapons_name_the_model_that_ships_with_us(self):
        """The model is data, so the commissioned asset is a table edit."""
        for weapon in weapons.default_table().weapons:
            assert str(weapon.model).endswith('.glb')

    def test_the_stand_in_model_is_actually_there(self):
        import os
        for weapon in weapons.default_table().weapons:
            assert os.path.exists(weapons.model_path(weapon)), weapon.key


class TestSpread:
    """Degrees of cone half-angle into pixels on the screen."""

    def test_no_spread_is_no_extra_gap(self):
        assert weapons.spread_pixels(0.0, 1080, math.radians(90)) == 0

    def test_a_wider_cone_is_a_wider_gap(self):
        narrow = weapons.spread_pixels(1.0, 1080, math.radians(90))
        wide = weapons.spread_pixels(4.0, 1080, math.radians(90))
        assert wide > narrow > 0

    def test_half_the_field_of_view_reaches_the_edge_of_the_screen(self):
        """The projection is the renderer's, so this is checkable exactly."""
        field = math.radians(90)
        pixels = weapons.spread_pixels(45.0, 1080, field)
        assert pixels == pytest.approx(540, rel=0.01)

    def test_a_taller_window_gives_the_same_angle_more_pixels(self):
        field = math.radians(90)
        assert (weapons.spread_pixels(5.0, 2160, field)
                == pytest.approx(weapons.spread_pixels(5.0, 1080, field) * 2,
                                 rel=0.01))

    def test_a_weapon_grows_from_its_resting_cone_to_its_widest(self):
        weapon = weapons.Weapon(restSpread=1.0, maxSpread=5.0)
        assert weapon.spread_at(0.0) == pytest.approx(1.0)
        assert weapon.spread_at(1.0) == pytest.approx(5.0)
        assert weapon.spread_at(0.5) == pytest.approx(3.0)

    def test_a_fraction_outside_the_range_is_clamped(self):
        weapon = weapons.Weapon(restSpread=1.0, maxSpread=5.0)
        assert weapon.spread_at(-3.0) == pytest.approx(1.0)
        assert weapon.spread_at(9.0) == pytest.approx(5.0)


class TestDamageAtRange:
    """What a hit costs is a function of how far it travelled.

    Three numbers say it -- how far full damage carries, how far it takes to
    fade, and what is left at the end -- because a weapon's *range* is most of
    what tells it apart from the weapon beside it, and a table of flat numbers
    made every hitscan weapon the same weapon at a different rate of fire.
    """

    def test_a_weapon_that_declares_no_fade_does_not_fade(self):
        """The default, so a weapon has range only when it says so."""
        weapon = weapons.Weapon(damage=20.0)
        assert weapon.damage_at(0.0) == pytest.approx(20.0)
        assert weapon.damage_at(300.0) == pytest.approx(20.0)

    def test_inside_the_full_range_it_is_undiminished(self):
        weapon = weapons.Weapon(damage=50.0, fullRange=6.0, fadeRange=30.0,
                                fadedDamage=10.0)
        assert weapon.damage_at(0.0) == pytest.approx(50.0)
        assert weapon.damage_at(6.0) == pytest.approx(50.0)

    def test_beyond_the_fade_range_it_is_whatever_is_left(self):
        weapon = weapons.Weapon(damage=50.0, fullRange=6.0, fadeRange=30.0,
                                fadedDamage=10.0)
        assert weapon.damage_at(30.0) == pytest.approx(10.0)
        assert weapon.damage_at(400.0) == pytest.approx(10.0)

    def test_between_them_it_falls_evenly(self):
        weapon = weapons.Weapon(damage=50.0, fullRange=6.0, fadeRange=30.0,
                                fadedDamage=10.0)
        assert weapon.damage_at(18.0) == pytest.approx(30.0)

    def test_nothing_left_at_the_far_end_is_allowed(self):
        """A shotgun: past its reach the pellets arrive and cost nothing."""
        weapon = weapons.Weapon(damage=14.0, fullRange=6.0, fadeRange=22.0,
                                fadedDamage=0.0)
        assert weapon.damage_at(25.0) == 0.0

    def test_a_fade_that_ends_before_it_starts_is_no_fade(self):
        """A table half-edited must not quietly invert the curve."""
        weapon = weapons.Weapon(damage=50.0, fullRange=30.0, fadeRange=6.0,
                                fadedDamage=10.0)
        assert weapon.damage_at(50.0) == pytest.approx(50.0)


class TestHowTheLoadoutIsMeantToPlay:
    """The design, stated as what a fight costs rather than as field values.

    Each of these is a sentence somebody could say about the weapon -- *the
    shotgun kills in one up close and does nothing across the level* -- and
    the numbers in the table are whatever makes them true.  Written this way
    round because it is the sentences that are the design; retuning is meant
    to break a claim about the game, not an assertion that 34 is still 34.
    """

    def hits_to_kill(self, key, metres):
        weapon = weapons.default_table().by_key(key)
        each = weapon.damage_at(metres) * max(1, int(weapon.pellets))
        return math.inf if each <= 0 else math.ceil(100.0 / each)

    def test_a_pistol_kills_in_two_at_arms_length(self):
        assert self.hits_to_kill('pistol', 2.0) <= 2

    def test_a_pistol_kills_in_three_across_a_room(self):
        assert self.hits_to_kill('pistol', 14.0) <= 3

    def test_a_pistol_takes_half_a_dozen_across_the_level(self):
        assert 5 <= self.hits_to_kill('pistol', 45.0) <= 6

    def test_a_shotgun_kills_in_one_at_close_quarters(self):
        """Every pellet lands at that range: the cone is centimetres wide."""
        assert self.hits_to_kill('shotgun', 3.0) == 1

    def test_a_shotgun_is_a_handful_of_shots_at_middle_distance(self):
        """Before the cone is counted, which takes more of them still."""
        assert 3 <= self.hits_to_kill('shotgun', 14.0) <= 5

    def test_a_shotgun_does_nothing_at_all_across_the_level(self):
        assert weapons.default_table().by_key('shotgun').damage_at(30.0) == 0.0

    def test_a_rifle_kills_in_one_at_any_range_it_can_see(self):
        """Its whole argument: the shot is hard to line up and it ends the fight."""
        for metres in (2.0, 40.0, 150.0, 390.0):
            assert self.hits_to_kill('rifle', metres) == 1


class TestLookingThroughTheRifle:
    """The zoom, which is the rifle's other half.

    A weapon that kills in one at any range has to be hard to *aim* or it is
    the only weapon anybody carries; at four hundred metres a body is a pixel
    or two, and without something to look through the rifle is not accurate,
    it is a lottery.  The field of view is the weapon's own number, so the one
    weapon that has a scope is the one weapon the table says has one.
    """

    def test_the_rifle_narrows_the_view(self):
        rifle = weapons.default_table().by_key('rifle')
        assert 0.0 < float(rifle.zoomFieldOfView) < 45.0

    def test_nothing_else_does(self):
        for weapon in weapons.default_table().weapons:
            if str(weapon.key) != 'rifle':
                assert float(weapon.zoomFieldOfView) == 0.0, weapon.key

    def test_zooming_with_the_rifle_up_narrows_the_frustum(self):
        rifle = weapons.default_table().by_key('rifle')
        wide = math.radians(90.0)
        assert weapons.field_of_view(rifle, True, wide) < wide

    def test_not_zooming_leaves_the_view_alone(self):
        rifle = weapons.default_table().by_key('rifle')
        wide = math.radians(90.0)
        assert weapons.field_of_view(rifle, False, wide) == wide

    def test_zooming_with_anything_else_up_does_nothing(self):
        """So the button is dead in the hand rather than wrong in the hand."""
        wide = math.radians(90.0)
        for key in ('pistol', 'shotgun', 'rocket', 'grenade'):
            weapon = weapons.default_table().by_key(key)
            assert weapons.field_of_view(weapon, True, wide) == wide

    def test_holding_nothing_at_all_is_the_wide_view(self):
        wide = math.radians(90.0)
        assert weapons.field_of_view(None, True, wide) == wide


class TestReticule:
    def test_the_reticule_widens_with_the_weapon_s_spread(self):
        table = weapons.default_table()
        weapon = table.by_slot(1)
        tight = weapons.reticule_spread(weapon, 0.0, 1080, math.radians(90))
        loose = weapons.reticule_spread(weapon, 1.0, 1080, math.radians(90))
        assert loose > tight

    def test_a_weapon_that_does_not_spread_never_widens(self):
        weapon = weapons.Weapon(restSpread=0.0, maxSpread=0.0)
        assert weapons.reticule_spread(weapon, 1.0, 1080, math.radians(90)) == 0


class TestTheWeaponModels:
    """A weapon you switch to that looks identical reads as a broken key."""

    def test_no_two_weapons_share_a_model(self):
        table = weapons.default_table()
        models = [str(weapon.model) for weapon in table.weapons]
        assert len(models) == len(set(models))

    def test_each_of_them_is_on_disk(self):
        import os
        for weapon in weapons.default_table().weapons:
            assert os.path.exists(weapons.model_path(weapon)), weapon.key

    def test_they_are_held_at_a_plausible_distance(self):
        """Inside the near plane is invisible; a metre away is not in hand."""
        for weapon in weapons.default_table().weapons:
            forward = -float(weapon.modelOffset[2])
            assert 0.1 < forward < 1.0, weapon.key


class TestEveryModelIsCredited:
    """The rule from CREDITS.md, made a test rather than a good intention.

    §10 generates an acknowledgements screen, and art that arrives without its
    author named is art that screen will be silently wrong about.  Cheaper to
    fail here than to ship an incomplete notice.
    """

    def credits(self):
        import os
        path = os.path.join(weapons.ASSETS, 'weapons', 'CREDITS.md')
        with open(path, encoding='utf-8') as source:
            return source.read()

    def shipped_models(self):
        import glob
        import os
        return sorted(glob.glob(os.path.join(weapons.ASSETS, 'weapons',
                                             '*.glb')))

    def test_there_is_art_to_credit(self):
        assert self.shipped_models()

    def test_every_shipped_model_is_named_in_the_credits(self):
        import os
        text = self.credits()
        for path in self.shipped_models():
            assert os.path.basename(path) in text, os.path.basename(path)

    def test_every_model_the_table_names_is_credited(self):
        import os
        text = self.credits()
        for weapon in weapons.default_table().weapons:
            assert os.path.basename(str(weapon.model)) in text

    def drawn_models(self):
        """Every model in this directory something asks to be drawn."""
        import os
        from twig_bb import projectiles
        named = [str(weapon.model) for weapon in weapons.default_table().weapons]
        named += [str(kind.model) for kind in projectiles.default_table().kinds]
        return {os.path.basename(name) for name in named if name}

    def test_no_model_ships_that_nothing_draws(self):
        """Art nobody draws is weight in the repository and a licence to check.

        The two tables above are the whole of what asks for a weapon model --
        what is held, and what is thrown -- so a file here that neither names
        is one to delete rather than to carry.
        """
        import os
        shipped = {os.path.basename(path) for path in self.shipped_models()}
        assert shipped == self.drawn_models()

    def test_the_licence_and_the_source_are_named(self):
        text = self.credits()
        assert 'BSD' in text
        assert 'arsenal.py' in text

    def test_the_models_are_small_enough_to_belong_in_a_repository(self):
        """Source art carries 2048px maps; a game model has no business doing so."""
        import os
        for path in self.shipped_models():
            megabytes = os.path.getsize(path) / 1e6
            assert megabytes < 1.5, '%s is %.1f MB' % (os.path.basename(path),
                                                       megabytes)

    def test_each_model_carries_whatever_textures_it_needs(self):
        """Self-contained .glb: no sidecar files to lose on the way in."""
        import glob
        import os
        loose = glob.glob(os.path.join(weapons.ASSETS, 'weapons', '*', '*'))
        assert loose == [], 'a model depends on files beside it: %r' % (loose,)
