"""The simulation's timestep, and the world time a slow frame throws away.

A frame that took a second must not be simulated as a second -- a character
moved that far in one step tunnels through the level. Clamping it is right, and
it is also why a stalling game reads as *slow motion* rather than as a freeze:
the world advances by the clamp while the wall clock advances by the whole
frame, so everything moves at a fraction of speed while the frame rate carries
on reporting whatever the renderer managed.

These pin the clamp and, more importantly, pin the accounting of what it cost:
world time discarded this frame, and the debt accumulated since the map loaded.
"""

import pytest

from twig_bb.frameclock import FrameClock


@pytest.fixture
def clock():
    found = FrameClock()
    found.reset(100.0)
    return found


class TestTheTimestep:
    def test_an_ordinary_frame_is_simulated_as_itself(self, clock):
        assert clock.tick(100.016) == pytest.approx(0.016)

    def test_a_slow_frame_is_cut_to_the_maximum_step(self, clock):
        assert clock.tick(101.0) == pytest.approx(FrameClock.MAX_STEP)

    def test_each_tick_measures_from_the_one_before(self, clock):
        clock.tick(100.010)
        assert clock.tick(100.030) == pytest.approx(0.020)

    def test_a_clock_nobody_started_starts_itself(self):
        """A first tick has no previous frame to be a duration from."""
        found = FrameClock()
        assert found.tick(50.0) == 0.0
        assert found.tick(50.020) == pytest.approx(0.020)

    def test_resetting_forgets_the_gap_across_a_map_load(self, clock):
        """A level load is not a stall the player suffered; it is not one here."""
        clock.reset(160.0)
        assert clock.tick(160.016) == pytest.approx(0.016)
        assert clock.debt == 0.0

    def test_the_maximum_step_can_be_asked_for(self):
        found = FrameClock(maximum=0.010)
        found.reset(0.0)
        assert found.tick(1.0) == pytest.approx(0.010)


class TestWhatTheClampCosts:
    def test_an_ordinary_frame_loses_nothing(self, clock):
        clock.tick(100.016)
        assert clock.real == pytest.approx(0.016)
        assert clock.lost == 0.0
        assert clock.debt == 0.0

    def test_a_stalled_frame_records_the_world_time_it_never_simulated(self, clock):
        clock.tick(101.0)
        assert clock.real == pytest.approx(1.0)
        assert clock.dt == pytest.approx(FrameClock.MAX_STEP)
        assert clock.lost == pytest.approx(1.0 - FrameClock.MAX_STEP)

    def test_the_debt_accumulates_across_frames(self, clock):
        clock.tick(101.0)
        clock.tick(102.0)
        assert clock.debt == pytest.approx(2.0 - 2 * FrameClock.MAX_STEP)

    def test_healthy_frames_do_not_pay_the_debt_back(self, clock):
        """Discarded world time is gone; a fast frame later does not return it."""
        clock.tick(101.0)
        owed = clock.debt
        for step in range(1, 11):
            clock.tick(101.0 + step * 0.016)
        assert clock.debt == pytest.approx(owed)

    def test_the_ratio_says_how_much_slower_the_world_is_running(self, clock):
        """1.0 is real time; 0.05 is a world running at a twentieth of speed."""
        clock.tick(100.016)
        assert clock.pace == pytest.approx(1.0)
        clock.tick(101.016)
        assert clock.pace == pytest.approx(FrameClock.MAX_STEP)

    def test_a_frame_of_no_duration_has_a_pace_of_real_time(self, clock):
        """Two ticks at one instant: nothing was lost, so nothing is behind."""
        assert clock.tick(100.0) == 0.0
        assert clock.pace == 1.0


class TestDescribe:
    def test_it_says_the_timestep_and_stays_quiet_when_all_is_well(self, clock):
        clock.tick(100.016)
        described = clock.describe()
        assert described['dt ms'] == pytest.approx(16.0)
        assert 'behind' not in described

    def test_a_clamped_frame_says_how_far_behind_the_world_is(self, clock):
        clock.tick(101.0)
        described = clock.describe()
        assert described['dt ms'] == pytest.approx(FrameClock.MAX_STEP * 1000.0)
        assert described['real ms'] == pytest.approx(1000.0)
        assert described['behind'] == '5% speed, 0.9s lost'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
