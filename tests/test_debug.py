"""twig-bb's own sections of the developer overlay.

The registry and the drawing are OpenGLContext's and are tested there; what is
tested here is that this game registers the sections it says it does, and that
each answers sensibly against a stand-in viewer -- including the awkward states,
because a debug overlay is most wanted exactly when the thing it is reporting on
is half built.
"""

from __future__ import annotations

import pytest

from OpenGLContext.ui.debugoverlay import DebugOverlay

from twig_bb import debug as twigdebug
from twig_bb import weapons
from twig_bb.frameclock import FrameClock
from twig_bb.player import PlayerState


class FakeWorld:
    triangle_count = 12345
    batches = [object(), object()]


class FakeAtlas:
    pages = [object()]


class FakeLoaded:
    name = 'ztn3dm1'
    family = 'Quake 3'
    world = FakeWorld()
    atlas = FakeAtlas()

    def missing_textures(self):
        return ['textures/base/absent']

    def unscripted_surfaces(self):
        return []

    def unplaceable_pickups(self):
        return {}


class FakeMode:
    name = 'walk'


class FakeDefinition:
    movementMode = FakeMode()


class FakeNav:
    submerged = False
    grounded = True


class Viewer:
    """A context with the parts the providers read, and nothing else."""

    def __init__(self, **named):
        self.loaded = FakeLoaded()
        self.contextDefinition = FakeDefinition()
        self.player = PlayerState.starting(weapons.default_table())
        self._walking = True
        self._nav = FakeNav()
        self._world = None
        self.overlay = DebugOverlay()
        for name, value in named.items():
            setattr(self, name, value)

    @property
    def debugOverlay(self):
        return self.overlay

    def getViewPlatform(self):
        return None

    def physicsWorld(self):
        return self._world


@pytest.fixture
def viewer():
    return Viewer()


def rows(viewer, title):
    for section in viewer.debugOverlay.sections():
        if section.title == title:
            return dict(section.rows)
    return {}


class TestInstallation:
    def test_it_registers_the_sections_this_game_owns(self, viewer):
        twigdebug.install(viewer)
        titles = [section.title for section in viewer.debugOverlay.sections()]
        assert 'Map' in titles
        assert 'Player' in titles

    def test_installing_twice_does_not_duplicate_a_section(self, viewer):
        twigdebug.install(viewer)
        twigdebug.install(viewer)
        titles = [section.title for section in viewer.debugOverlay.sections()]
        assert titles.count('Map') == 1


class TestMapSection:
    def test_it_names_the_map_and_its_family(self, viewer):
        twigdebug.install(viewer)
        found = rows(viewer, 'Map')
        assert found['name'] == 'ztn3dm1'
        assert found['family'] == 'Quake 3'

    def test_it_counts_the_geometry(self, viewer):
        twigdebug.install(viewer)
        found = rows(viewer, 'Map')
        assert found['triangles'] == '12345'
        assert found['batches'] == '2'

    def test_it_says_how_many_textures_are_missing(self, viewer):
        twigdebug.install(viewer)
        assert rows(viewer, 'Map')['missing textures'] == '1'

    def test_a_viewer_with_no_map_yet_says_nothing_rather_than_failing(self):
        viewer = Viewer(loaded=None)
        twigdebug.install(viewer)
        assert rows(viewer, 'Map') == {}

    def test_it_credits_the_map_it_is_showing(self, viewer):
        """A level is somebody's work; the overlay says whose, and under what."""
        from twig_bb.mapnotice import MapNotice
        viewer.notice = MapNotice(name='ztn3dm1', title='Blood Run',
                                  author='Tyrann', pack='OpenArena maps',
                                  licence='CC BY-SA 3.0')
        twigdebug.install(viewer)
        found = rows(viewer, 'Map')
        assert found['title'] == 'Blood Run'
        assert found['author'] == 'Tyrann'
        assert found['licence'] == 'CC BY-SA 3.0'

    def test_a_map_that_credits_nobody_grows_no_empty_rows(self, viewer):
        from twig_bb.mapnotice import MapNotice
        viewer.notice = MapNotice(name='ztn3dm1')
        twigdebug.install(viewer)
        found = rows(viewer, 'Map')
        assert 'title' not in found and 'author' not in found
        assert 'licence' not in found

    def test_it_counts_the_speakers_that_found_a_sound(self):
        """"Why is it silent" is answered by this number being zero."""
        from twig_bb.speakers import from_entities
        from twig_bb.entities import Entity

        class Found:
            def resolve(self, noise):
                return '/content/' + noise

        viewer = Viewer(speakers=from_entities([
            Entity({'classname': 'target_speaker', 'origin': '0 0 0',
                    'noise': 'sound/world/wind1.wav'}),
        ], Found()))
        twigdebug.install(viewer)
        assert rows(viewer, 'Map')['speakers'] == '1'

    def test_it_counts_the_surfaces_no_script_defines(self):
        """A still pool of lava is content nobody has, not a broken animator."""
        class Unscripted(FakeLoaded):
            def unscripted_surfaces(self):
                return ['textures/liquids/protolava', 'textures/base/wall']

        viewer = Viewer(loaded=Unscripted())
        twigdebug.install(viewer)
        assert rows(viewer, 'Map')['unscripted surfaces'] == '2'

    def test_a_fully_scripted_map_omits_the_row(self):
        twigdebug.install(Viewer())
        assert 'unscripted surfaces' not in rows(Viewer(), 'Map')

    def test_a_viewer_with_no_speakers_built_yet_omits_the_row(self):
        twigdebug.install(Viewer())
        assert 'speakers' not in rows(Viewer(), 'Map')

    def test_it_counts_the_pickups_it_has_nothing_for(self):
        """A map whose weapon circuit is all content nobody has plays like a
        map with no weapons in it, which reads as a broken reader."""
        class Unanswered(FakeLoaded):
            def unplaceable_pickups(self):
                return {'item_quad': 3, 'weapon_bfg': 1}

        viewer = Viewer(loaded=Unanswered())
        twigdebug.install(viewer)
        assert rows(viewer, 'Map')['pickups not answered'] == '4'

    def test_a_map_this_game_answers_entirely_omits_the_row(self):
        twigdebug.install(Viewer())
        assert 'pickups not answered' not in rows(Viewer(), 'Map')

    def test_it_counts_the_pickups_that_are_placed(self):
        from twig_bb import items, projectiles, rules
        viewer = Viewer(rules=rules.Rules(
            None, minds={}, flight=projectiles.Projectiles(),
            ))
        viewer.rules.pickups = items.Pickups([])
        twigdebug.install(viewer)
        assert rows(viewer, 'Map')['items'] == '0'

    def test_it_says_what_the_map_can_kill_you_with(self):
        """Both hazards are invisible from inside the game when they are absent.

        A map whose liquid brushes name a material nobody has reports no
        volumes and its lava is scenery; a level with no floor under it is a
        fall that never ends.
        """
        from twig_bb import falling, liquids, projectiles, rules
        viewer = Viewer(rules=rules.Rules(
            None, minds={}, flight=projectiles.Projectiles(),
            harm=liquids.LiquidHarm(liquids.LiquidVolumes([])),
            floor=falling.KillFloor(-137.5)))
        twigdebug.install(viewer)
        found = rows(viewer, 'Map')
        assert found['liquid volumes'] == '0'
        assert found['kill floor (m)'] == '-137.5'

    def test_a_map_not_being_walked_in_yet_omits_both(self):
        twigdebug.install(Viewer())
        found = rows(Viewer(), 'Map')
        assert 'liquid volumes' not in found
        assert 'kill floor (m)' not in found


class TestWhichLiquidThePlayerIsIn:
    """"Submerged: True" cannot tell a right liquid from a wrong one."""

    def submerged_in(self, kind):
        import numpy as np

        from twig_bb import liquids

        class Swimming:
            submerged = True
            grounded = False

            def camera_position(self):
                return (5.0, 2.0, 5.0)

        pool = liquids.LiquidVolumes([
            liquids.LiquidVolume(mins=np.array((0, 0, 0), 'd'),
                                 maxs=np.array((10, 5, 10), 'd'), kind=kind)])
        viewer = Viewer(_nav=Swimming(), _liquids=pool)
        twigdebug.install(viewer)
        return rows(viewer, 'Player')['submerged']

    def test_the_liquid_is_named(self):
        assert self.submerged_in('lava') == 'lava'

    def test_a_swimmer_at_the_surface_is_named_by_their_body(self):
        """The eye leaves the water a head's height before the body does.

        A swimmer lifting themselves out spends those moments with the camera
        in the air and the rest of them in the pool, and the row is there to
        name the liquid rather than to say "something".
        """
        import numpy as np

        from twig_bb import liquids

        class Surfacing:
            submerged = True

            def camera_position(self):
                return (5.0, 6.0, 5.0)

            def feet_position(self):
                return (5.0, 4.0, 5.0)

        pool = liquids.LiquidVolumes([
            liquids.LiquidVolume(mins=np.array((0, 0, 0), 'd'),
                                 maxs=np.array((10, 5, 10), 'd'), kind='water')])
        viewer = Viewer(_nav=Surfacing(), _liquids=pool)
        twigdebug.install(viewer)
        assert rows(viewer, 'Player')['submerged'] == 'water'

    def test_being_under_with_no_volumes_read_still_says_so(self):
        class Swimming:
            submerged = True

        viewer = Viewer(_nav=Swimming(), _liquids=None)
        twigdebug.install(viewer)
        assert rows(viewer, 'Player')['submerged'] == 'yes'


class TestPlayerSection:
    def test_it_names_the_movement_mode(self, viewer):
        """The mode label used to be drawn over the game; this is its home."""
        twigdebug.install(viewer)
        assert rows(viewer, 'Player')['mode'] == 'walk'

    def test_it_says_whether_the_camera_is_walking_or_flying(self, viewer):
        twigdebug.install(viewer)
        assert rows(viewer, 'Player')['navigation'] == 'walking'
        viewer._walking = False
        assert rows(viewer, 'Player')['navigation'] == 'free-fly'

    def test_it_reports_the_position_in_map_units(self, viewer):
        """The engine's own View section gives scene metres; this gives the
        units the entity lump is actually written in."""
        class Platform:
            position = (2.54, 1.0, -0.5, 1.0)

        viewer.getViewPlatform = lambda: Platform()
        twigdebug.install(viewer)
        found = rows(viewer, 'Player')
        # 2.54 m is 100 map units, and scene -z is map +y.
        assert found['map units'].startswith('100')
        assert 'scene' not in found

    def test_it_reports_health_ammunition_and_the_weapon_in_hand(self, viewer):
        twigdebug.install(viewer)
        found = rows(viewer, 'Player')
        assert found['health'] == '100'
        assert found['weapon'] == 'pistol'

    def test_it_says_when_the_player_is_under_a_liquid(self, viewer):
        twigdebug.install(viewer)
        assert rows(viewer, 'Player')['submerged'] == 'no'
        viewer._nav.submerged = True
        assert rows(viewer, 'Player')['submerged'] == 'yes'

    def test_a_free_flying_camera_has_no_submerged_row(self, viewer):
        viewer._nav = None
        twigdebug.install(viewer)
        assert 'submerged' not in rows(viewer, 'Player')

    def test_it_reports_the_timestep_the_simulation_is_being_given(self, viewer):
        viewer._clock = FrameClock()
        viewer._clock.reset(0.0)
        viewer._clock.tick(0.016)
        twigdebug.install(viewer)
        found = rows(viewer, 'Player')
        assert found['dt ms'] == '16'
        assert 'behind' not in found

    def test_a_stalling_game_says_the_world_is_running_slowly(self, viewer):
        """The row that makes an unplayable game legible.

        A clamped step means the world advances slower than the wall clock, and
        no other number on the overlay says so -- the frame rate reports the
        renderer, and the renderer is fine.
        """
        viewer._clock = FrameClock()
        viewer._clock.reset(0.0)
        viewer._clock.tick(1.0)
        twigdebug.install(viewer)
        found = rows(viewer, 'Player')
        assert found['real ms'] == '1000'
        # 0.95s, not 1.0: the 50ms the simulation *did* get is not lost time.
        assert found['behind'] == '5% speed, 0.9s lost'

    def test_a_viewer_with_no_clock_yet_omits_the_rows(self, viewer):
        twigdebug.install(viewer)
        assert 'dt ms' not in rows(viewer, 'Player')


class TestPhysicsSection:
    def test_there_is_no_physics_section_before_the_world_is_built(self,
                                                                   viewer):
        twigdebug.install(viewer)
        assert rows(viewer, 'Physics') == {}

    def test_it_counts_bodies_once_there_is_a_world(self, viewer):
        class World:
            bodies = [object(), object(), object()]
            contacts = []

        viewer._world = World()
        twigdebug.install(viewer)
        assert rows(viewer, 'Physics')['bodies'] == '3'


class TestTheCombatSection:
    """What a fight is doing that cannot be seen from inside the game.

    A rocket that never arrives and a projectile budget that is full look
    exactly the same to a player; this is the only place the difference shows.
    """

    class Context:
        pass

    def context(self):
        from twig_bb import arena, effects, projectiles, weapons
        made = self.Context()
        made.arena = arena.Arena(weapons=weapons.default_table())
        made.arena.add('player', name='You')
        made.flight = projectiles.Projectiles(projectiles.default_table())
        made.effects = effects.Effects(made.arena)
        return made

    def rows(self, context):
        return dict(twigdebug.combat_provider(context)())

    def test_it_says_how_much_of_the_budget_is_in_the_air(self):
        from twig_bb import projectiles
        context = self.context()
        context.flight.launch(
            context.flight.table.by_key(projectiles.ROCKET),
            origin=(0, 1, 0), direction=(1, 0, 0), owner='player')
        assert self.rows(context)['in flight'].startswith('1 /')

    def test_it_says_what_the_effects_setting_is(self):
        from twig_bb import effects
        context = self.context()
        context.effects.intensity = effects.REDUCED
        assert self.rows(context)['effects'] == effects.REDUCED

    def test_it_counts_the_particles_alive(self):
        from twig_bb import arena
        context = self.context()
        context.effects.show([arena.Impact(point=(0, 0, 0), normal=(0, 1, 0),
                                           surface='stone')])
        assert self.rows(context)['particles'] > 0

    def test_it_reports_the_match(self):
        assert 'combatants' in self.rows(self.context())

    def test_a_context_with_no_match_reports_nothing(self):
        assert twigdebug.combat_provider(self.Context())() == []
