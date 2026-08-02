"""What the player gets back when a fight happens to them.

The arithmetic of it: which way a hit came from, how hard it was, and what the
HUD is told.  None of this needs a window, which is what lets "being shot from
behind lights the bottom of the screen" be a test rather than a thing somebody
has to go and check by playing.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from OpenGLContext.ui.metrics import FontMetrics

from twitchoglc import arena, feedback, game, hud, weapons


@pytest.fixture
def metrics():
    return FontMetrics(char_width=8, char_height=16, line_gap=2)


@pytest.fixture
def match():
    made = arena.Arena(weapons=weapons.default_table(), fragLimit=15,
                       timeLimit=10.0)
    made.add(game.PLAYER_ID, position=(0.0, 0.0, 0.0), name='You')
    made.add('bot1', position=(10.0, 0.0, 0.0), bot=True, name='Bot 1')
    return made


@pytest.fixture
def screen(metrics):
    made = hud.GameHUD(weapons.default_table())
    made.layout((1280, 720), metrics)
    return made


@pytest.fixture
def player(match):
    return feedback.Presenter(match, hud=None)


class TestWhichWayItCameFrom:
    """A bearing: radians from straight ahead, positive to the right."""

    #: Looking down -Z, which is where a camera looks by default.
    ahead = (0.0, 0.0, -1.0)

    def bearing(self, at, forward=None):
        return feedback.bearing_to((0.0, 0.0, 0.0),
                                   self.ahead if forward is None else forward,
                                   at)

    def test_straight_ahead_is_zero(self):
        assert self.bearing((0.0, 0.0, -5.0)) == pytest.approx(0.0, abs=1e-9)

    def test_directly_behind_is_half_a_turn(self):
        assert abs(self.bearing((0.0, 0.0, 5.0))) == pytest.approx(math.pi)

    def test_to_the_right_is_a_quarter_turn_right(self):
        assert self.bearing((5.0, 0.0, 0.0)) == pytest.approx(math.pi / 2)

    def test_to_the_left_is_a_quarter_turn_left(self):
        assert self.bearing((-5.0, 0.0, 0.0)) == pytest.approx(-math.pi / 2)

    def test_height_does_not_change_the_bearing(self):
        """A shooter on a balcony is still to the right, not above-and-right.

        The indicator says which way to *turn*, and turning is about one axis.
        """
        assert self.bearing((5.0, 40.0, 0.0)) == pytest.approx(math.pi / 2)

    def test_the_bearing_follows_the_camera(self):
        """Turning to face a shooter brings the mark round to the front."""
        assert self.bearing((5.0, 0.0, 0.0), forward=(1.0, 0.0, 0.0)) \
            == pytest.approx(0.0, abs=1e-9)

    def test_somebody_standing_on_the_camera_is_straight_ahead(self):
        """No direction to give rather than an arbitrary one."""
        assert self.bearing((0.0, 0.0, 0.0)) == 0.0

    def test_a_camera_looking_nowhere_gives_no_direction(self):
        assert self.bearing((5.0, 0.0, 0.0), forward=(0.0, 0.0, 0.0)) == 0.0


class TestBeingShot:

    def show(self, presenter, match, camera=(0.0, 0.0, 0.0),
             forward=(0.0, 0.0, -1.0), now=0.0):
        presenter.show(match.drain(), camera=camera, forward=forward, now=now)

    def test_taking_damage_marks_the_screen(self, match, screen):
        presenter = feedback.Presenter(match, hud=screen)
        match.combatant('bot1').position = np.array([0.0, 0.0, -10.0])
        match.damage(game.PLAYER_ID, 30, by='bot1')
        self.show(presenter, match)
        assert screen.damage.marks

    def test_the_mark_points_at_whoever_fired(self, match, screen):
        presenter = feedback.Presenter(match, hud=screen)
        match.combatant('bot1').position = np.array([0.0, 0.0, 10.0])
        match.damage(game.PLAYER_ID, 30, by='bot1')
        self.show(presenter, match)
        assert abs(screen.damage.marks[0].bearing) == pytest.approx(math.pi)

    def test_a_harder_hit_marks_harder(self, match, screen):
        presenter = feedback.Presenter(match, hud=screen)
        match.damage(game.PLAYER_ID, 10, by='bot1')
        self.show(presenter, match)
        soft = screen.damage.marks[-1].intensity
        match.damage(game.PLAYER_ID, 60, by='bot1')
        self.show(presenter, match)
        assert screen.damage.marks[-1].intensity > soft

    def test_damage_to_somebody_else_does_not_mark_our_screen(self, match, screen):
        presenter = feedback.Presenter(match, hud=screen)
        match.damage('bot1', 30, by=game.PLAYER_ID)
        self.show(presenter, match)
        assert not screen.damage.marks

    def test_dying_to_the_map_still_marks_the_screen(self, match, screen):
        """Lava has no position; the hit is still felt, just not from anywhere."""
        presenter = feedback.Presenter(match, hud=screen)
        match.damage(game.PLAYER_ID, 30)
        self.show(presenter, match)
        assert screen.damage.marks

    def test_landing_a_shot_marks_the_reticule(self, match, screen):
        presenter = feedback.Presenter(match, hud=screen)
        match.impact(point=(1, 0, 0), normal=(-1, 0, 0), target='bot1',
                     by=game.PLAYER_ID)
        self.show(presenter, match, now=5.0)
        assert screen.crosshair._hit_at == 5.0

    def test_hitting_a_wall_does_not_mark_the_reticule(self, match, screen):
        """The mark means "you hit somebody"; a wall would make it a lie."""
        presenter = feedback.Presenter(match, hud=screen)
        match.impact(point=(1, 0, 0), normal=(-1, 0, 0), surface='stone',
                     by=game.PLAYER_ID)
        self.show(presenter, match)
        assert screen.crosshair._hit_at is None

    def test_a_bot_hitting_another_bot_does_not_mark_our_reticule(self, match,
                                                                  screen):
        presenter = feedback.Presenter(match, hud=screen)
        match.impact(point=(1, 0, 0), normal=(-1, 0, 0), target=game.PLAYER_ID,
                     by='bot1')
        self.show(presenter, match)
        assert screen.crosshair._hit_at is None


class TestBeingKilled:

    def show(self, presenter, match, now=0.0):
        presenter.show(match.drain(), camera=(0.0, 0.0, 0.0),
                       forward=(0.0, 0.0, -1.0), now=now)

    def test_dying_puts_a_notice_up(self, match, screen):
        presenter = feedback.Presenter(match, hud=screen)
        match.damage(game.PLAYER_ID, 500, by='bot1')
        self.show(presenter, match)
        assert screen.dead.visible
        assert 'Bot 1' in screen.deathcause.value

    def test_the_notice_counts_down_to_the_respawn(self, match, screen):
        """An honest timer, so a player does not wonder whether it has hung."""
        presenter = feedback.Presenter(match, hud=screen)
        match.damage(game.PLAYER_ID, 500, by='bot1')
        self.show(presenter, match)
        match.advance(0.5)
        presenter.update(now=0.5)
        first = screen.respawn.value
        match.advance(0.5)
        presenter.update(now=1.0)
        assert screen.respawn.value != first

    def test_coming_back_takes_the_notice_down(self, match, screen):
        presenter = feedback.Presenter(match, hud=screen)
        match.damage(game.PLAYER_ID, 500, by='bot1')
        self.show(presenter, match)
        match.advance(arena.RESPAWN_DELAY)
        match.respawn(game.PLAYER_ID, position=(0.0, 0.0, 0.0))
        presenter.update(now=arena.RESPAWN_DELAY)
        assert not screen.dead.visible

    def test_coming_back_clears_the_damage_marks(self, match, screen):
        """A fresh body is not still bleeding from the last one's wounds."""
        presenter = feedback.Presenter(match, hud=screen)
        match.damage(game.PLAYER_ID, 500, by='bot1')
        self.show(presenter, match)
        match.advance(arena.RESPAWN_DELAY)
        match.respawn(game.PLAYER_ID, position=(0.0, 0.0, 0.0))
        presenter.update(now=arena.RESPAWN_DELAY)
        assert not screen.damage.marks

    def test_a_bot_dying_leaves_the_notice_alone(self, match, screen):
        presenter = feedback.Presenter(match, hud=screen)
        match.damage('bot1', 500, by=game.PLAYER_ID)
        self.show(presenter, match)
        assert not screen.dead.visible


class TestOneStreamManyReaders:
    """The seam: sound and screen read the same events, so they cannot disagree."""

    class Ears:
        def __init__(self):
            self.heard = []
            self.platform = None

        def show(self, events, platform=None):
            self.heard.extend(events)
            self.platform = platform
            return len(events)

    def test_the_sounds_hear_everything_the_screen_sees(self, match, screen):
        ears = self.Ears()
        presenter = feedback.Presenter(match, hud=screen, sounds=ears)
        match.fired('bot1', 'rifle', origin=(0, 0, 0), direction=(1, 0, 0))
        match.damage(game.PLAYER_ID, 30, by='bot1')
        presenter.show(match.drain(), camera=(0, 0, 0), forward=(0, 0, -1))
        assert {type(event) for event in ears.heard} == {arena.Fired,
                                                         arena.Damaged}
        assert screen.damage.marks

    def test_the_effects_see_it_too(self, match, screen):
        from twitchoglc import effects as effectsmod
        drawn = effectsmod.Effects(match)
        presenter = feedback.Presenter(match, hud=screen, effects=drawn)
        match.impact(point=(1, 0, 0), normal=(0, 1, 0), surface='stone')
        presenter.show(match.drain(), camera=(0, 0, 0), forward=(0, 0, -1))
        assert drawn.emitters[effectsmod.DUST].pool.live > 0

    def test_the_camera_reaches_the_ear(self, match, screen):
        ears = self.Ears()
        presenter = feedback.Presenter(match, hud=screen, sounds=ears)
        platform = object()
        match.fired('bot1', 'rifle', origin=(0, 0, 0), direction=(1, 0, 0))
        presenter.show(match.drain(), camera=(0, 0, 0), forward=(0, 0, -1),
                       platform=platform)
        assert ears.platform is platform


class TestPickingSomethingUp:
    """A pickup nobody is told about is indistinguishable from a bug.

    The number in the corner goes up by twenty-five and nothing says why,
    which is most of why the item entities being missing read as the game
    being broken rather than as a feature that had not arrived.
    """

    def shown(self, match, screen, target=game.PLAYER_ID, title='ARMOUR'):
        presenter = feedback.Presenter(match, hud=screen)
        match.picked_up(target, key='armour', title=title, point=(1, 0, 0))
        presenter.show(match.drain(), camera=(0, 0, 0), forward=(0, 0, -1),
                       now=0.0)
        return [one.text for one in screen.messages.messages]

    def test_the_player_is_told_what_they_took(self, match, screen):
        assert any('ARMOUR' in line for line in self.shown(match, screen))

    def test_a_bot_taking_something_is_not_news(self, match, screen):
        assert self.shown(match, screen, target='bot1') == []

    def test_a_kind_with_no_title_still_says_something(self, match, screen):
        assert any('armour' in line
                   for line in self.shown(match, screen, title=''))


class TestWithNothingToDrawOn:
    """A capture run has no HUD, and must still be able to run a match."""

    def test_events_with_no_hud_are_harmless(self, match):
        presenter = feedback.Presenter(match, hud=None)
        match.damage(game.PLAYER_ID, 500, by='bot1')
        presenter.show(match.drain(), camera=(0, 0, 0), forward=(0, 0, -1),
                       now=0.0)
        presenter.update(now=1.0)
