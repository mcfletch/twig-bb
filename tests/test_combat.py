"""Firing a weapon: where the shot goes, what it meets, and what that costs.

The rules of a shot, kept apart from the arena's bookkeeping so each can be
read on its own — and so a shot can be resolved against a constructed world of
three boxes rather than against a level.
"""

from __future__ import annotations

import numpy as np
import pytest

from omi_physics import model
from omi_physics.world import PhysicsWorld

from twitchoglc import arena, collision, combat, weapons
from twitchoglc.surfaces import SurfaceStyle
from twitchoglc.worldgeometry import SurfaceIndex


def _imported_from(node):
    """Every module name one AST node imports, or nothing for other nodes."""
    import ast
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        return [node.module or '']
    return []


def _styled(w, body, style):
    """A collision map saying the whole of one body is made of ``style``."""
    return collision.MapCollision(
        world=w, body=body,
        surfaces=SurfaceIndex(ends=np.array([2]), styles=(style,)))


def world():
    return PhysicsWorld(gravity=model.Gravity(gravity=9.81, direction=(0, -1, 0)))


def wall(w, x):
    e = 20.0
    points = np.array([(x, -e, -e), (x, e, -e), (x, e, e), (x, -e, e)], dtype='d')
    indices = np.array([(0, 1, 2), (0, 2, 3)], dtype='i')
    shape = w.add_shape(model.Shape.trimesh(points, indices))
    return w.add_body(model.Motion(type=model.STATIC),
                      collider=model.Collider(shape=shape), position=(0, 0, 0))


def match(bots=1, **named):
    made = arena.Arena(weapons=weapons.default_table(), **named)
    made.add('player', position=(0.0, 0.0, 0.0), name='You')
    for index in range(bots):
        made.add('bot%d' % index, position=(10.0 + index * 5, 0.0, 0.0),
                 bot=True, name='Bot %d' % index)
    return made


def rifle():
    return weapons.default_table().by_key('rifle')


class TestWhatAShotMeets:

    def test_a_shot_at_a_combatant_hits_them(self):
        found = match()
        hits = combat.fire(world(), found, 'player', rifle(),
                           origin=(0, 0, 0), direction=(1, 0, 0))
        assert [hit.target for hit in hits] == ['bot0']

    def test_a_shot_into_empty_space_hits_nothing(self):
        found = match()
        assert combat.fire(world(), found, 'player', rifle(),
                           origin=(0, 0, 0), direction=(0, 1, 0)) == []

    def test_a_wall_stops_the_shot(self):
        """The property that makes cover mean something."""
        w = world()
        wall(w, x=5.0)
        found = match()
        hits = combat.fire(w, found, 'player', rifle(),
                           origin=(0, 0, 0), direction=(1, 0, 0))
        assert [hit.target for hit in hits] == ['']
        assert found.combatant('bot0').health == arena.STARTING_HEALTH

    def test_a_shot_stops_at_the_nearest_of_two_targets(self):
        found = match(bots=2)
        hits = combat.fire(world(), found, 'player', rifle(),
                           origin=(0, 0, 0), direction=(1, 0, 0))
        assert [hit.target for hit in hits] == ['bot0']

    def test_a_shooter_does_not_hit_themselves(self):
        found = match()
        hits = combat.fire(world(), found, 'player', rifle(),
                           origin=(0, 0, 0), direction=(1, 0, 0))
        assert 'player' not in [hit.target for hit in hits]

    def test_the_dead_are_not_shot_again(self):
        found = match()
        found.damage('bot0', 500, by='player')
        assert combat.fire(world(), found, 'player', rifle(),
                           origin=(0, 0, 0), direction=(1, 0, 0)) == []

    def test_a_target_beyond_the_weapons_range_is_not_hit(self):
        found = match()
        found.combatant('bot0').position = np.array([5000.0, 0.0, 0.0])
        assert combat.fire(world(), found, 'player', rifle(),
                           origin=(0, 0, 0), direction=(1, 0, 0)) == []

    def test_the_hit_says_where_it_landed(self):
        """What an impact effect and a hit marker are placed by.

        On the *near* side of the target: a trace stops at the surface it
        meets, so an effect placed at the hit point sits on the body rather
        than inside or behind it.
        """
        found = match()
        hit = combat.fire(world(), found, 'player', rifle(),
                          origin=(0, 1.0, 0), direction=(1, 0, 0))[0]
        assert hit.point is not None
        assert 0.0 < float(hit.point[0]) < 10.0


class TestWhatAShotReports:
    """Every trace that met something, not only the ones that hurt somebody.

    An impact effect, an impact sound and — later — a splash centre are all
    placed from a trace that met the level, so a shot that reported only its
    casualties would leave three features with nothing to hang on.
    """

    def test_a_hit_on_the_world_names_no_target(self):
        """The documented spelling for "the level, not a person"."""
        w = world()
        wall(w, x=5.0)
        hit = combat.fire(w, match(), 'player', rifle(),
                          origin=(0, 0, 0), direction=(1, 0, 0))[0]
        assert hit.target == ''
        assert not hit.on_somebody
        assert hit.damage == 0

    def test_a_hit_on_a_combatant_names_them(self):
        hit = combat.fire(world(), match(), 'player', rifle(),
                          origin=(0, 0, 0), direction=(1, 0, 0))[0]
        assert hit.target == 'bot0'
        assert hit.on_somebody

    def test_a_trace_that_meets_nothing_is_not_reported(self):
        """A miss is an empty list; the *shot* is what always happened."""
        assert combat.fire(world(), match(), 'player', rifle(),
                           origin=(0, 0, 0), direction=(0, 1, 0)) == []

    def test_every_pellet_is_reported_separately(self):
        """Eight pellets that hit a wall are eight impacts, not one."""
        w = world()
        wall(w, x=5.0)
        gun = weapons.default_table().by_key('shotgun')
        hits = combat.fire(w, match(), 'player', gun, origin=(0, 0, 0),
                           direction=(1, 0, 0), spread=1.0, seed=3)
        assert len(hits) == gun.pellets
        assert {hit.target for hit in hits} == {''}

    def test_a_world_hit_carries_the_surface_it_met(self):
        """What lets an impact on metal differ from one on stone."""
        w = world()
        body = wall(w, x=5.0)
        hit = combat.fire(w, match(), 'player', rifle(), origin=(0, 0, 0),
                          direction=(1, 0, 0),
                          surfaces=_styled(w, body, SurfaceStyle(name='metal')))[0]
        assert hit.surface.name == 'metal'

    def test_a_hit_on_a_person_carries_no_surface(self):
        """A body is not made of the level, and must not report as though it were."""
        w = world()
        body = wall(w, x=50.0)
        hit = combat.fire(w, match(), 'player', rifle(), origin=(0, 0, 0),
                          direction=(1, 0, 0),
                          surfaces=_styled(w, body, SurfaceStyle(name='metal')))[0]
        assert hit.target == 'bot0'
        assert hit.surface is None

    def test_without_an_index_a_world_hit_reports_no_surface(self):
        """None is the honest answer, not a guessed default."""
        w = world()
        wall(w, x=5.0)
        hit = combat.fire(w, match(), 'player', rifle(),
                          origin=(0, 0, 0), direction=(1, 0, 0))[0]
        assert hit.surface is None

    def test_a_world_hit_faces_back_along_the_trace(self):
        """What an impact effect is oriented from."""
        w = world()
        wall(w, x=5.0)
        hit = combat.fire(w, match(), 'player', rifle(),
                          origin=(0, 0, 0), direction=(1, 0, 0))[0]
        assert float(np.dot(hit.normal, (1, 0, 0))) < 0.0


class TestWhatAShotSays:
    """Presentation reads events; it must never reach into the rules' state.

    The HUD was written from the shooting code, which is fine for one caller
    and wrong as a pattern: bots fire too, and a player has to see and hear
    *their* shots as well as their own.
    """

    def test_firing_emits_a_fired_event(self):
        found = match()
        combat.fire(world(), found, 'player', rifle(),
                    origin=(0, 1, 0), direction=(1, 0, 0))
        shot = [e for e in found.events if isinstance(e, arena.Fired)]
        assert len(shot) == 1
        assert shot[0].shooter == 'player'
        assert shot[0].weapon == 'rifle'
        assert shot[0].origin == (0.0, 1.0, 0.0)

    def test_a_bot_firing_emits_one_too(self):
        """Both directions of the fight, or half of it is silent."""
        found = match()
        combat.fire(world(), found, 'bot0', rifle(),
                    origin=(10, 1, 0), direction=(-1, 0, 0))
        assert [e.shooter for e in found.events
                if isinstance(e, arena.Fired)] == ['bot0']

    def test_a_shot_that_hits_nothing_still_says_it_was_fired(self):
        """A miss makes a noise, and a player who cannot hear one is deaf to it."""
        found = match()
        combat.fire(world(), found, 'player', rifle(),
                    origin=(0, 0, 0), direction=(0, 1, 0))
        assert [e for e in found.events if isinstance(e, arena.Fired)]

    def test_one_shot_emits_one_fired_event_however_many_pellets(self):
        found = match()
        combat.fire(world(), found, 'player',
                    weapons.default_table().by_key('shotgun'),
                    origin=(0, 0, 0), direction=(1, 0, 0))
        assert len([e for e in found.events if isinstance(e, arena.Fired)]) == 1

    def test_a_wall_impact_emits_an_impact_event(self):
        w = world()
        body = wall(w, x=5.0)
        found = match()
        combat.fire(w, found, 'player', rifle(), origin=(0, 0, 0),
                    direction=(1, 0, 0),
                    surfaces=_styled(w, body, SurfaceStyle(name='metal')))
        met = [e for e in found.events if isinstance(e, arena.Impact)]
        assert len(met) == 1
        assert met[0].surface == 'metal'
        assert not met[0].on_somebody
        assert met[0].by == 'player'

    def test_a_hit_on_a_person_emits_an_impact_naming_them(self):
        found = match()
        combat.fire(world(), found, 'player', rifle(),
                    origin=(0, 0, 0), direction=(1, 0, 0))
        met = [e for e in found.events if isinstance(e, arena.Impact)][0]
        assert met.on_somebody and met.target == 'bot0'

    def test_every_pellet_emits_its_own_impact(self):
        """Eight pellets that land are eight effects, not one."""
        w = world()
        wall(w, x=5.0)
        gun = weapons.default_table().by_key('shotgun')
        found = match()
        combat.fire(w, found, 'player', gun, origin=(0, 0, 0),
                    direction=(1, 0, 0), spread=1.0, seed=3)
        assert len([e for e in found.events
                    if isinstance(e, arena.Impact)]) == gun.pellets

    def test_a_shot_that_meets_nothing_emits_no_impact(self):
        found = match()
        combat.fire(world(), found, 'player', rifle(),
                    origin=(0, 0, 0), direction=(0, 1, 0))
        assert not [e for e in found.events if isinstance(e, arena.Impact)]

    def test_nothing_in_the_shooting_rules_can_reach_the_presentation(self):
        import ast
        import inspect
        for node in ast.walk(ast.parse(inspect.getsource(combat))):
            for name in _imported_from(node):
                assert not name.startswith('OpenGLContext')
                assert name.rpartition('.')[2] not in (
                    'hud', 'effects', 'firstperson', 'viewer')


class TestWhatAShotCosts:

    def test_a_hit_takes_the_weapons_damage(self):
        found = match()
        gun = rifle()
        combat.fire(world(), found, 'player', gun,
                    origin=(0, 0, 0), direction=(1, 0, 0))
        assert found.combatant('bot0').health == \
            arena.STARTING_HEALTH - int(gun.damage)

    def test_a_hit_emits_a_damage_event(self):
        found = match()
        combat.fire(world(), found, 'player', rifle(),
                    origin=(0, 0, 0), direction=(1, 0, 0))
        assert [event for event in found.events
                if isinstance(event, arena.Damaged)]

    def test_enough_hits_kill(self):
        found = match()
        for _ in range(20):
            combat.fire(world(), found, 'player', rifle(),
                        origin=(0, 0, 0), direction=(1, 0, 0))
        assert not found.combatant('bot0').alive

    def test_a_kill_scores(self):
        found = match()
        for _ in range(20):
            combat.fire(world(), found, 'player', rifle(),
                        origin=(0, 0, 0), direction=(1, 0, 0))
        assert found.score('player') == 1


class TestWhoIsUnderTheCrosshair:
    """Nothing in the world said who anybody was.

    A fight was against interchangeable red shapes, with no way to tell an
    opponent you were hunting from one who had just arrived.  The answer has
    to be the one a *shot* would give: a name over somebody a shot would miss
    is worse than no name at all.
    """

    def looking(self, w, found, direction=(1, 0, 0)):
        return combat.who_is_at(w, found, 'player', (0, 0, 0), direction)

    def test_somebody_in_the_open_is_named(self):
        assert self.looking(world(), match()) == 'bot0'

    def test_empty_space_names_nobody(self):
        assert self.looking(world(), match(), direction=(0, 1, 0)) == ''

    def test_a_wall_between_them_names_nobody(self):
        """Which is also what stops this finding people through geometry."""
        w = world()
        wall(w, x=5.0)
        assert self.looking(w, match()) == ''

    def test_the_nearest_of_two_is_the_one_named(self):
        found = match(bots=2)
        assert self.looking(world(), found) == 'bot0'

    def test_the_dead_are_not_named(self):
        found = match()
        found.damage('bot0', 500, by='player')
        assert self.looking(world(), found) == ''

    def test_the_looker_is_never_named(self):
        assert self.looking(world(), match(), direction=(-1, 0, 0)) != 'player'

    def test_a_heading_of_nothing_names_nobody(self):
        assert self.looking(world(), match(), direction=(0, 0, 0)) == ''

    def test_asking_damages_nobody(self):
        found = match()
        self.looking(world(), found)
        assert found.combatant('bot0').health == arena.STARTING_HEALTH

    def test_asking_puts_nothing_on_the_event_stream(self):
        """It is asked every frame; a question must not be an announcement."""
        found = match()
        self.looking(world(), found)
        assert found.events == []

    def test_the_staged_bodies_are_taken_back_out(self):
        """Or a later shot meets a capsule this question left behind."""
        w, found = world(), match()
        self.looking(w, found)
        assert combat.raycast.raycast(w, (0, 0, 0), (1, 0, 0)) is None


class TestHowManyHitsAKillTakes:
    """Reported as a pistol needing thirty-odd hits to kill a bot.

    The arithmetic disagreed with the report by a factor of four, which means
    the interesting question was never "is the damage too low" but "are the
    hits landing at all" — and retuning the table would have buried whichever
    it was.  So the table's own claim is what is pinned here: every weapon
    kills a fresh, unarmoured target in the number of hits its numbers say,
    down every range a fight happens at.  If that is ever not true again, this
    fails and the *shot* is where to look; if the pistol is genuinely too weak
    to play with, this changes when the table does and says so.
    """

    RANGES = (3.0, 6.0, 12.0, 25.0)

    def duel(self, gap):
        found = arena.Arena(weapons=weapons.default_table())
        found.add('player', position=(0.0, 0.0, 0.0), name='You')
        found.add('bot0', position=(gap, 0.0, 0.0), bot=True, name='Bot')
        return found

    def hits_to_kill(self, key, gap, spread=0.0):
        """Aimed traces, eye to eye, until the target is down."""
        gun = weapons.default_table().by_key(key)
        w, found = world(), self.duel(gap)
        eye = np.array([0.0, combat.EYE_HEIGHT, 0.0])
        aim = combat.aim_at(found, 'player', 'bot0')
        for shot in range(1, 200):
            combat.fire(w, found, 'player', gun, origin=eye, direction=aim,
                        spread=spread, seed=shot)
            if not found.combatant('bot0').alive:
                return shot
        return None

    @pytest.mark.parametrize('gap', RANGES)
    def test_the_pistol_takes_what_its_damage_says(self, gap):
        gun = weapons.default_table().by_key('pistol')
        due = -(-arena.STARTING_HEALTH // int(gun.damage))       # round up
        assert self.hits_to_kill('pistol', gap) == due

    @pytest.mark.parametrize('gap', RANGES)
    def test_the_rifle_does_too(self, gap):
        gun = weapons.default_table().by_key('rifle')
        due = -(-arena.STARTING_HEALTH // int(gun.damage))
        assert self.hits_to_kill('rifle', gap) == due

    def test_the_pistol_is_not_the_weakest_thing_in_the_table(self):
        """Per second, which is what a fight is measured in."""
        table = weapons.default_table()

        def rate(key):
            gun = table.by_key(key)
            return (float(gun.damage) * max(1, int(gun.pellets))
                    / float(gun.fireInterval))
        assert rate('pistol') > rate('rifle') * 0.5

    def test_a_trace_down_the_middle_lands_at_every_range(self):
        """The half that was actually in doubt: that an aimed shot connects."""
        for gap in self.RANGES + (40.0, 60.0):
            found, w = self.duel(gap), world()
            eye = np.array([0.0, combat.EYE_HEIGHT, 0.0])
            hits = combat.fire(w, found, 'player',
                               weapons.default_table().by_key('pistol'),
                               origin=eye,
                               direction=combat.aim_at(found, 'player', 'bot0'))
            assert [hit.target for hit in hits] == ['bot0'], gap


class TestAWeaponThatFiresSeveralPellets:
    """A shotgun is one trigger pull and several rays."""

    def shotgun(self):
        return weapons.default_table().by_key('shotgun')

    def test_it_casts_one_ray_per_pellet(self):
        found = match()
        gun = self.shotgun()
        assert gun.pellets > 1
        hits = combat.fire(world(), found, 'player', gun,
                           origin=(0, 0, 0), direction=(1, 0, 0), spread=0.0)
        assert len(hits) == gun.pellets

    def test_each_pellet_does_its_own_damage(self):
        found = match()
        gun = self.shotgun()
        combat.fire(world(), found, 'player', gun,
                    origin=(0, 0, 0), direction=(1, 0, 0), spread=0.0)
        assert found.combatant('bot0').health == \
            arena.STARTING_HEALTH - int(gun.damage) * gun.pellets

    def test_spread_scatters_the_pellets(self):
        """Otherwise every pellet lands in the same place and the cone is a lie."""
        found = match()
        gun = self.shotgun()
        spread = combat.fire(world(), found, 'player', gun, origin=(0, 0, 0),
                             direction=(1, 0, 0), spread=0.2, seed=1)
        points = {tuple(np.round(hit.point, 4)) for hit in spread}
        assert len(points) > 1

    def test_the_scatter_is_reproducible_from_its_seed(self):
        """§11: the same inputs give the same result on one machine."""
        first = combat.fire(world(), match(), 'player', self.shotgun(),
                            origin=(0, 0, 0), direction=(1, 0, 0),
                            spread=0.2, seed=7)
        second = combat.fire(world(), match(), 'player', self.shotgun(),
                             origin=(0, 0, 0), direction=(1, 0, 0),
                             spread=0.2, seed=7)
        assert [np.round(hit.point, 6).tolist() for hit in first] == \
            [np.round(hit.point, 6).tolist() for hit in second]

    def test_a_different_seed_scatters_differently(self):
        first = combat.fire(world(), match(), 'player', self.shotgun(),
                            origin=(0, 0, 0), direction=(1, 0, 0),
                            spread=0.2, seed=1)
        second = combat.fire(world(), match(), 'player', self.shotgun(),
                             origin=(0, 0, 0), direction=(1, 0, 0),
                             spread=0.2, seed=2)
        assert [hit.point.tolist() for hit in first] != \
            [hit.point.tolist() for hit in second]


class TestPuttingPeopleInTheWorldAndTakingThemOut:
    """The world between shots must be the map, and must stay that size.

    A body per combatant per shot is a physics world that grows for the whole
    match, and every ray cast walks every body in it — so a fight that has
    been going for ten minutes would cast more slowly than one that had just
    started, for no reason a player could see.
    """

    def test_staging_a_shot_does_not_grow_the_world(self):
        w = world()
        found = match()
        for _ in range(50):
            combat.fire(w, found, 'player', rifle(), origin=(0, 0, 0),
                        direction=(0, 1, 0))
        assert w.body_count <= 2                # the one bot, and room to spare

    def test_the_capsules_are_gone_again_between_shots(self):
        """A trace must never meet a body left behind by an earlier one."""
        w = world()
        found = match()
        combat.fire(w, found, 'player', rifle(), origin=(0, 0, 0),
                    direction=(1, 0, 0))
        assert not [body for body in range(w.body_count)
                    if int(w.collider_shape[body]) >= 0]

    def test_a_staged_body_is_where_the_combatant_is(self):
        """Reused bodies have to be *moved*, not merely switched back on."""
        w = world()
        found = match()
        combat.fire(w, found, 'player', rifle(), origin=(0, 0, 0),
                    direction=(1, 0, 0))
        found.combatant('bot0').position = np.array([0.0, 0.0, 10.0])
        hits = combat.fire(w, found, 'player', rifle(), origin=(0, 0, 0),
                           direction=(0, 0, 1))
        assert [hit.target for hit in hits] == ['bot0']

    def test_a_shot_with_more_people_in_it_still_stages_them_all(self):
        w = world()
        found = match(bots=1)
        combat.fire(w, found, 'player', rifle(), origin=(0, 0, 0),
                    direction=(0, 1, 0))
        crowded = match(bots=4)
        for index in range(4):
            crowded.combatant('bot%d' % index).position = np.array(
                [0.0, 0.0, 5.0 + index * 5])
        hits = combat.fire(w, crowded, 'player', rifle(), origin=(0, 0, 0),
                           direction=(0, 0, 1))
        assert [hit.target for hit in hits] == ['bot0']


class TestWhereACombatantIs:
    """A shot meets a body, and a bot's body is a capsule around its feet."""

    def test_a_shot_at_chest_height_hits(self):
        found = match()
        hits = combat.fire(world(), found, 'player', rifle(),
                           origin=(0, 1.0, 0), direction=(1, 0, 0))
        assert [hit.target for hit in hits] == ['bot0']

    def test_a_shot_over_their_head_misses(self):
        found = match()
        assert combat.fire(world(), found, 'player', rifle(),
                           origin=(0, 6.0, 0), direction=(1, 0, 0)) == []

    def test_a_shot_wide_of_them_misses(self):
        found = match()
        assert combat.fire(world(), found, 'player', rifle(),
                           origin=(0, 0, 5.0), direction=(1, 0, 0)) == []


class TestLineOfSight:
    """What a bot asks before it decides it can shoot at something."""

    def test_two_combatants_in_the_open_can_see_each_other(self):
        found = match()
        assert combat.can_see(world(), found, 'player', 'bot0')

    def test_a_wall_between_them_blocks_it(self):
        w = world()
        wall(w, x=5.0)
        assert not combat.can_see(w, match(), 'player', 'bot0')

    def test_a_combatant_who_is_not_there_cannot_be_seen(self):
        assert not combat.can_see(world(), match(), 'player', 'nobody')

    def test_the_dead_cannot_be_seen(self):
        """A bot must not keep aiming at a corpse."""
        found = match()
        found.damage('bot0', 500, by='player')
        assert not combat.can_see(world(), found, 'player', 'bot0')

    def test_it_is_the_eyes_that_look_rather_than_the_feet(self):
        """A knee-high ledge between two players does not blind them."""
        w = world()
        e = 20.0
        points = np.array([(-e, 0.2, -e), (e, 0.2, -e), (e, 0.2, e), (-e, 0.2, e)],
                          dtype='d')
        indices = np.array([(0, 1, 2), (0, 2, 3)], dtype='i')
        shape = w.add_shape(model.Shape.trimesh(points, indices))
        w.add_body(model.Motion(type=model.STATIC),
                   collider=model.Collider(shape=shape), position=(0, 0, 0))
        assert combat.can_see(w, match(), 'player', 'bot0')


class TestAimingAtSomebody:

    def test_the_aim_points_from_one_to_the_other(self):
        found = match()
        heading = combat.aim_at(found, 'player', 'bot0')
        assert heading is not None
        assert float(heading[0]) == pytest.approx(1.0, abs=0.2)

    def test_aiming_at_nobody_gives_nothing(self):
        assert combat.aim_at(match(), 'player', 'nobody') is None

    def test_the_aim_is_a_unit_heading(self):
        heading = combat.aim_at(match(), 'player', 'bot0')
        assert float(np.linalg.norm(heading)) == pytest.approx(1.0, abs=1e-6)

    def test_aiming_at_yourself_gives_nothing(self):
        assert combat.aim_at(match(), 'player', 'player') is None
