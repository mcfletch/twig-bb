"""twitch's own sections of the developer overlay.

The registry and the drawing are OpenGLContext's and are tested there; what is
tested here is that this game registers the sections it says it does, and that
each answers sensibly against a stand-in viewer -- including the awkward states,
because a debug overlay is most wanted exactly when the thing it is reporting on
is half built.
"""

from __future__ import annotations

import pytest

from OpenGLContext.ui.debugoverlay import DebugOverlay

from twitchoglc import debug as twitchdebug
from twitchoglc import weapons
from twitchoglc.player import PlayerState


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
        twitchdebug.install(viewer)
        titles = [section.title for section in viewer.debugOverlay.sections()]
        assert 'Map' in titles
        assert 'Player' in titles

    def test_installing_twice_does_not_duplicate_a_section(self, viewer):
        twitchdebug.install(viewer)
        twitchdebug.install(viewer)
        titles = [section.title for section in viewer.debugOverlay.sections()]
        assert titles.count('Map') == 1


class TestMapSection:
    def test_it_names_the_map_and_its_family(self, viewer):
        twitchdebug.install(viewer)
        found = rows(viewer, 'Map')
        assert found['name'] == 'ztn3dm1'
        assert found['family'] == 'Quake 3'

    def test_it_counts_the_geometry(self, viewer):
        twitchdebug.install(viewer)
        found = rows(viewer, 'Map')
        assert found['triangles'] == '12345'
        assert found['batches'] == '2'

    def test_it_says_how_many_textures_are_missing(self, viewer):
        twitchdebug.install(viewer)
        assert rows(viewer, 'Map')['missing textures'] == '1'

    def test_a_viewer_with_no_map_yet_says_nothing_rather_than_failing(self):
        viewer = Viewer(loaded=None)
        twitchdebug.install(viewer)
        assert rows(viewer, 'Map') == {}


class TestPlayerSection:
    def test_it_names_the_movement_mode(self, viewer):
        """The mode label used to be drawn over the game; this is its home."""
        twitchdebug.install(viewer)
        assert rows(viewer, 'Player')['mode'] == 'walk'

    def test_it_says_whether_the_camera_is_walking_or_flying(self, viewer):
        twitchdebug.install(viewer)
        assert rows(viewer, 'Player')['navigation'] == 'walking'
        viewer._walking = False
        assert rows(viewer, 'Player')['navigation'] == 'free-fly'

    def test_it_reports_the_position_in_map_units(self, viewer):
        """The engine's own View section gives scene metres; this gives the
        units the entity lump is actually written in."""
        class Platform:
            position = (2.54, 1.0, -0.5, 1.0)

        viewer.getViewPlatform = lambda: Platform()
        twitchdebug.install(viewer)
        found = rows(viewer, 'Player')
        # 2.54 m is 100 map units, and scene -z is map +y.
        assert found['map units'].startswith('100')
        assert 'scene' not in found

    def test_it_reports_health_ammunition_and_the_weapon_in_hand(self, viewer):
        twitchdebug.install(viewer)
        found = rows(viewer, 'Player')
        assert found['health'] == '100'
        assert found['weapon'] == 'pistol'

    def test_it_says_when_the_player_is_under_a_liquid(self, viewer):
        twitchdebug.install(viewer)
        assert rows(viewer, 'Player')['submerged'] == 'no'
        viewer._nav.submerged = True
        assert rows(viewer, 'Player')['submerged'] == 'yes'

    def test_a_free_flying_camera_has_no_submerged_row(self, viewer):
        viewer._nav = None
        twitchdebug.install(viewer)
        assert 'submerged' not in rows(viewer, 'Player')


class TestPhysicsSection:
    def test_there_is_no_physics_section_before_the_world_is_built(self,
                                                                   viewer):
        twitchdebug.install(viewer)
        assert rows(viewer, 'Physics') == {}

    def test_it_counts_bodies_once_there_is_a_world(self, viewer):
        class World:
            bodies = [object(), object(), object()]
            contacts = []

        viewer._world = World()
        twitchdebug.install(viewer)
        assert rows(viewer, 'Physics')['bodies'] == '3'
