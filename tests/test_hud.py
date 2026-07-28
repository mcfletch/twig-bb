"""The game HUD: what goes where, what colour it is, and what it says.

All of it is the layout of a viewport plus a game state, so none of it needs a
window -- which is the point of building it this way.
"""

from __future__ import annotations

import math

import pytest

from OpenGLContext.ui.metrics import FontMetrics

from twitchoglc import hud, weapons
from twitchoglc.player import PlayerState


@pytest.fixture
def metrics():
    return FontMetrics(char_width=8, char_height=16, line_gap=2)


@pytest.fixture
def table():
    return weapons.default_table()


@pytest.fixture
def player(table):
    return PlayerState.starting(table)


@pytest.fixture
def screen(table, player, metrics):
    made = hud.GameHUD(table)
    made.update(player, now=0.0, viewport=(1280, 720),
                field_of_view=math.radians(90))
    made.layout((1280, 720), metrics)
    return made


def colour(value):
    return tuple(float(component) for component in value)


class TestArrangement:
    def test_the_reticule_is_in_the_middle(self, screen):
        assert screen.crosshair.rect.centre == (640, 360)

    def test_health_and_armour_sit_in_the_bottom_left(self, screen):
        assert screen.vitals.rect.x < 640
        assert screen.vitals.rect.y < 360

    def test_ammunition_sits_in_the_bottom_right(self, screen):
        assert screen.ammo.rect.right > 640
        assert screen.ammo.rect.y < 360

    def test_messages_run_along_the_top(self, screen):
        assert screen.messages.rect.top > 360

    def test_nothing_on_the_hud_takes_the_pointer(self, screen):
        for x, y in ((640, 360), (20, 20), (1260, 700)):
            assert screen.widget_at(x, y) is None

    def test_it_lays_out_again_for_a_different_window(self, screen, metrics):
        screen.layout((800, 600), metrics)
        assert screen.crosshair.rect.centre == (400, 300)


class TestVitals:
    def test_the_meters_show_what_the_player_has(self, screen, player):
        assert screen.health.value == player.health
        assert screen.armour.value == player.armour

    def test_a_wounded_player_reads_low_and_then_critical(self, table, player,
                                                          metrics):
        screen = hud.GameHUD(table)
        skin = screen.activeSkin()
        player.health = 40
        screen.update(player, now=0.0)
        assert colour(screen.health.stateColour(skin)) == colour(skin.hudWarn)
        player.health = 10
        screen.update(player, now=0.0)
        assert colour(screen.health.stateColour(skin)) \
            == colour(skin.hudCritical)

    def test_armour_is_hidden_until_there_is_some(self, screen, player):
        assert not screen.armour.visible
        player.give_armour(50)
        screen.update(player, now=0.0)
        assert screen.armour.visible


class TestAmmunition:
    def test_the_readout_names_the_weapon_and_its_count(self, screen, player):
        assert 'PISTOL' in screen.ammo.text()
        assert str(player.ammo['bullets']) in screen.ammo.text()

    def test_running_low_is_marked_critical(self, screen, player):
        player.ammo['bullets'] = 2
        screen.update(player, now=0.0)
        assert screen.ammo.critical

    def test_a_full_pouch_is_not(self, screen, player):
        assert not screen.ammo.critical


class TestWeaponBar:
    def test_it_shows_every_weapon_in_the_table(self, screen, table):
        assert len(screen.weaponbar.slots) == len(table.weapons)

    def test_a_weapon_that_is_not_held_is_dimmed(self, screen, player):
        skin = screen.activeSkin()
        held, missing = screen.weaponbar.slots[0], screen.weaponbar.slots[1]
        assert colour(screen.weaponbar.slotColour(held, skin)) \
            != colour(screen.weaponbar.slotColour(missing, skin))

    def test_the_selected_weapon_is_marked_out_from_the_rest(self, screen,
                                                             player):
        skin = screen.activeSkin()
        player.give('shotgun')
        screen.update(player, now=0.0)
        selected, other = screen.weaponbar.slots[0], screen.weaponbar.slots[1]
        assert selected.selected and not other.selected
        assert colour(screen.weaponbar.slotColour(selected, skin)) \
            != colour(screen.weaponbar.slotColour(other, skin))

    def test_each_slot_is_labelled_with_its_number_key(self, screen):
        assert [slot.label for slot in screen.weaponbar.slots] \
            == ['1', '2', '3']

    def test_the_bar_grows_with_the_number_of_weapons(self, screen, metrics):
        wide = screen.weaponbar.natural_size(metrics)[0]
        screen.weaponbar.slots = screen.weaponbar.slots[:1]
        assert screen.weaponbar.natural_size(metrics)[0] < wide


class TestReticule:
    def test_the_selected_weapon_s_reticule_is_the_one_drawn(self, screen,
                                                              table):
        assert screen.crosshair.shape == table.by_key('pistol').crosshair.shape

    def test_switching_weapon_switches_the_reticule(self, screen, player,
                                                    table, metrics):
        player.give('shotgun')
        player.select('shotgun')
        screen.update(player, now=0.0)
        assert screen.crosshair.shape == table.by_key('shotgun').crosshair.shape

    def test_firing_opens_the_reticule(self, screen, player, metrics):
        tight = float(screen.crosshair.spread)
        player.fired(now=1.0)
        screen.update(player, now=1.01, viewport=(1280, 720),
                      field_of_view=math.radians(90))
        assert float(screen.crosshair.spread) > tight

    def test_a_confirmed_hit_marks_the_reticule(self, screen, metrics):
        assert screen.crosshair.hitMarks(metrics) == []
        screen.hit(now=5.0)
        screen.tick(5.05)
        assert screen.crosshair.hitMarks(metrics)


class TestMessages:
    def test_a_pickup_is_announced(self, screen):
        screen.post('PICKED UP A SHOTGUN', now=0.0)
        assert [text for text, _colour in screen.messages.entries(0.5)] \
            == ['PICKED UP A SHOTGUN']

    def test_it_goes_away_on_its_own(self, screen):
        screen.post('PICKED UP A SHOTGUN', now=0.0)
        screen.tick(30.0)
        assert screen.messages.entries(30.0) == []


class TestDeveloperInformation:
    def test_nothing_developer_facing_is_on_the_game_hud(self, screen):
        """§3: the two must not drift back together."""
        from OpenGLContext.ui.debugoverlay import DebugPanel
        assert not [child for child in screen.walk()
                    if isinstance(child, DebugPanel)]


class TestCrowding:
    """The bottom of the screen holds three things; they must not collide."""

    def viewport(self, table, player, metrics, size):
        made = hud.GameHUD(table)
        made.update(player, now=0.0, viewport=size,
                    field_of_view=math.radians(90))
        made.layout(size, metrics)
        return made

    @pytest.mark.parametrize('size', [(1920, 1080), (1280, 720), (640, 480)])
    def test_the_weapon_bar_clears_the_meters_and_the_ammunition(
            self, table, player, metrics, size):
        screen = self.viewport(table, player, metrics, size)
        for other in (screen.vitals, screen.ammo):
            assert not screen.weaponbar.rect.intersects(other.rect), (
                'the weapon bar overlaps %r at %s' % (other.name or other, size))

    def test_the_meters_clear_the_ammunition(self, table, player, metrics):
        screen = self.viewport(table, player, metrics, (640, 480))
        assert not screen.vitals.rect.intersects(screen.ammo.rect)

    def test_the_reticule_is_clear_of_everything(self, table, player, metrics):
        screen = self.viewport(table, player, metrics, (640, 480))
        for other in (screen.vitals, screen.ammo, screen.weaponbar,
                      screen.messages):
            assert not screen.crosshair.rect.intersects(other.rect)
