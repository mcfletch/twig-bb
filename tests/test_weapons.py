"""The weapon table, and the reticule each weapon brings with it.

The table is declared data, so nearly all of this is reading fields back; what
is worth pinning is the arithmetic that turns a cone of spread in degrees into
a gap in pixels, and the selection rules the number keys and the wheel drive.
"""

from __future__ import annotations

import math

import pytest

from twitchoglc import weapons


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


class TestTheStandInModels:
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

    def test_the_author_is_linked_and_the_licence_named(self):
        text = self.credits()
        assert 'https://3dmodelscc0.itch.io/' in text
        assert 'CC0' in text

    def test_the_models_are_small_enough_to_belong_in_a_repository(self):
        """Source art carries 2048px maps; a stand-in has no business doing so."""
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
