"""Where the view goes while the player is dead.

Being killed used to leave the camera where it stood, still steered by the
mouse, with a line of text saying it had happened — which reads as the message
being wrong rather than as a death. All of this is arithmetic over positions
and seconds, so it is a test rather than something somebody has to go and get
killed to check.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from OpenGLContext.move.viewplatform import ViewPlatform

from twig_bb import deathcam


def killed(eye=(0.0, 1.6, 0.0), feet=(0.0, 0.0, 0.0), yaw=0.0, killer=None):
    camera = deathcam.DeathCamera()
    camera.begin(eye, feet, yaw=yaw, killer=killer)
    return camera


def settled(camera):
    """Run the fall right through, so the shot is where it ends up."""
    camera.advance(deathcam.DROP_SECONDS * 2.0)
    return camera


class TestTakingTheView:

    def test_nothing_is_watching_until_somebody_dies(self):
        assert not deathcam.DeathCamera().watching

    def test_dying_takes_the_view(self):
        assert killed().watching

    def test_it_starts_where_the_player_was_looking_from(self):
        """A cut is indistinguishable from the game reloading; this falls."""
        camera = killed(eye=(3.0, 1.6, -2.0))
        assert camera.position() == pytest.approx([3.0, 1.6, -2.0])

    def test_it_ends_up_near_the_floor(self):
        camera = settled(killed(feet=(3.0, 5.0, -2.0)))
        assert camera.position() == pytest.approx(
            [3.0, 5.0 + deathcam.EYE_HEIGHT, -2.0])

    def test_the_fall_is_under_way_in_between(self):
        camera = killed(eye=(0.0, 1.6, 0.0), feet=(0.0, 0.0, 0.0))
        camera.advance(deathcam.DROP_SECONDS * 0.5)
        height = float(camera.position()[1])
        assert deathcam.EYE_HEIGHT < height < 1.6

    def test_it_does_not_go_on_falling_past_the_floor(self):
        camera = killed()
        camera.advance(deathcam.DROP_SECONDS * 20.0)
        assert camera.position()[1] == pytest.approx(deathcam.EYE_HEIGHT)

    def test_giving_the_view_back_stops_it(self):
        camera = settled(killed())
        camera.end()
        assert not camera.watching

    def test_giving_it_back_twice_is_one_respawn(self):
        camera = killed()
        camera.end()
        camera.end()
        assert not camera.watching

    def test_a_second_death_starts_afresh(self):
        camera = settled(killed())
        camera.begin((0.0, 1.6, 0.0), (0.0, 0.0, 0.0))
        assert camera.elapsed == 0.0
        assert camera.position() == pytest.approx([0.0, 1.6, 0.0])


class TestLookingAtWhoeverDidIt:
    """The one thing a player wants in that second, and cannot otherwise get."""

    def gaze(self, camera):
        """Where the death camera is looking, in world terms.

        Through the platform's own matrices rather than through the angles it
        was given: the question is what ends up on screen, and a rule checked
        against the rule that produced it could be wrong in both places.
        """
        platform = ViewPlatform()
        camera.apply(platform)
        matrix = np.asarray(platform.quaternion.matrix(), dtype='d')
        return matrix[:3, :3] @ np.array([0.0, 0.0, -1.0])

    def test_it_turns_towards_the_killer(self):
        camera = settled(killed(killer=(10.0, 0.0, 0.0)))
        assert self.gaze(camera)[0] > 0.9

    def test_it_turns_the_other_way_for_a_killer_the_other_side(self):
        camera = settled(killed(killer=(-10.0, 0.0, 0.0)))
        assert self.gaze(camera)[0] < -0.9

    def test_it_looks_up_at_somebody_standing_over_it(self):
        """From the floor, which is where it now is."""
        camera = settled(killed(killer=(4.0, 1.6, 0.0)))
        assert self.gaze(camera)[1] > 0.1

    def test_with_nobody_to_blame_it_keeps_the_heading_it_died_on(self):
        """The lava, a long fall: there is nothing to look at."""
        camera = settled(killed(yaw=1.25))
        looking = self.gaze(camera)
        assert looking[0] == pytest.approx(math.sin(1.25), abs=1e-6)
        assert looking[2] == pytest.approx(-math.cos(1.25), abs=1e-6)

    def test_a_killer_standing_exactly_where_the_body_is_is_not_a_direction(self):
        camera = settled(killed(yaw=0.5, feet=(0.0, 0.0, 0.0),
                                killer=(0.0, deathcam.EYE_HEIGHT, 0.0)))
        assert self.gaze(camera)[2] < 0.0


class TestTheRedWash:

    def test_nothing_is_washed_while_alive(self):
        assert deathcam.DeathCamera().wash() == 0.0

    def test_it_comes_up_with_the_fall(self):
        camera = killed()
        camera.advance(deathcam.DROP_SECONDS * 0.5)
        assert 0.0 < camera.wash() < deathcam.WASH

    def test_it_settles_at_the_declared_strength(self):
        assert settled(killed()).wash() == pytest.approx(deathcam.WASH)

    def test_it_is_short_of_a_curtain(self):
        """The fight going on without you is the point of drawing the world."""
        assert 0.0 < deathcam.WASH < 0.6

    def test_coming_back_clears_it(self):
        camera = settled(killed())
        camera.end()
        assert camera.wash() == 0.0


class TestPuttingItOnAPlatform:

    def test_the_platform_is_moved(self):
        platform = ViewPlatform()
        settled(killed(feet=(1.0, 2.0, 3.0))).apply(platform)
        assert tuple(platform.position)[:3] == pytest.approx(
            (1.0, 2.0 + deathcam.EYE_HEIGHT, 3.0))

    def test_time_only_moves_while_it_is_watching(self):
        camera = deathcam.DeathCamera()
        camera.advance(5.0)
        assert camera.elapsed == 0.0
