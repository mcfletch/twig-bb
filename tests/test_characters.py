"""What a combatant's body is doing, and which clip shows it.

No GL and no models: the state machine is a pure function of what the rules
already know about somebody, which is what makes it testable at boundary
speeds, mid-air and on the frame somebody lands.
"""
import pytest

from twig_bb import characters


def moving(**named):
    return characters.Motion(**named)


class TestLocomotion:
    def test_standing_still(self):
        machine = characters.Locomotion()
        assert machine.update(moving(), 0.1) == 'idle'

    def test_walking_and_running(self):
        machine = characters.Locomotion()
        assert machine.update(moving(speed=1.5), 0.1) == 'walk'
        assert machine.update(moving(speed=6.0), 0.1) == 'run'

    def test_the_boundaries(self):
        machine = characters.Locomotion()
        assert machine.update(moving(speed=characters.WALK_SPEED - 0.01), 0.1) == 'idle'
        assert machine.update(moving(speed=characters.WALK_SPEED), 0.1) == 'walk'
        assert machine.update(moving(speed=characters.RUN_SPEED), 0.1) == 'run'

    def test_leaving_the_ground_rising_and_falling(self):
        machine = characters.Locomotion()
        assert machine.update(moving(grounded=False, rising=True), 0.1) == 'jump'
        assert machine.update(moving(grounded=False), 0.1) == 'fall'

    def test_landing_is_played_out_then_left(self):
        machine = characters.Locomotion()
        machine.update(moving(grounded=False), 0.1)
        assert machine.update(moving(), 0.05) == 'land'
        assert machine.update(moving(), 0.05) == 'land'
        assert machine.update(moving(), characters.LAND_TIME) == 'idle'

    def test_landing_at_speed_still_lands(self):
        machine = characters.Locomotion()
        machine.update(moving(grounded=False), 0.1)
        assert machine.update(moving(speed=6.0), 0.05) == 'land'

    def test_leaving_the_ground_cuts_a_landing_short(self):
        machine = characters.Locomotion()
        machine.update(moving(grounded=False), 0.1)
        assert machine.update(moving(), 0.05) == 'land'
        assert machine.update(moving(grounded=False, rising=True), 0.05) == 'jump'

    def test_turning_on_the_spot(self):
        machine = characters.Locomotion()
        assert machine.update(moving(turning=2.0), 0.1) == 'turn_left'
        assert machine.update(moving(turning=-2.0), 0.1) == 'turn_right'

    def test_turning_while_walking_is_still_walking(self):
        machine = characters.Locomotion()
        assert machine.update(moving(speed=2.0, turning=2.0), 0.1) == 'walk'

    def test_a_slow_turn_is_not_a_turn(self):
        machine = characters.Locomotion()
        assert machine.update(moving(turning=0.2), 0.1) == 'idle'

    def test_death_beats_everything_and_stays(self):
        machine = characters.Locomotion()
        assert machine.update(moving(dead=True, speed=6.0), 0.1) == 'die'
        assert machine.update(moving(speed=6.0), 0.1) == 'die'

    def test_a_respawn_starts_over(self):
        machine = characters.Locomotion()
        machine.update(moving(dead=True), 0.1)
        machine.reset()
        assert machine.update(moving(), 0.1) == 'idle'

    def test_one_shots_are_named(self):
        assert 'die' in characters.ONE_SHOTS
        assert 'walk' not in characters.ONE_SHOTS


class TestWeaponClip:
    def test_empty_handed(self):
        assert characters.weapon_clip(moving()) is None

    def test_carrying(self):
        assert characters.weapon_clip(moving(weapon='rifle')) == 'hold_rifle'

    def test_aiming_what_can_be_aimed(self):
        assert characters.weapon_clip(moving(weapon='rifle', aiming=True)) == 'aim_rifle'
        assert characters.weapon_clip(moving(weapon='pistol', aiming=True)) == 'aim_pistol'

    def test_aiming_what_cannot_is_still_carrying(self):
        assert characters.weapon_clip(
            moving(weapon='shotgun', aiming=True)) == 'hold_shotgun'

    def test_firing_beats_aiming(self):
        assert characters.weapon_clip(
            moving(weapon='rifle', aiming=True, firing=True)) == 'fire_rifle'

    def test_a_weapon_with_no_clips_of_its_own(self):
        # Grenades borrow the rocket launcher's two-handed stance.
        assert characters.weapon_clip(moving(weapon='grenade')) == 'hold_rocket'

    def test_a_weapon_nothing_knows_about(self):
        assert characters.weapon_clip(moving(weapon='harpoon')) == 'hold_rifle'

    def test_the_dead_aim_nothing(self):
        assert characters.weapon_clip(moving(weapon='rifle', dead=True)) is None


class TestMotion:
    def test_from_a_walker(self):
        class Walker:
            def base(self):
                return (1.0, 2.0, 3.0)
            velocity = (3.0, 0.0, 4.0)
            grounded = True

        motion = characters.motion_of(Walker(), weapon='rifle')
        assert motion.speed == pytest.approx(5.0)
        assert motion.grounded and motion.weapon == 'rifle'

    def test_a_rising_body_is_not_grounded(self):
        class Walker:
            velocity = (0.0, 4.0, 0.0)
            grounded = False

        motion = characters.motion_of(Walker())
        assert not motion.grounded and motion.rising

    def test_horizontal_speed_only(self):
        class Walker:
            velocity = (0.0, 9.0, 0.0)
            grounded = True

        assert characters.motion_of(Walker()).speed == pytest.approx(0.0)

    def test_a_body_that_is_not_there(self):
        motion = characters.motion_of(None, dead=True)
        assert motion.speed == 0.0 and motion.dead


class _Layer:
    def __init__(self):
        self.tracks = []
        self.played = []
        self.stopped = 0

    def play(self, name, **named):
        self.played.append((name, named))
        self.tracks.append(name)

    def stop(self, **named):
        self.stopped += 1
        self.tracks = []


class _Model:
    """A CharacterModel's surface, without a file or a window behind it."""

    def __init__(self, clips=('idle', 'walk', 'run', 'die', 'hold_rifle',
                              'fire_rifle')):
        self.clips = dict.fromkeys(clips)
        self.group = object()
        self.layers = {}
        self.played = []
        self.attached = []
        self.updated = 0.0

    def mask(self, *bones, **named):
        return frozenset({1, 2})

    def play(self, name, **named):
        self.played.append((name, named))

    def layer(self, name, **named):
        return self.layers.setdefault(name, _Layer())

    def update(self, dt):
        self.updated += dt

    def reset(self):
        self.played = []

    def attach(self, point, node):
        if point != 'grip':
            return None
        self.attached.append(node)
        return node

    def detach(self, point, node):
        if node in self.attached:
            self.attached.remove(node)
            return True
        return False


class TestCharacter:
    def test_it_plays_the_movement_and_the_weapon(self):
        figure = characters.Character(_Model())
        played = figure.update(moving(speed=6.0, weapon='rifle'), 0.1)
        assert played == ('run', 'hold_rifle')
        assert figure.model.played[0][0] == 'run'
        assert figure.model.layers['upper'].tracks == ['hold_rifle']
        assert figure.model.updated == pytest.approx(0.1)

    def test_a_one_shot_does_not_loop(self):
        figure = characters.Character(_Model())
        figure.update(moving(dead=True), 0.1)
        assert figure.model.played[-1][1]['loop'] is False

    def test_a_shot_fades_in_faster_than_a_stance(self):
        figure = characters.Character(_Model())
        figure.update(moving(weapon='rifle'), 0.1)      # the first pose snaps
        figure.update(moving(weapon='rifle', firing=True), 0.1)
        fade = figure.model.layers['upper'].played[-1][1]['fade']
        assert fade == characters.Character.QUICK_FADE

    def test_the_first_pose_after_a_reset_snaps(self):
        """What a fade would blend from is the rest pose, which is a T-pose."""
        figure = characters.Character(_Model())
        figure.update(moving(), 0.1)
        assert figure.model.played[-1][1]['fade'] == 0.0
        figure.update(moving(speed=6.0), 0.1)
        assert figure.model.played[-1][1]['fade'] == characters.Character.FADE

    def test_putting_the_weapon_away_stops_the_upper_layer(self):
        figure = characters.Character(_Model())
        figure.update(moving(weapon='rifle'), 0.1)
        figure.update(moving(), 0.1)
        assert figure.model.layers['upper'].stopped == 1

    def test_a_clip_the_model_has_not_got_is_simply_not_played(self):
        figure = characters.Character(_Model(clips=('idle',)))
        assert figure.update(moving(speed=6.0), 0.1) == ('run', None)
        assert figure.model.played == []

    def test_holding_and_dropping(self):
        figure = characters.Character(_Model())
        weapon = object()
        assert figure.hold('rifle', weapon) is True
        assert figure.holding == 'rifle' and figure.model.attached == [weapon]
        figure.drop()
        assert figure.holding is None and figure.model.attached == []

    def test_changing_weapons_leaves_one_in_the_hand(self):
        figure = characters.Character(_Model())
        first, second = object(), object()
        figure.hold('rifle', first)
        figure.hold('pistol', second)
        assert figure.model.attached == [second]

    def test_a_body_with_no_art_still_answers(self):
        drawn = object()
        figure = characters.Character(group=drawn)
        assert figure.group is drawn
        assert figure.update(moving(speed=6.0, weapon='rifle'), 0.1) == (
            'run', 'hold_rifle')
        assert figure.hold('rifle', object()) is False
        assert figure.drop() is None

    def test_holding_nothing(self):
        figure = characters.Character(_Model())
        assert figure.hold('rifle', None) is False

    def test_a_model_with_no_hand_to_put_it_in(self):
        class NoGrip(_Model):
            def attach(self, point, node):
                return None

        figure = characters.Character(NoGrip())
        assert figure.hold('rifle', object()) is False
        assert figure.holding is None


class TestLoading:
    def test_the_shipped_figures_load_and_satisfy_the_contract(self):
        pytest.importorskip('OpenGLContext.character')
        for name in characters.BUILDS:
            figure = characters.load(name)
            assert figure.model is not None, name
            assert figure.model.humanoid.complete, name
            missing = set(characters.MOVEMENT) - set(figure.model.clips)
            assert not missing, (name, missing)
            assert 'grip' in figure.model.points, name

    def test_every_weapon_family_has_its_clips(self):
        pytest.importorskip('OpenGLContext.character')
        figure = characters.load(characters.BUILDS[0])
        for family in set(characters.WEAPON_FAMILY.values()):
            assert 'hold_%s' % family in figure.model.clips
            assert 'fire_%s' % family in figure.model.clips
        for family in characters.AIMED:
            assert 'aim_%s' % family in figure.model.clips

    def test_a_name_that_resolves_to_nothing(self):
        drawn = object()
        figure = characters.load('nobody-by-that-name', group=drawn)
        assert figure.model is None and figure.group is drawn


class TestCast:
    def test_one_figure_each_taken_round_robin(self):
        cast = characters.Cast(['a', 'b', 'c'], builds=['x', 'y'])
        assert len(cast) == 3 and 'b' in cast
        assert cast.of('a') is not None
        assert cast.of('nobody') is None

    def test_a_subtree_per_body(self):
        cast = characters.Cast(['a'], builds=['nothing'])
        assert cast.subtree('a') is None
        assert cast.subtree('nobody') is None

    def test_updating_somebody_who_is_not_in_it(self):
        cast = characters.Cast([], builds=['nothing'])
        assert cast.update('nobody', moving(), 0.1) == ('', None)

    def test_the_shipped_builds_are_the_default(self):
        cast = characters.Cast(['a'])
        assert cast.of('a').model is not None


class _Armoury:
    """An armoury with no files behind it: one distinct node per key."""

    def __init__(self, keys=('rifle', 'pistol')):
        self.models = {key: object() for key in keys}
        self.asked = []

    def of(self, key):
        self.asked.append(key)
        return self.models.get(key)


class TestCarrying:
    def test_what_the_rules_say_it_carries_ends_up_in_its_hand(self):
        armoury = _Armoury()
        figure = characters.Character(_Model(), armoury=armoury)
        figure.update(moving(weapon='rifle'), 0.1)
        assert figure.holding == 'rifle'
        assert figure.model.attached == [armoury.models['rifle']]

    def test_changing_weapon_swaps_the_model(self):
        armoury = _Armoury()
        figure = characters.Character(_Model(), armoury=armoury)
        figure.update(moving(weapon='rifle'), 0.1)
        figure.update(moving(weapon='pistol'), 0.1)
        assert figure.model.attached == [armoury.models['pistol']]

    def test_carrying_the_same_thing_costs_nothing(self):
        armoury = _Armoury()
        figure = characters.Character(_Model(), armoury=armoury)
        for _ in range(5):
            figure.update(moving(weapon='rifle'), 0.1)
        assert armoury.asked == ['rifle']

    def test_the_dead_keep_hold_of_it(self):
        """A weapon that blinks out on the frame somebody dies reads as a bug."""
        armoury = _Armoury()
        figure = characters.Character(_Model(), armoury=armoury)
        figure.update(moving(weapon='rifle'), 0.1)
        figure.update(moving(weapon='rifle', dead=True), 0.1)
        assert figure.holding == 'rifle'
        assert figure.model.attached == [armoury.models['rifle']]

    def test_empty_handed_stays_empty(self):
        figure = characters.Character(_Model(), armoury=_Armoury())
        figure.update(moving(), 0.1)
        assert figure.holding is None and figure.model.attached == []

    def test_a_weapon_with_no_model_leaves_the_hand_empty(self):
        figure = characters.Character(_Model(), armoury=_Armoury(keys=()))
        figure.update(moving(weapon='rifle'), 0.1)
        assert figure.holding is None and figure.model.attached == []

    def test_a_figure_with_no_armoury_still_plays_the_clips(self):
        figure = characters.Character(_Model())
        assert figure.update(moving(weapon='rifle'), 0.1) == ('idle', 'hold_rifle')
        assert figure.holding is None


class TestComingBack:
    """A respawn, which is the one thing that clears a latched death."""

    def test_a_respawned_body_stops_playing_dead(self):
        figure = characters.Character(_Model())
        figure.update(moving(dead=True), 0.1)
        assert figure.update(moving(speed=6.0), 0.1)[0] == 'run'

    def test_it_snaps_rather_than_easing_out_of_dying(self):
        figure = characters.Character(_Model())
        figure.update(moving(dead=True), 0.1)
        figure.update(moving(), 0.1)
        assert figure.model.played[-1][1]['fade'] == 0.0

    def test_being_dead_twice_over_is_not_a_respawn(self):
        figure = characters.Character(_Model())
        figure.update(moving(dead=True), 0.1)
        assert figure.update(moving(dead=True, speed=6.0), 0.1)[0] == 'die'


class TestArmoury:
    def test_one_model_per_key_loaded_once(self):
        armoury = characters.Armoury(table=None)
        assert armoury.of('rifle') is None
        assert armoury.of('') is None

    def test_it_reads_the_weapon_table_for_the_file(self):
        from twig_bb import weapons as weapontable
        armoury = characters.Armoury(weapontable.default_table())
        first = armoury.of('rifle')
        assert first is not None
        assert armoury.of('rifle') is first, 'loaded once and shared'

    def test_a_weapon_the_table_has_never_heard_of(self):
        from twig_bb import weapons as weapontable
        assert characters.Armoury(weapontable.default_table()).of('harpoon') is None

    def test_the_model_is_mounted_by_the_grip_it_declares(self):
        from twig_bb import weapons as weapontable
        armoury = characters.Armoury(weapontable.default_table())
        held = armoury.of('rifle')
        # The rifle says it is held 0.15 m from its origin along its own bore,
        # so what comes back is placed by that rather than by the origin.
        assert any(abs(float(value)) > 0.01 for value in held.translation)


class TestACastThatIsArmed:
    def test_every_figure_gets_the_armoury(self):
        armoury = _Armoury()
        cast = characters.Cast(['a', 'b'], armoury=armoury)
        assert [figure.armoury for figure in cast.figures.values()] == [armoury] * 2

    def test_the_shipped_figures_end_up_holding_the_shipped_weapons(self):
        """The whole path, with the real files: rules to a rifle in a hand."""
        pytest.importorskip('OpenGLContext.character')
        from twig_bb import weapons as weapontable
        cast = characters.Cast(['a'], armoury=characters.Armoury(
            weapontable.default_table()))
        figure = cast.of('a')
        assert figure.model is not None
        cast.update('a', moving(weapon='rifle'), 0.1)
        assert figure.holding == 'rifle'
        grip = figure.model.point('grip')
        assert figure._held in list(grip.children)
        # And keeps hold of it when it dies: a weapon that vanishes on the
        # frame somebody is shot is the one thing a player would call a bug.
        cast.update('a', moving(weapon='rifle', dead=True), 0.1)
        assert figure.holding == 'rifle' and figure._held in list(grip.children)
