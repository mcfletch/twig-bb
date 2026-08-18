"""Things that fly: rockets and grenades, stepped as one batch.

The properties that matter are all about *not* being wrong at speed — a rocket
that tunnels through a wall, a grenade that never settles, a projectile that
kills the person who fired it at the muzzle — so that is what is asserted, over
constructed geometry rather than over a level.
"""

from __future__ import annotations

import sys
import time

import numpy as np
import pytest

from omi_physics import model
from omi_physics.world import PhysicsWorld

from twig_bb import arena, projectiles, weapons


def world():
    return PhysicsWorld(gravity=model.Gravity(gravity=9.81, direction=(0, -1, 0)))


def wall(w, x, extent=30.0):
    """A trimesh plane across the x axis: a thin one, on purpose."""
    e = extent
    points = np.array([(x, -e, -e), (x, e, -e), (x, e, e), (x, -e, e)], dtype='d')
    indices = np.array([(0, 1, 2), (0, 2, 3)], dtype='i')
    shape = w.add_shape(model.Shape.trimesh(points, indices))
    return w.add_body(model.Motion(type=model.STATIC),
                      collider=model.Collider(shape=shape), position=(0, 0, 0))


def floor(w, y=0.0, extent=60.0):
    e = extent
    points = np.array([(-e, y, -e), (e, y, -e), (e, y, e), (-e, y, e)], dtype='d')
    indices = np.array([(0, 1, 2), (0, 2, 3)], dtype='i')
    shape = w.add_shape(model.Shape.trimesh(points, indices))
    return w.add_body(model.Motion(type=model.STATIC),
                      collider=model.Collider(shape=shape), position=(0, 0, 0))


def match(bots=1):
    made = arena.Arena(weapons=weapons.default_table(), fragLimit=15,
                       timeLimit=10.0)
    made.add('player', position=(0.0, 0.0, 0.0), name='You')
    for index in range(bots):
        made.add('bot%d' % index, position=(20.0 + index * 5, 0.0, 0.0),
                 bot=True, name='Bot %d' % index)
    return made


@pytest.fixture
def kinds():
    return projectiles.default_table()


@pytest.fixture
def rocket(kinds):
    return kinds.by_key(projectiles.ROCKET)


@pytest.fixture
def grenade(kinds):
    return kinds.by_key(projectiles.GRENADE)


@pytest.fixture
def flight(kinds):
    return projectiles.Projectiles(kinds)


class TestTheTable:
    """A rocket and a grenade differ in declared numbers, not in code."""

    def test_a_rocket_ignores_gravity_and_a_grenade_does_not(self, rocket,
                                                             grenade):
        assert float(rocket.gravity) == 0.0
        assert float(grenade.gravity) > 0.0

    def test_a_rocket_detonates_on_contact_and_a_grenade_bounces(self, rocket,
                                                                 grenade):
        assert float(rocket.bounce) == 0.0
        assert float(grenade.bounce) > 0.0

    def test_a_grenade_has_a_fuse_and_a_rocket_does_not(self, rocket, grenade):
        assert float(rocket.fuse) == 0.0
        assert float(grenade.fuse) > 0.0

    def test_an_unknown_kind_is_no_kind_rather_than_an_error(self, kinds):
        assert kinds.by_key('nothing-like-this') is None

    def test_a_rocket_is_a_motor_and_a_grenade_is_not(self, rocket, grenade):
        """A rocket builds speed as it flies; a grenade only ever loses it."""
        assert float(rocket.acceleration) > 0.0
        assert float(grenade.acceleration) == 0.0

    def test_a_rocket_leaves_slower_than_it_ends_up(self, rocket):
        """Slow enough at the muzzle to be a close-range splash weapon, fast
        enough at its ceiling to be one a sidestep cannot answer."""
        assert float(rocket.speed) < float(rocket.maxSpeed)


class TestHowLongAShotTakes:
    """`time_to` is the flat flight time a bot leads a target by; it has to
    account for the thrust, or a lead computed from the launch speed alone
    aims a rocket where the target was a good deal too long ago."""

    def test_an_unpowered_round_is_distance_over_speed(self, grenade):
        assert grenade.time_to(32.0) == pytest.approx(32.0 / float(grenade.speed))

    def test_zero_distance_takes_no_time(self, rocket):
        assert rocket.time_to(0.0) == 0.0

    def test_a_motor_arrives_sooner_than_its_launch_speed_would(self, rocket):
        flat = 40.0 / float(rocket.speed)
        assert rocket.time_to(40.0) < flat

    def test_it_is_monotonic_in_distance(self, rocket):
        earlier = [rocket.time_to(d) for d in range(0, 60, 5)]
        assert earlier == sorted(earlier)
        assert all(b > a for a, b in zip(earlier, earlier[1:]))

    def test_a_round_that_cannot_move_never_arrives(self, kinds):
        still = projectiles.Projectile(key='still', speed=0.0, acceleration=0.0)
        assert still.time_to(10.0) == float('inf')

    def test_distance_in_is_the_inverse_of_time_to(self, rocket):
        """The distance covered in the time it takes to cover it, out and back."""
        for distance in (2.0, 12.0, 24.0, 80.0):
            assert rocket.distance_in(rocket.time_to(distance)) == \
                pytest.approx(distance, rel=1e-6)

    def test_a_motor_covers_more_ground_than_its_launch_speed_says(self, rocket):
        over = 5.0
        assert rocket.distance_in(over) > float(rocket.speed) * over

    def test_an_unpowered_round_is_launch_speed_times_time(self, grenade):
        assert grenade.distance_in(3.0) == pytest.approx(float(grenade.speed) * 3.0)


class TestPickingUpSpeed:
    """A rocket's speed climbs each tick, along its heading, up to its cap."""

    def _speed(self, flight, index=0):
        return float(np.linalg.norm(flight.velocity[index]))

    def test_it_leaves_the_muzzle_at_its_launch_speed(self, flight, rocket):
        flight.launch(rocket, origin=(0, 1, 0), direction=(1, 0, 0),
                      owner='player')
        # The first tick moves at the launch speed -- thrust is added for the
        # tick after, so a rocket "leaves at speed" is literally true.
        flight.step(world(), match(bots=0), dt=0.1)
        assert flight.position[0][0] == pytest.approx(float(rocket.speed) * 0.1)

    def test_it_is_faster_after_flying_than_at_the_muzzle(self, flight, rocket):
        flight.launch(rocket, origin=(0, 1, 0), direction=(1, 0, 0),
                      owner='player')
        for _ in range(6):
            flight.step(world(), match(bots=0), dt=0.05)
        assert self._speed(flight) > float(rocket.speed)

    def test_the_thrust_stays_on_the_heading(self, flight, rocket):
        flight.launch(rocket, origin=(0, 1, 0), direction=(1, 0, 0),
                      owner='player')
        for _ in range(6):
            flight.step(world(), match(bots=0), dt=0.05)
        assert flight.velocity[0][1] == pytest.approx(0.0, abs=1e-9)
        assert flight.velocity[0][2] == pytest.approx(0.0, abs=1e-9)

    def test_it_never_passes_its_ceiling(self, flight, rocket):
        flight.launch(rocket, origin=(0, 1, 0), direction=(1, 0, 0),
                      owner='player')
        for _ in range(200):
            flight.step(world(), match(bots=0), dt=0.05)
            if not len(flight):
                break
            assert self._speed(flight) <= float(rocket.maxSpeed) + 1e-6

    def test_a_grenade_only_slows(self, flight, grenade):
        """Its speed change is gravity's, never a motor's: no thrust adds to it."""
        flight.launch(grenade, origin=(0, 50, 0), direction=(1, 0, 0),
                      owner='player')
        first = None
        for _ in range(3):
            flight.step(world(), match(bots=0), dt=0.02)
        first = float(flight.velocity[0][0])
        for _ in range(3):
            flight.step(world(), match(bots=0), dt=0.02)
        # The horizontal component is never pushed up: only gravity acts, and
        # it is vertical, so along the heading a grenade is not a motor.
        assert float(flight.velocity[0][0]) == pytest.approx(first, abs=1e-9)


class TestAskingWhatIsInASlot:
    """Which kind is in each slot, for whoever has to *draw* the batch.

    A rocket and a grenade are not the same shape, so the renderer needs to
    know which of the two it is looking at -- and the batch stores that as an
    index into a registry it owns, which is not a thing to reach into.
    """

    def test_a_slot_says_which_kind_is_in_it(self, flight, rocket, grenade):
        flight.launch(rocket, origin=(0, 1, 0), direction=(1, 0, 0), owner='player')
        flight.launch(grenade, origin=(0, 1, 0), direction=(1, 0, 0), owner='player')
        assert flight.kind_at(0) is rocket
        assert flight.kind_at(1) is grenade

    def test_an_empty_slot_holds_no_kind(self, flight):
        assert flight.kind_at(0) is None

    def test_and_so_does_one_past_the_end(self, flight, rocket):
        flight.launch(rocket, origin=(0, 1, 0), direction=(1, 0, 0), owner='player')
        assert flight.kind_at(1) is None
        assert flight.kind_at(-1) is None


class TestFlying:

    def test_a_launched_projectile_is_in_the_air(self, flight, rocket):
        flight.launch(rocket, origin=(0, 1, 0), direction=(1, 0, 0),
                      owner='player')
        assert len(flight) == 1

    def test_it_travels_along_its_heading(self, flight, rocket):
        flight.launch(rocket, origin=(0, 1, 0), direction=(1, 0, 0),
                      owner='player')
        flight.step(world(), match(), dt=0.1)
        assert flight.position[0][0] == pytest.approx(float(rocket.speed) * 0.1,
                                                      rel=1e-6)

    def test_a_heading_need_not_be_normalised(self, flight, rocket):
        flight.launch(rocket, origin=(0, 1, 0), direction=(7, 0, 0),
                      owner='player')
        flight.step(world(), match(), dt=0.1)
        assert flight.position[0][0] == pytest.approx(float(rocket.speed) * 0.1,
                                                      rel=1e-6)

    def test_a_heading_of_nothing_launches_nothing(self, flight, rocket):
        assert flight.launch(rocket, origin=(0, 1, 0), direction=(0, 0, 0),
                             owner='player') is False
        assert len(flight) == 0

    def test_a_rocket_does_not_fall(self, flight, rocket):
        flight.launch(rocket, origin=(0, 5, 0), direction=(1, 0, 0),
                      owner='player')
        for _ in range(10):
            flight.step(world(), match(), dt=0.02)
        assert flight.position[0][1] == pytest.approx(5.0, abs=1e-9)

    def test_a_grenade_falls_under_gravity(self, flight, grenade):
        flight.launch(grenade, origin=(0, 5, 0), direction=(1, 0, 0),
                      owner='player')
        for _ in range(10):
            flight.step(world(), match(), dt=0.02)
        assert flight.position[0][1] < 5.0

    def test_a_projectile_that_flies_for_ever_gives_up(self, flight, rocket):
        """Otherwise a shot into the sky is a body nobody ever reclaims."""
        flight.launch(rocket, origin=(0, 1, 0), direction=(0, 1, 0),
                      owner='player')
        flight.step(world(), match(), dt=float(rocket.lifetime) + 0.1)
        assert len(flight) == 0

    def test_the_batch_holds_many_at_once(self, flight, rocket):
        for index in range(50):
            flight.launch(rocket, origin=(0, 1, index * 0.5),
                          direction=(1, 0, 0), owner='player')
        assert len(flight) == 50

    def test_a_full_batch_refuses_rather_than_growing(self, kinds, rocket):
        flight = projectiles.Projectiles(kinds, capacity=4)
        for _ in range(10):
            flight.launch(rocket, origin=(0, 1, 0), direction=(1, 0, 0),
                          owner='player')
        assert len(flight) == 4


class TestNotTunnelling:
    """A rocket as a rigid body is a rocket that passes through a wall at speed."""

    def test_a_thin_wall_crossed_in_one_tick_still_stops_it(self, flight, rocket):
        w = world()
        wall(w, x=5.0)
        flight.launch(rocket, origin=(0, 1, 0), direction=(1, 0, 0),
                      owner='player')
        # One tick long enough to pass the wall entirely at this speed.
        gone = flight.step(w, match(), dt=20.0 / float(rocket.speed))
        assert len(gone) == 1
        assert gone[0].point[0] == pytest.approx(5.0, abs=0.3)
        assert len(flight) == 0

    def test_it_does_not_stop_short_of_a_wall_it_never_reaches(self, flight,
                                                              rocket):
        w = world()
        wall(w, x=50.0)
        assert flight.launch(rocket, origin=(0, 1, 0), direction=(1, 0, 0),
                             owner='player')
        assert flight.step(w, match(), dt=0.05) == []
        assert len(flight) == 1


class TestHittingSomebody:

    def test_a_direct_hit_damages_them(self, flight, rocket):
        found = match()
        flight.launch(rocket, origin=(0, 1.0, 0), direction=(1, 0, 0),
                      owner='player')
        for _ in range(40):
            flight.step(world(), found, dt=0.05)
            if not len(flight):
                break
        assert found.combatant('bot0').health < arena.STARTING_HEALTH

    def test_the_detonation_says_who_it_hit(self, flight, rocket):
        found = match()
        flight.launch(rocket, origin=(0, 1.0, 0), direction=(1, 0, 0),
                      owner='player')
        gone = []
        for _ in range(40):
            gone.extend(flight.step(world(), found, dt=0.05))
            if not len(flight):
                break
        assert gone and gone[-1].target == 'bot0'

    def test_a_rocket_ignores_its_owner_at_the_muzzle(self, flight, rocket):
        """Or every rocket kills the person who fired it, instantly."""
        found = match()
        flight.launch(rocket, origin=(0, 1.0, 0), direction=(1, 0, 0),
                      owner='player')
        flight.step(world(), found, dt=0.01)
        assert found.combatant('player').health == arena.STARTING_HEALTH
        assert len(flight) == 1

    def test_it_stops_ignoring_its_owner_once_it_has_cleared_them(self, flight,
                                                                  rocket):
        """A rocket bounced back off a wall must be able to come home."""
        found = match()
        # Fired at a wall a little way off, so it comes back past the shooter.
        flight.launch(rocket, origin=(0, 1.0, 0), direction=(1, 0, 0),
                      owner='player')
        flight.step(world(), found, dt=projectiles.ARMING_DISTANCE
                    / float(rocket.speed) + 0.01)
        assert flight.armed[0]


class TestAGrenadeThrownStraightAtSomebody:
    """It should go off on them and it should kill them.

    Reported as a grenade meeting a bot head-on and the bot walking away.  The
    contact path already existed — a projectile that meets a *body* detonates
    rather than bouncing — so what was unproven was the rest of it: that the
    burst that follows reaches the person the grenade was touching.  Two
    ranges, because they fail differently: at five metres it is an ordinary
    flight, and at one it is inside the arming distance, where a projectile is
    still ignoring the person who threw it.  Both are inside
    :func:`twig_bb.bots.reach`, because a grenade aimed *flat* at somebody
    ten metres away is in the floor before it gets there — which is a
    different bug with its own tests.
    """

    def thrown(self, flight, grenade, gap, dt=1.0 / 240.0, armour=0):
        """Throw one at a combatant ``gap`` metres away and let it land."""
        found = arena.Arena(weapons=weapons.default_table(), fragLimit=15,
                            timeLimit=10.0)
        found.add('player', position=(0.0, 0.0, 0.0), name='You')
        found.add('bot0', position=(gap, 0.0, 0.0), bot=True, name='Bot')
        found.combatant('bot0').armour = armour
        w = world()
        eye = np.array([0.0, 1.0, 0.0])
        aim = np.append(np.asarray(found.combatant('bot0').position)
                        + np.array([0.0, 1.0, 0.0]) - eye, 0.0)[:3]
        flight.launch(grenade, origin=eye, direction=aim, owner='player')
        for _ in range(2000):
            gone = flight.step(w, found, dt=dt)
            if gone:
                from twig_bb import blast
                blast.answer(w, found, flight.table, gone)
                return found, gone
            if not len(flight):
                break
        return found, []

    def test_at_five_metres_it_goes_off_on_them(self, flight, grenade):
        found, gone = self.thrown(flight, grenade, 5.0)
        assert gone and gone[-1].target == 'bot0'

    def test_at_five_metres_it_kills_them(self, flight, grenade):
        found, _gone = self.thrown(flight, grenade, 5.0)
        assert not found.combatant('bot0').alive

    def test_at_one_metre_it_still_goes_off_on_them(self, flight, grenade):
        """Inside the arming distance, where its owner is still being ignored."""
        found, gone = self.thrown(flight, grenade, 1.0)
        assert gone and gone[-1].target == 'bot0'

    def test_at_one_metre_it_kills_them(self, flight, grenade):
        found, _gone = self.thrown(flight, grenade, 1.0)
        assert not found.combatant('bot0').alive

    def test_a_direct_hit_is_lethal_on_its_own(self, grenade, rocket):
        """Whoever is struck head-on is left out of the burst, so the direct
        number is the whole of what a direct hit costs -- and at less than a
        full life a grenade in somebody's chest left them walking."""
        for kind in (grenade, rocket):
            assert float(kind.damage) >= arena.STARTING_HEALTH

    def test_armour_still_saves_you_from_one(self, flight, grenade):
        """Which is what makes armour worth the detour."""
        found, _gone = self.thrown(flight, grenade, 5.0, armour=100)
        assert found.combatant('bot0').alive


class TestABouncingGrenade:

    def test_it_bounces_off_the_floor_rather_than_detonating(self, flight,
                                                             grenade):
        w = world()
        floor(w, y=0.0)
        flight.launch(grenade, origin=(0, 3.0, 0), direction=(1, 0, 0),
                      owner='player')
        for _ in range(20):
            flight.step(w, match(), dt=0.05)
        assert len(flight) == 1                 # still in the air, or rolling

    def test_a_bounce_reverses_it_and_takes_energy_out(self, flight, grenade):
        w = world()
        floor(w, y=0.0)
        flight.launch(grenade, origin=(0, 1.0, 0), direction=(0, -1, 0),
                      owner='player')
        before = abs(float(flight.velocity[0][1]))
        for _ in range(30):
            flight.step(w, match(), dt=0.02)
            if flight.velocity[0][1] > 0.0:
                break
        assert 0.0 < float(flight.velocity[0][1]) < before

    def test_its_fuse_detonates_it_in_the_air(self, flight, grenade):
        flight.launch(grenade, origin=(0, 40.0, 0), direction=(0, 1, 0),
                      owner='player')
        gone = []
        for _ in range(200):
            gone.extend(flight.step(world(), match(), dt=0.05))
            if not len(flight):
                break
        assert gone and gone[-1].kind == projectiles.GRENADE
        assert not gone[-1].target

    def test_a_grenade_comes_to_rest_rather_than_bouncing_for_ever(self, flight,
                                                                   grenade):
        """Each bounce keeps less, and below a threshold it is simply put down.

        The fuse is taken off for this one, because what is being asserted is
        that the bouncing *converges* — a grenade still jittering under the
        player's feet when its fuse runs out would pass a test that only
        watched it until then.
        """
        grenade.fuse = 0.0
        w = world()
        floor(w, y=0.0)
        flight.launch(grenade, origin=(0, 2.0, 0), direction=(0.2, 0, 0),
                      owner='player')
        for _ in range(150):
            flight.step(w, match(), dt=0.02)
        assert len(flight) == 1
        assert abs(float(flight.velocity[0][1])) < 1.0


class TestSayingWhatHappened:

    def test_a_detonation_is_announced_on_the_match_stream(self, flight, rocket):
        w = world()
        wall(w, x=3.0)
        found = match()
        flight.launch(rocket, origin=(0, 1, 0), direction=(1, 0, 0),
                      owner='player')
        for _ in range(20):
            flight.step(w, found, dt=0.05)
        assert [event for event in found.events
                if isinstance(event, arena.Detonated)]

    def test_the_detonation_names_who_fired_it(self, flight, rocket):
        w = world()
        wall(w, x=3.0)
        found = match()
        flight.launch(rocket, origin=(0, 1, 0), direction=(1, 0, 0),
                      owner='bot0')
        for _ in range(20):
            flight.step(w, found, dt=0.05)
        gone = [event for event in found.events
                if isinstance(event, arena.Detonated)]
        assert gone and gone[0].by == 'bot0'


class TestWhereABurstIsCentred:
    """Clear of what the round met, by the radius it met it at.

    A warhead is at its own radius from a wall when its nose touches it, and
    the difference matters far more than a centimetre and a half should: the
    burst that follows asks whether it can *see* each person near it, and a
    point sitting exactly on a triangle is on both sides of it at once.  Half
    the time the cast out of it meets that triangle at no distance and reports
    the whole room to be behind cover, which is a rocket that lands at
    somebody's feet and does nothing whatever.
    """

    def clearance(self, kind, w, found, flight, origin, direction):
        """How far the burst ended up off the plane it landed on."""
        flight.launch(kind, origin=origin, direction=direction, owner='player')
        for _ in range(200):
            gone = flight.step(w, found, dt=1.0 / 60.0)
            if gone:
                return (gone[0].point, gone[0].normal)
        raise AssertionError('nothing went off')

    def test_a_rocket_on_the_floor_is_a_radius_above_it(self, flight, rocket):
        w = world()
        floor(w)
        point, normal = self.clearance(rocket, w, match(), flight,
                                       origin=(0, 1.6, 0), direction=(1, -1, 0))
        assert float(point[1]) == pytest.approx(float(rocket.radius))

    def test_a_rocket_on_a_wall_is_a_radius_out_from_it(self, flight, rocket):
        w = world()
        wall(w, x=3.0)
        point, normal = self.clearance(rocket, w, match(), flight,
                                       origin=(0, 1, 0), direction=(1, 0, 0))
        assert 3.0 - float(point[0]) == pytest.approx(float(rocket.radius))

    def test_a_grenade_that_ran_out_of_fuse_in_the_air_is_where_it_was(
            self, flight, grenade):
        """Nothing to be clear of, so nothing is moved."""
        w = world()
        found = match()
        flight.launch(grenade, origin=(0, 40.0, 0), direction=(1, 0, 0),
                      owner='player')
        for _ in range(400):
            gone = flight.step(w, found, dt=1.0 / 60.0)
            if gone:
                break
        assert gone and gone[0].normal is None
        assert float(gone[0].point[1]) < 40.0    # it fell, and stayed fallen


#: What a busy fight's worth of projectiles may cost, in milliseconds a tick.
#: Well inside a 16.7 ms frame, because the projectiles are one of a dozen
#: things a frame does.
FIGHT_BUDGET_MS = 4.0

#: And what a number far past anything a match produces may cost: a whole
#: frame, and no more.
FLOOD_BUDGET_MS = 16.0

#: How much of the small budget the *small* case may take before this machine
#: is too loaded for the large one's budget to mean anything.  Measured: with
#: nothing else running, sixteen projectiles cost 0.71 ms and three hundred
#: cost 12.5 ms; on a box running another test suite the same code costs 1.76
#: and 31.5.  A quarter of the small budget -- one millisecond -- sits cleanly
#: between the two.  See :meth:`TestWhatItCosts.busy`.
QUIET = 0.25


#: A line tracer roughly halves the speed of everything below, so a wall-clock
#: budget measured under one is a measurement of the tracer.  The tests that
#: assert a time say so rather than being given a bound loose enough to pass
#: under coverage -- which would be a bound that no longer means "fits in a
#: frame".
traced = pytest.mark.skipif(
    sys.gettrace() is not None or sys.getprofile() is not None,
    reason='a timing budget cannot be measured while something is tracing')


class TestWhatItCosts:

    def tick(self, count, kind, ticks=10, runs=3):
        """Milliseconds of **processor time** a tick costs for ``count`` in flight.

        Processor time and not wall-clock time, which is the difference between
        measuring the work and measuring the machine.  A budget of "fits in a
        frame" is a claim about how much computing a tick asks for; a wall
        clock also counts every moment the operating system gave the core to
        something else, so on a busy machine the same code reads as three times
        slower and the test fails for a reason nothing here can fix.  Loosening
        the bound instead would leave a number that no longer means "fits in a
        frame", which is the only thing it is for.

        The **fastest** of ``runs``, for the leftover noise: a first pass warms
        caches that later ones do not have to, and scheduling only ever adds.
        It is the same reason :mod:`timeit` reports a minimum.
        """
        return min(self._once(count, kind, ticks) for _ in range(max(1, runs)))

    def _once(self, count, kind, ticks):
        """One measurement of a tick, in milliseconds of processor time."""
        w = world()
        floor(w, y=-40.0, extent=400.0)
        found = match()
        flight = projectiles.Projectiles(projectiles.default_table(),
                                         capacity=512)
        for index in range(count):
            flight.launch(kind, origin=(0, 1.0, index * 0.1),
                          direction=(1, 0, 0.01), owner='player')
        started = time.process_time()
        for _ in range(ticks):
            flight.step(w, found, dt=1.0 / 60.0)
        return (time.process_time() - started) / ticks * 1000.0

    def busy(self, kind):
        """Milliseconds for the small case, or None if this machine is loaded.

        The reference is **the same code at a twentieth of the scale**, which
        is the only calibration that degrades the way the thing being measured
        does: a box running another suite takes two or three times as long over
        identical arithmetic, because cores, caches and memory bandwidth are
        all shared, and a fixed millisecond bound then fails for a reason
        nothing in this file can fix.  Skipping and saying so is honest;
        loosening the bound until it passes anywhere would leave a number that
        no longer means "fits in a frame", which is the only thing it is for.
        """
        spent = self.tick(16, kind)
        return None if spent > FIGHT_BUDGET_MS * QUIET else spent

    @traced
    def test_a_busy_fights_worth_costs_a_fraction_of_a_frame(self, rocket):
        """What a match actually holds: a rocket a second from each of eight."""
        spent = self.tick(16, rocket)
        assert spent < FIGHT_BUDGET_MS, \
            '%.2f ms a tick for 16 projectiles' % (spent,)

    @traced
    def test_several_hundred_still_fit_in_one_frame(self, rocket):
        """Far past anything a match produces, and it must still not drop a frame.

        The margin here is real but not large -- 12.5 ms measured against a
        16 ms budget -- which is why the machine is checked first rather than
        the bound being relaxed: three hundred projectiles in the air at once
        is already several times what a busy eight-player fight produces, so
        the honest place to spend the margin is on the number rather than on
        the budget.
        """
        if self.busy(rocket) is None:
            pytest.skip('this machine is loaded; a frame budget would measure it')
        spent = self.tick(300, rocket)
        assert spent < FLOOD_BUDGET_MS, \
            '%.1f ms a tick for 300 projectiles' % (spent,)

    @traced
    def test_the_cost_is_one_swept_cast_each_and_no_more(self, rocket):
        """Linear, not quadratic: nothing here compares projectiles to each other."""
        few, many = self.tick(32, rocket), self.tick(128, rocket)
        assert many < few * 8.0, '%.2f ms then %.2f ms' % (few, many)
