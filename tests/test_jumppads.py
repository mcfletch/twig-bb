"""Push volumes: `trigger_push` and `trigger_monsterjump`, per SPEC-TRIGGER-PUSH."""

from __future__ import annotations

import numpy as np
import pytest

from twig_bb import jumppads
from twig_bb.entities import Entity
from twig_bb.worldgeometry import SCENE_SCALE

MAP_GRAVITY = jumppads.DEFAULT_GRAVITY


def direction(**keys) -> np.ndarray:
    """The unit push direction an entity's orientation keys give."""
    return jumppads.push_direction(Entity(keys))


def velocity(scene_gravity=None, **keys) -> np.ndarray:
    """The map-unit velocity a `trigger_push` imparts."""
    return jumppads.push_velocity(Entity(keys), MAP_GRAVITY,
                                  scene_gravity or MAP_GRAVITY)


# -- direction ---------------------------------------------------------------

def test_the_angle_key_is_a_yaw_only_shorthand():
    """SPEC-TRIGGER-PUSH §3.2, §6.3: `angle a` is the triple (0, a, 0)."""
    assert direction(angle='90') == pytest.approx((0.0, 1.0, 0.0))
    assert direction(angles='0 90 0') == pytest.approx((0.0, 1.0, 0.0))


def test_angle_minus_one_is_straight_up_and_minus_two_straight_down():
    """SPEC-TRIGGER-PUSH §3.4: two triples are not orientations at all."""
    assert direction(angle='-1') == pytest.approx((0.0, 0.0, 1.0))
    assert direction(angle='-2') == pytest.approx((0.0, 0.0, -1.0))


def test_the_special_case_is_matched_against_the_whole_triple():
    """SPEC-TRIGGER-PUSH §3.4: `angles "10 -1 0"` is an ordinary orientation."""
    assert direction(angles='0 -1 0') == pytest.approx((0.0, 0.0, 1.0))
    ordinary = direction(angles='10 -1 0')
    assert not np.allclose(ordinary, (0.0, 0.0, 1.0))


def test_the_special_case_needs_exact_equality():
    """SPEC-TRIGGER-PUSH §3.4: a value of -1.0001 is not a special case."""
    assert not np.allclose(direction(angle='-1.0001'), (0.0, 0.0, 1.0))


def test_no_orientation_at_all_gives_the_zero_vector():
    """SPEC-TRIGGER-PUSH §3.5: the direction is computed only for a non-zero triple."""
    assert direction(classname='trigger_push') == pytest.approx((0.0, 0.0, 0.0))
    assert direction(angle='0') == pytest.approx((0.0, 0.0, 0.0))
    assert direction(angles='0 0 0') == pytest.approx((0.0, 0.0, 0.0))


def test_angle_360_is_the_mappers_way_of_pushing_along_plus_x():
    """SPEC-TRIGGER-PUSH §3.7: 360 passes the non-zero test and yaws like 0."""
    assert direction(angle='360') == pytest.approx((1.0, 0.0, 0.0))


def test_a_roll_alone_makes_the_triple_non_zero_and_pushes_along_plus_x():
    """SPEC-TRIGGER-PUSH §6.4: roll does not reach the forward vector."""
    assert direction(angles='0 0 45') == pytest.approx((1.0, 0.0, 0.0))


def test_a_positive_pitch_aims_downward():
    """SPEC-TRIGGER-PUSH §6.2, §6.3: the sign an importer is most likely to flip."""
    assert direction(angles='45 0 0') == pytest.approx(
        (0.70710678, 0.0, -0.70710678))
    assert direction(angles='-45 0 0') == pytest.approx(
        (0.70710678, 0.0, 0.70710678))


def test_the_direction_is_a_unit_vector():
    """SPEC-TRIGGER-PUSH §6.5, §3.9."""
    for angles in ('30 40 50', '-20 200 0', '89 1 0'):
        assert float(np.linalg.norm(direction(angles=angles))) == pytest.approx(1.0)


# -- imparted velocity --------------------------------------------------------

def test_the_velocity_is_the_direction_times_speed_times_ten():
    """SPEC-TRIGGER-PUSH §2.1, §2.2."""
    assert velocity(angle='-1', speed='100') == pytest.approx((0.0, 0.0, 1000.0))


def test_the_default_speed_is_a_thousand():
    """SPEC-TRIGGER-PUSH §1.2, §2.3: 10 000 units per second."""
    assert velocity(angle='-1') == pytest.approx((0.0, 0.0, 10000.0))


def test_a_speed_of_exactly_zero_is_the_same_as_an_absent_speed():
    """SPEC-TRIGGER-PUSH §1.4: the substitution is unconditional on the value."""
    assert velocity(angle='-1', speed='0') == pytest.approx((0.0, 0.0, 10000.0))


def test_a_pad_with_no_orientation_is_a_freeze_volume():
    """SPEC-TRIGGER-PUSH §3.6: a zero direction times any speed pins the player,
    because §2.4 assigns rather than adds.  Maps may rely on it."""
    volume = jumppads.PushVolume(
        mins=np.zeros(3), maxs=np.ones(3),
        velocity=velocity(classname='trigger_push', speed='500'), once=False)
    assert volume.velocity == pytest.approx((0.0, 0.0, 0.0))
    assert not volume.is_noop


@pytest.mark.parametrize('authored,expected', [
    ({'angle': '-1'}, (0, 0, 10000)),
    ({'angle': '-2'}, (0, 0, -10000)),
    ({'angle': '360'}, (10000, 0, 0)),
    ({'angle': '90'}, (0, 10000, 0)),
    ({'angles': '-45 0 0'}, (7071, 0, 7071)),
    ({'angles': '45 0 0'}, (7071, 0, -7071)),
    ({}, (0, 0, 0)),
])
def test_the_worked_reference_values_reproduce(authored, expected):
    """SPEC-TRIGGER-PUSH §6.6."""
    assert velocity(**authored) == pytest.approx(expected, abs=1.0)


def test_a_pad_is_rescaled_when_the_scene_runs_at_a_different_gravity():
    """The plan's rule: rescaling by sqrt(g_scene / g_map) preserves apex and
    range, changing only the flight time."""
    slow = velocity(angle='-1', speed='100', scene_gravity=MAP_GRAVITY / 4.0)
    assert slow == pytest.approx((0.0, 0.0, 500.0))


def test_worldspawn_gravity_overrides_the_default():
    """SPEC-TRIGGER-PUSH §8.2: a map may set `gravity` on worldspawn."""
    entities = [Entity({'classname': 'worldspawn', 'gravity': '200'})]
    assert jumppads.map_gravity(entities) == pytest.approx(200.0)


def test_a_map_with_no_gravity_key_uses_eight_hundred():
    """SPEC-TRIGGER-PUSH §8.1, §8.2."""
    assert jumppads.map_gravity([Entity({'classname': 'worldspawn'})]) \
        == pytest.approx(800.0)
    assert jumppads.map_gravity([]) == pytest.approx(800.0)


def test_the_apex_sanity_check_from_the_spec_holds():
    """SPEC-TRIGGER-PUSH §8.5: a `speed` of 4*sqrt(h) reaches height h."""
    height = 256.0
    speed = 4.0 * height ** 0.5
    v = velocity(angle='-1', speed=str(speed))
    apex = float(v[2]) ** 2 / (2.0 * MAP_GRAVITY)
    assert apex == pytest.approx(height, rel=1e-6)


# -- monsterjump --------------------------------------------------------------

def test_monsterjump_sets_horizontal_from_speed_and_vertical_from_height():
    """SPEC-TRIGGER-PUSH §9.4: `height` *is* the vertical velocity."""
    entity = Entity({'classname': 'trigger_monsterjump', 'angle': '90',
                     'speed': '300', 'height': '400'})
    v = jumppads.monsterjump_velocity(entity, MAP_GRAVITY, MAP_GRAVITY)
    assert v == pytest.approx((0.0, 300.0, 400.0))


def test_monsterjump_defaults_are_two_hundred_each():
    """SPEC-TRIGGER-PUSH §9.4."""
    entity = Entity({'classname': 'trigger_monsterjump', 'angle': '360'})
    v = jumppads.monsterjump_velocity(entity, MAP_GRAVITY, MAP_GRAVITY)
    assert v == pytest.approx((200.0, 0.0, 200.0))


def test_a_monsterjump_yaw_of_zero_is_read_as_three_hundred_and_sixty():
    """SPEC-TRIGGER-PUSH §9.4: unlike `trigger_push`, it cannot aim nowhere."""
    entity = Entity({'classname': 'trigger_monsterjump', 'angle': '0'})
    v = jumppads.monsterjump_velocity(entity, MAP_GRAVITY, MAP_GRAVITY)
    assert v == pytest.approx((200.0, 0.0, 200.0))


# -- volumes from a map ------------------------------------------------------

class FakeMap:
    """The little of a map that push volumes need: entities and model bounds."""

    def __init__(self, entities, bounds):
        self.entities = [Entity(keys) for keys in entities]
        self._bounds = bounds

    def model_bounds(self, index):
        return self._bounds.get(index)


def _map(**keys):
    entities = [{'classname': 'worldspawn'},
                dict({'classname': 'trigger_push', 'model': '*1'}, **keys)]
    bounds = {1: (np.array([0.0, 0.0, 0.0]), np.array([128.0, 128.0, 32.0]))}
    return FakeMap(entities, bounds)


def test_a_push_entity_becomes_a_volume_from_its_brush_models_bounds():
    """SPEC-TRIGGER-PUSH §5.1: the submodel's AABB is the entity's bounds."""
    volumes = jumppads.push_volumes(_map(angle='-1'), MAP_GRAVITY)
    assert len(volumes) == 1
    assert volumes[0].velocity[2] > 0


def test_the_volume_is_grown_by_two_units_on_every_axis():
    """SPEC-TRIGGER-PUSH §5.4, §5.5: linking grows both boxes by one unit each,
    so the effective slack is two units and a strict test misses pads that work
    in the original.  The literal 2 is the spec's number, not this module's
    constant -- asserting on the constant would only restate the code."""
    volume = jumppads.push_volumes(_map(angle='-1'), MAP_GRAVITY)[0]
    assert list(volume.mins) == pytest.approx([-2.0, -2.0, -2.0])
    assert list(volume.maxs) == pytest.approx([130.0, 130.0, 34.0])


def test_the_origin_key_offsets_the_volume():
    """SPEC-TRIGGER-PUSH §5.3."""
    volume = jumppads.push_volumes(_map(angle='-1', origin='10 20 30'), MAP_GRAVITY)[0]
    assert float(volume.mins[0]) == pytest.approx(10.0 - jumppads.TRIGGER_SLACK)


def test_the_push_once_spawnflag_is_read():
    """SPEC-TRIGGER-PUSH §4.1: bit 1 removes the volume after the first contact."""
    assert jumppads.push_volumes(_map(angle='-1', spawnflags='1'), MAP_GRAVITY)[0].once
    assert not jumppads.push_volumes(_map(angle='-1'), MAP_GRAVITY)[0].once
    assert not jumppads.push_volumes(_map(angle='-1', spawnflags='6'),
                                     MAP_GRAVITY)[0].once


def test_a_pad_whose_brush_model_is_missing_is_skipped():
    world = FakeMap([{'classname': 'trigger_push', 'model': '*9', 'angle': '-1'}], {})
    assert jumppads.push_volumes(world, MAP_GRAVITY) == []


def test_a_monsterjump_entity_also_becomes_a_volume():
    """SPEC-TRIGGER-PUSH §9.4: despite the name, it throws players in this fork."""
    entities = [{'classname': 'trigger_monsterjump', 'model': '*1', 'angle': '-1'}]
    bounds = {1: (np.zeros(3), np.full(3, 64.0))}
    volumes = jumppads.push_volumes(FakeMap(entities, bounds), MAP_GRAVITY)
    assert len(volumes) == 1
    assert volumes[0].retrigger_interval == pytest.approx(0.1)


def test_a_plain_push_volume_has_no_retrigger_limit():
    """SPEC-TRIGGER-PUSH §7.1: the push is reapplied every frame while inside."""
    assert jumppads.push_volumes(_map(angle='-1'), MAP_GRAVITY)[0].retrigger_interval \
        == 0.0


def test_a_map_with_no_push_entities_yields_no_volumes():
    """The sample Alien Arena map is exactly this case."""
    assert jumppads.push_volumes(FakeMap([{'classname': 'light'}], {}),
                                 MAP_GRAVITY) == []


# -- the running system ------------------------------------------------------

def _system(**keys):
    volumes = jumppads.push_volumes(_map(**keys), MAP_GRAVITY)
    return jumppads.PushSystem(volumes)


def test_standing_inside_a_pad_yields_its_velocity():
    system = _system(angle='-1', speed='100')
    result = system.update(1 / 60.0, _scene((64.0, 64.0, 16.0)))
    assert result is not None
    assert result[1] > 0                    # upward in scene space (+Y)


def test_standing_outside_a_pad_yields_nothing():
    system = _system(angle='-1', speed='100')
    assert system.update(1 / 60.0, _scene((1000.0, 1000.0, 1000.0))) is None


def test_the_push_is_reapplied_every_frame_while_inside():
    """SPEC-TRIGGER-PUSH §7.1, §7.2: the player is velocity-clamped while inside."""
    system = _system(angle='-1', speed='100')
    inside = _scene((64.0, 64.0, 16.0))
    first = system.update(1 / 60.0, inside)
    second = system.update(1 / 60.0, inside)
    assert first is not None and second is not None
    assert second == pytest.approx(first)


def test_a_push_once_volume_fires_only_once():
    """SPEC-TRIGGER-PUSH §4.1, §7.3."""
    system = _system(angle='-1', speed='100', spawnflags='1')
    inside = _scene((64.0, 64.0, 16.0))
    assert system.update(1 / 60.0, inside) is not None
    assert system.update(1 / 60.0, inside) is None


def test_noclip_generates_no_contacts():
    """SPEC-TRIGGER-PUSH §7.8."""
    system = _system(angle='-1', speed='100')
    inside = _scene((64.0, 64.0, 16.0))
    assert system.update(1 / 60.0, inside, noclip=True) is None
    assert system.update(1 / 60.0, inside) is not None


def test_the_two_unit_slack_catches_a_player_just_outside_the_brush():
    """SPEC-TRIGGER-PUSH §5.5, §5.7: a pad flush with the floor is reachable."""
    system = _system(angle='-1', speed='100')
    just_outside = _scene((64.0, 64.0, 33.5))       # 1.5 units above the pad's top
    assert system.update(1 / 60.0, just_outside) is not None


def test_a_monsterjump_volume_is_rate_limited():
    """SPEC-TRIGGER-PUSH §9.4: retrigger at most once every 0.1 seconds."""
    entities = [{'classname': 'trigger_monsterjump', 'model': '*1', 'angle': '-1'}]
    bounds = {1: (np.zeros(3), np.full(3, 64.0))}
    volumes = jumppads.push_volumes(FakeMap(entities, bounds), MAP_GRAVITY)
    system = jumppads.PushSystem(volumes)
    inside = _scene((32.0, 32.0, 32.0))
    assert system.update(0.01, inside) is not None
    assert system.update(0.01, inside) is None      # too soon
    fired = [system.update(0.01, inside) is not None for _ in range(12)]
    # exactly one further launch inside the next 0.12 s, once 0.1 s has passed
    assert sum(fired) == 1
    assert fired.index(True) == 9                   # t = 0.11 s


def test_a_system_with_no_volumes_never_fires():
    system = jumppads.PushSystem([])
    assert system.update(1 / 60.0, np.zeros(3)) is None


def _scene(map_point):
    """A map-space point as the scene-space position the system is given."""
    from twig_bb.worldgeometry import to_scene_points
    return to_scene_points(np.array([map_point]))[0]


def test_the_velocity_handed_back_is_in_scene_units():
    """The character controller works in metres per second, +Y up."""
    system = _system(angle='-1', speed='100')
    result = system.update(1 / 60.0, _scene((64.0, 64.0, 16.0)))
    assert result[1] == pytest.approx(1000.0 * SCENE_SCALE, rel=1e-5)


def test_a_player_well_clear_of_a_pad_is_not_pushed():
    """The volume is bounded: the slack of §5.4-§5.5 widens it, it does not
    make it unbounded."""
    system = _system(angle='-1', speed='100')
    assert system.update(1 / 60.0, _scene((400.0, 64.0, 16.0))) is None


# -- aimed pads, the version 46 variant ---------------------------------------

def test_an_aimed_pad_launches_towards_its_destination():
    """`SPEC-Q3PUSH §2.1`: a version 46 pad is aimed at a place, not pointed in
    a direction, and every one of the 236 pads in the OpenArena maps is."""
    velocity = jumppads.aimed_velocity(
        source=np.array([0.0, 0.0, 0.0]),
        destination=np.array([512.0, 0.0, 256.0]),
        gravity=800.0)
    assert velocity[0] > 0                       # towards it, in x
    assert velocity[1] == pytest.approx(0.0)
    assert velocity[2] > 0                       # and upwards


def test_the_arc_actually_arrives(monkeypatch):
    """Integrating the launch under the same gravity must pass through the
    destination, or the pad throws the player at the wall beside it."""
    source = np.array([0.0, 0.0, 0.0])
    destination = np.array([512.0, 128.0, 256.0])
    gravity = 800.0
    velocity = jumppads.aimed_velocity(source, destination, gravity)
    flight = jumppads.arc_flight_time(source, destination, gravity)
    landing = source + velocity * flight
    landing[2] -= 0.5 * gravity * flight * flight
    assert landing == pytest.approx(destination, abs=1e-3)


def test_the_arc_clears_the_higher_end():
    """`SPEC-Q3PUSH §2.3`: the apex is above both ends, so the player goes over
    the lip of the platform rather than into it."""
    source = np.array([0.0, 0.0, 0.0])
    destination = np.array([512.0, 0.0, 256.0])
    velocity = jumppads.aimed_velocity(source, destination, 800.0)
    apex = velocity[2] ** 2 / (2 * 800.0)
    assert apex == pytest.approx(256.0 + jumppads.ARC_CLEARANCE)


def test_a_pad_aimed_straight_up_has_no_horizontal_throw():
    velocity = jumppads.aimed_velocity(np.zeros(3), np.array([0.0, 0.0, 300.0]),
                                       800.0)
    assert velocity[0] == pytest.approx(0.0)
    assert velocity[1] == pytest.approx(0.0)
    assert velocity[2] > 0


def test_a_pad_aimed_downwards_still_arcs_upwards_first():
    """The destination below the pad is a drop, and an arc still clears the
    edge the player is standing behind."""
    velocity = jumppads.aimed_velocity(np.array([0.0, 0.0, 512.0]),
                                       np.array([256.0, 0.0, 0.0]), 800.0)
    assert velocity[2] > 0


def test_the_map_gravity_is_what_the_arc_is_solved_under():
    """A low-gravity map's pads have to be weaker, or every one overshoots."""
    strong = jumppads.aimed_velocity(np.zeros(3), np.array([512.0, 0.0, 256.0]),
                                     800.0)
    weak = jumppads.aimed_velocity(np.zeros(3), np.array([512.0, 0.0, 256.0]),
                                   200.0)
    assert weak[2] < strong[2]


def _aimed_map(destination=(0, 0, 512), targetname='pad1', target='pad1',
               classname='target_position'):
    """A source of entities and bounds, as :func:`push_volumes` wants."""
    entities = [
        Entity({'classname': 'worldspawn'}),
        Entity({'classname': 'trigger_push', 'model': '*1', 'target': target}),
        Entity({'classname': classname, 'targetname': targetname,
                'origin': '%g %g %g' % tuple(destination)}),
    ]

    class _Source:
        def __init__(self):
            self.entities = entities

        def model_bounds(self, index):
            if index != 1:
                return None
            return (np.array([-32.0, -32.0, 0.0]), np.array([32.0, 32.0, 16.0]))

    return _Source()


def test_a_pad_with_a_target_is_read_as_aimed():
    volumes = jumppads.push_volumes(_aimed_map())
    assert len(volumes) == 1
    assert volumes[0].velocity[2] > 0


@pytest.mark.parametrize('classname', ['target_position', 'target_push',
                                       'target_location'])
def test_every_observed_destination_classname_is_accepted(classname):
    """`SPEC-Q3PUSH §1.3` names the three seen in the shipped maps; the aim is
    the `targetname` match, not the classname."""
    volumes = jumppads.push_volumes(_aimed_map(classname=classname))
    assert volumes[0].velocity[2] > 0


def test_the_targetname_match_ignores_case():
    volumes = jumppads.push_volumes(_aimed_map(targetname='Pad1', target='pad1'))
    assert volumes[0].velocity[2] > 0


def test_a_pad_whose_target_resolves_to_nothing_falls_back_to_its_angle():
    """`SPEC-Q3PUSH §2.4`: a dangling target leaves only the version 38 keys."""
    volumes = jumppads.push_volumes(_aimed_map(target='nosuchthing'))
    assert len(volumes) == 1
    assert volumes[0].velocity.tolist() == [0.0, 0.0, 0.0]      # §3.6, frozen


def test_the_arc_starts_at_the_top_of_the_pad_not_its_floor():
    """A player standing on the pad is launched from where they are, and a pad
    is a thin brush on the ground."""
    volumes = jumppads.push_volumes(_aimed_map(destination=(512, 0, 512)))
    flight = jumppads.arc_flight_time(np.array([0.0, 0.0, 16.0]),
                                      np.array([512.0, 0.0, 512.0]), 800.0)
    assert volumes[0].velocity[0] == pytest.approx(512.0 / flight, rel=1e-6)
