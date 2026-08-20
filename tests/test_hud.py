"""The game HUD: what goes where, what colour it is, and what it says.

All of it is the layout of a viewport plus a game state, so none of it needs a
window -- which is the point of building it this way.
"""

from __future__ import annotations

import math

import pytest

from OpenGLContext.ui.metrics import FontMetrics

from twig_bb import hud, weapons
from twig_bb.player import PlayerState


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

    def test_losing_health_flashes_the_meter(self, table, player):
        """A number that changes silently in a corner nobody is looking at."""
        screen = hud.GameHUD(table)
        screen.update(player, now=0.0)
        player.take_damage(25)
        screen.update(player, now=1.0)
        screen.health.tick(1.0)
        assert screen.health.flashAlpha() > 0.0

    def test_losing_armour_flashes_its_own_meter(self, table, player):
        screen = hud.GameHUD(table)
        player.give_armour(80)
        screen.update(player, now=0.0)
        player.take_damage(40)
        screen.update(player, now=1.0)
        screen.armour.tick(1.0)
        assert screen.armour.flashAlpha() > 0.0

    def test_healing_does_not_flash(self, table, player):
        """A pickup is something the player did on purpose and already knows."""
        screen = hud.GameHUD(table)
        player.take_damage(50)
        screen.update(player, now=0.0)
        screen.health.tick(0.0)
        player.heal(30)
        screen.update(player, now=10.0)
        screen.health.tick(10.0)
        assert screen.health.flashAlpha() == 0.0

    def test_standing_still_does_not_flash(self, table, player):
        screen = hud.GameHUD(table)
        screen.update(player, now=0.0)
        screen.update(player, now=1.0)
        screen.health.tick(1.0)
        assert screen.health.flashAlpha() == 0.0


class TestBeingKilled:
    def test_a_death_notice_names_what_did_it_and_counts_down(self, screen):
        screen.died('Fragged by Bot 1', respawn_in=1.2)
        assert screen.dead.visible
        assert screen.deathcause.value == 'Fragged by Bot 1'
        assert '1.2' in screen.respawn.value

    def test_the_notice_is_down_until_something_puts_it_up(self, screen):
        assert not screen.dead.visible

    def test_coming_back_takes_it_down_and_clears_the_marks(self, screen):
        screen.damage.hurt(bearing=0.0, intensity=1.0, now=0.0)
        screen.died('Fragged by Bot 1', respawn_in=0.0)
        screen.revived()
        assert not screen.dead.visible
        assert not screen.damage.marks

    def test_a_respawn_already_due_says_so_rather_than_counting_zero(self, screen):
        screen.died('You died', respawn_in=0.0)
        assert '0.0' not in screen.respawn.value


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

    def test_each_slot_is_labelled_with_its_number_key(self, screen, table):
        assert [slot.label for slot in screen.weaponbar.slots] \
            == [str(int(weapon.slot)) for weapon in table.weapons]

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


class TestTheWeaponBarFitting:
    """Five weapons must not run off both ends of a narrow window.

    The bar's job is *which number key do I press*, and a bar whose ends are
    clipped answers that for the middle three weapons only.
    """

    def screen_at(self, table, player, metrics, width):
        made = hud.GameHUD(table)
        made.update(player, now=0.0)
        made.layout((width, 720), metrics)
        return made

    def test_a_wide_window_shows_every_title(self, table, player, metrics):
        screen = self.screen_at(table, player, metrics, 1920)
        assert 'SHOTGUN' in screen.weaponbar.slotText(screen.weaponbar.slots[1])

    def test_a_narrow_window_drops_to_the_numbers(self, table, player, metrics):
        screen = self.screen_at(table, player, metrics, 320)
        assert screen.weaponbar.slotText(screen.weaponbar.slots[1]) == '2'

    def test_it_still_fits_when_it_has_dropped_to_numbers(self, table, player,
                                                          metrics):
        """Measured where it was placed: `natural_size` with no room named
        answers what it wants on a screen with room, which is a different
        question."""
        screen = self.screen_at(table, player, metrics, 320)
        assert screen.weaponbar.rect.width <= 320
        assert screen.weaponbar.rect.x >= 0

    def test_the_number_keys_survive_however_narrow_it_gets(self, table, player,
                                                            metrics):
        """The one thing on the bar a player cannot work out for themselves."""
        screen = self.screen_at(table, player, metrics, 64)
        assert [screen.weaponbar.slotText(slot)
                for slot in screen.weaponbar.slots] == ['1', '2', '3', '4', '5']

    def test_a_bar_nobody_has_measured_shows_its_titles(self, table):
        """Before a layout there is no room to fit into, so nothing is dropped."""
        bar = hud.WeaponBar()
        bar.slots = [hud.WeaponSlot('1', 'PISTOL', 'pistol')]
        assert bar.slotText(bar.slots[0]) == '1 PISTOL'


class TestOneClock:
    """Everything on the HUD fades against the clock the layer is ticked with.

    That clock is the engine's own time source, which is what the context ticks
    the layers with and what a recorded session replaces
    (:mod:`OpenGLContext.telemetry`). A game that read a clock of its own would
    compute every fade from the difference between two of them -- which is
    about fifty years, and looks on screen like a damage wash and a hit mark
    that never go away -- and would draw a replayed session against this
    machine's clock rather than against the recorded one.
    """

    def tick(self, screen, at):
        """Advance the layer the way the context does."""
        screen.tick(at)

    def test_the_hud_clock_is_the_engine_s(self):
        from OpenGLContext.events import systemtime
        previous = systemtime.setTimeSource(lambda: 1234.5)
        try:
            assert hud.now() == 1234.5
        finally:
            systemtime.setTimeSource(previous)

    def test_a_hit_mark_put_up_on_that_clock_goes_away_again(self, screen):
        at = hud.now()
        screen.hit(at)
        self.tick(screen, at + 0.05)
        assert screen.crosshair.hitMarks(screen.metrics)
        self.tick(screen, at + float(screen.crosshair.hitDuration) + 0.1)
        assert not screen.crosshair.hitMarks(screen.metrics)

    def test_a_damage_wash_put_up_on_that_clock_fades_out(self, screen,
                                                          metrics):
        at = hud.now()
        screen.damage.hurt(bearing=0.0, intensity=1.0, now=at)
        self.tick(screen, at + 0.05)
        assert screen.damage.bands(metrics)
        self.tick(screen, at + float(screen.damage.duration) + 0.1)
        assert not screen.damage.bands(metrics)

    def test_a_wash_is_never_stronger_than_it_was_asked_to_be(self, screen,
                                                              metrics):
        """The symptom of two clocks: an alpha of a hundred million."""
        at = hud.now()
        screen.damage.hurt(bearing=0.0, intensity=1.0, now=at)
        self.tick(screen, at)
        assert all(colour[3] <= 1.0
                   for _rect, colour in screen.damage.bands(metrics))

    def test_a_meter_flash_on_that_clock_fades_out(self, screen, player):
        at = hud.now()
        screen.health.flash(at)
        self.tick(screen, at + 0.05)
        assert screen.health.flashAlpha() > 0.0
        self.tick(screen, at + float(screen.health.flashDuration) + 0.1)
        assert screen.health.flashAlpha() == 0.0


class TestKnowingWhetherYouAreWinning:
    """A player who cannot tell is playing a different game from the one the
    frag limit describes.

    Two readings and they answer different questions.  The corner says *where
    am I* and has to be there all the time, because nobody holds a key to find
    out something they want to know continuously.  The board says *against
    whom*, and is worth a key because it is read between fights.
    """

    def test_the_corner_shows_the_frags(self, screen):
        screen.score(frags=7, limit=15)
        assert '7' in screen.frags.value

    def test_it_shows_how_far_there_is_left_to_go(self, screen):
        """"Seven" means nothing on its own: what a player is deciding is
        whether to press or to go and find armour."""
        screen.score(frags=7, limit=15)
        assert '15' in screen.frags.value

    def test_a_match_with_no_frag_limit_shows_the_count_alone(self, screen):
        screen.score(frags=7, limit=0)
        assert screen.frags.value == '7'

    def test_one_frag_from_the_end_is_worth_colouring(self, screen):
        screen.score(frags=14, limit=15)
        assert screen.frags.critical

    def test_the_middle_of_a_match_is_not(self, screen):
        screen.score(frags=3, limit=15)
        assert not screen.frags.critical

    def test_the_corner_is_always_up(self, screen):
        assert screen.frags in screen.children
        assert screen.frags.visible

    def test_the_board_is_not_up_until_it_is_asked_for(self, screen):
        assert not screen.standings.visible

    def test_asking_for_it_puts_every_row_up(self, screen):
        screen.scoreboard(['       FRAGS DEATHS', 'You        7      2',
                           'Bot 1      2      7'])
        assert screen.standings.visible
        assert len(screen.standings.children) == 3

    def test_the_rows_are_shown_as_given(self, screen):
        """`game.scoreboard_lines` has already made the columns line up, and a
        HUD that re-tabulated them would be a second opinion about one table."""
        screen.scoreboard(['You        7      2'])
        assert screen.standings.children[0].value == 'You        7      2'

    def test_taking_it_down_hides_it(self, screen):
        screen.scoreboard(['You        7      2'])
        screen.hide_scoreboard()
        assert not screen.standings.visible

    def test_taking_it_down_twice_is_one_key(self, screen):
        screen.hide_scoreboard()
        screen.hide_scoreboard()
        assert not screen.standings.visible

    def test_an_empty_board_does_not_go_up(self, screen):
        screen.scoreboard([])
        assert not screen.standings.visible

    def test_it_is_rebuilt_rather_than_accumulated(self, screen):
        screen.scoreboard(['a', 'b', 'c'])
        screen.scoreboard(['a'])
        assert len(screen.standings.children) == 1
