"""The viewer's command line, spawn placement and navigation rules.

Everything here is arranged so it can be checked without a live GL window.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

import bspbuilder
from viewersupport import (
    BindingRecorder, HeadlessContext, KeyEvent, NavStub, NullInput,
    look_once, synthetic_map, walking_platform,
)
from twig_bb import collision, maploader, viewer


# -- rendering environment ----------------------------------------------------

def test_the_viewer_draws_in_a_core_profile_with_the_pbr_pass():
    """The plan requires the core profile and the PBR render pass.

    Core is what OpenGLContext resolves to on its own, so the viewer names
    the renderer and the backend and leaves the profile to the engine.
    """
    from OpenGLContext.contextdefinition import ContextDefinition
    assert ContextDefinition().profile == 'core'
    assert os.environ['OPENGLCONTEXT_RENDERER'] == 'pbr'
    assert os.environ['OPENGLCONTEXT_BACKEND'] == 'glfw'


def test_a_capture_run_silences_the_frame_counter():
    options = viewer.build_parser().parse_args(['m.bsp', '--capture', 'out.png'])
    viewer.apply_render_env(options)
    assert os.environ['OPENGLCONTEXT_DISABLE_FPS_DISPLAY'] == '1'


def test_shadows_are_off_by_default_because_the_maps_bake_their_own():
    options = viewer.build_parser().parse_args(['m.bsp'])
    viewer.apply_render_env(options)
    assert os.environ['OPENGLCONTEXT_SHADOWS'] == '0'
    viewer.apply_render_env(viewer.build_parser().parse_args(['m.bsp', '--shadows']))
    assert os.environ['OPENGLCONTEXT_SHADOWS'] == '1'


def test_the_lightmap_exposure_is_a_command_line_option():
    """SPEC-LTMP §11.6: the engine's multiplier must be configurable."""
    options = viewer.build_parser().parse_args(['m.bsp', '--lightmap', '3'])
    assert options.lightmap_strength == pytest.approx(3.0)
    assert viewer.build_parser().parse_args(['m.bsp']).lightmap_strength is None


def test_walking_is_on_by_default_and_can_be_turned_off():
    assert viewer.build_parser().parse_args(['m.bsp']).physics
    assert not viewer.build_parser().parse_args(['m.bsp', '--no-physics']).physics


# -- spawn placement ----------------------------------------------------------

def test_the_avatar_starts_at_a_spawn_point(tmp_path):
    lumps = bspbuilder.v46_quad(size=512.0)
    lumps['entities'] = bspbuilder.entity_text([
        {'classname': 'worldspawn'},
        {'classname': 'info_player_deathmatch', 'origin': '128 256 64'}])
    loaded = maploader.load(synthetic_map(tmp_path, lumps))
    eye, _yaw = viewer.choose_spawn(loaded)
    assert eye[0] == pytest.approx(128 * 0.0254)
    assert eye[1] > 64 * 0.0254         # lifted to eye height above the origin


def test_a_map_with_no_spawn_still_places_the_avatar_inside_it(tmp_path):
    loaded = maploader.load(synthetic_map(tmp_path))
    eye, yaw = viewer.choose_spawn(loaded)
    low, high = loaded.world.bounds
    assert (eye[0] >= low[0]) and (eye[0] <= high[0])
    assert yaw == 0.0


def test_the_spawn_index_selects_among_several(tmp_path):
    lumps = bspbuilder.v46_quad(size=512.0)
    lumps['entities'] = bspbuilder.entity_text([
        {'classname': 'info_player_deathmatch', 'origin': '0 0 0'},
        {'classname': 'info_player_deathmatch', 'origin': '256 0 0'}])
    loaded = maploader.load(synthetic_map(tmp_path, lumps))
    assert viewer.choose_spawn(loaded, 1)[0][0] == pytest.approx(256 * 0.0254)
    # an index past the end wraps rather than failing
    assert viewer.choose_spawn(loaded, 3)[0][0] == pytest.approx(256 * 0.0254)


# -- the yaw convention -------------------------------------------------------
#
# The view platform's angles rotate the world, not the camera, so asserting on
# the sign of ``platform.yaw`` would only restate whatever the code does.  These
# tests measure the direction a step actually goes.

def _forward(map_angle_degrees: float) -> np.ndarray:
    """The world-space direction 'forward' walks for a map's `angle` key."""
    from OpenGLContext.move.physicsplatform import PhysicsViewPlatform
    platform = PhysicsViewPlatform.__new__(PhysicsViewPlatform)
    platform.yaw = viewer.yaw_for_angle(map_angle_degrees)
    return platform._world_dir(1.0, 0.0)


def test_a_map_yaw_of_zero_faces_along_the_maps_plus_x():
    """SPEC-BSP38 §3.3: yaw 0 is along +X, which is +X in scene space too."""
    assert _forward(0.0) == pytest.approx((1.0, 0.0, 0.0), abs=1e-9)


def test_a_map_yaw_of_ninety_faces_along_the_maps_plus_y():
    """+Y in map space is -Z in the scene's Y-up frame."""
    assert _forward(90.0) == pytest.approx((0.0, 0.0, -1.0), abs=1e-9)


def test_a_map_yaw_of_one_eighty_faces_back_along_minus_x():
    assert _forward(180.0) == pytest.approx((-1.0, 0.0, 0.0), abs=1e-9)


def test_a_map_yaw_of_two_seventy_faces_along_the_maps_minus_y():
    assert _forward(270.0) == pytest.approx((0.0, 0.0, 1.0), abs=1e-9)


def test_turning_left_swings_the_gaze_anticlockwise_seen_from_above():
    """A rising platform yaw turns the camera *right*, so turn-left subtracts."""
    from OpenGLContext.move.physicsplatform import PhysicsViewPlatform
    platform = PhysicsViewPlatform.__new__(PhysicsViewPlatform)
    platform.yaw = viewer.yaw_for_angle(0.0)
    before = platform._world_dir(1.0, 0.0)
    platform.yaw -= 0.4                             # what the turn-left key does
    after = platform._world_dir(1.0, 0.0)
    # anticlockwise about +Y takes +X towards -Z ... in the map's frame, that is
    # +X towards +Y, which is what a left turn from yaw 0 means
    assert after[2] < before[2]
    assert float(np.cross(before, after)[1]) > 0


# -- the character ------------------------------------------------------------

def test_the_avatar_is_the_size_the_spec_gives_a_player():
    """SPEC-BSP38 §3.2: 56 units tall on a 32 x 32 footprint."""
    caps = viewer.character_capabilities()
    assert caps.standHeight == pytest.approx(56 * 0.0254)
    assert caps.radius == pytest.approx(16 * 0.0254)
    assert caps.eyeHeight < caps.standHeight


def test_the_collision_world_holds_the_map_as_one_static_mesh(tmp_path):
    loaded = maploader.load(synthetic_map(tmp_path))
    world = collision.from_map(loaded).world
    assert world.body_count == 1
    assert int(world.motion_type[0]) != 2        # not kinematic; a static body


def test_a_map_with_nothing_solid_has_no_collision_world(tmp_path):
    lumps = bspbuilder.v46_quad()
    loaded = maploader.load(synthetic_map(tmp_path, lumps))
    for batch in loaded.world.batches:
        batch.style = batch.style.replace(solid=False)
    assert collision.from_map(loaded) is None


def test_the_jump_pad_impulse_reaches_the_character(tmp_path):
    """The end-to-end rule: a pad sets the capsule's motion outright, which is
    what `apply_impulse` does (SPEC-TRIGGER-PUSH §2.4)."""
    from OpenGLContext.move.physicsplatform import PhysicsViewPlatform
    loaded = maploader.load(synthetic_map(tmp_path))
    world = collision.from_map(loaded).world
    nav = PhysicsViewPlatform(world, viewer.character_capabilities(),
                              position=(0, 1, 0))
    nav.character.vy = -5.0
    nav.apply_impulse(np.array([0.0, 7.0, 0.0]))
    assert nav.character.vy == pytest.approx(7.0)    # replaced, not added
    assert not nav.character.grounded


# -- the core-texture pack ----------------------------------------------------

class _Loaded:
    """Just enough of a loaded map for the core-texture decision."""

    def __init__(self, missing):
        self._missing = missing

    def missing_textures(self):
        return list(self._missing)


def _texture_options(mode='ask', packs=('quake3-core',)):
    options = viewer.build_parser().parse_args(['m.bsp', '--core-textures', mode])
    options.texture_packs = list(packs)
    return options


def test_nothing_is_offered_when_every_texture_was_found(monkeypatch):
    """Only reach for a pack when something is actually missing."""
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack, cache_dir=None: pytest.fail('looked for a pack'))
    assert viewer.available_textures(_Loaded([]), _texture_options()) == []


def test_a_pack_already_unpacked_is_used_without_asking(monkeypatch, tmp_path):
    """Once per user, not once per run — and using what is there is not a
    question worth putting on screen."""
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack, cache_dir=None: str(tmp_path))
    monkeypatch.setattr(viewer.download, 'fetch_pack',
                        lambda pack, cache_dir=None: pytest.fail('should not fetch'))
    assert viewer.available_textures(_Loaded(['a']),
                                     _texture_options()) == [str(tmp_path)]


def test_ask_never_downloads_by_itself(monkeypatch):
    """`ask` means the window asks; loading must not decide on its own."""
    monkeypatch.setattr(viewer.download, 'pack_root', lambda pack, cache_dir=None: None)
    monkeypatch.setattr(viewer.download, 'fetch_pack',
                        lambda pack, cache_dir=None: pytest.fail('should not fetch'))
    assert viewer.available_textures(_Loaded(['a']), _texture_options()) == []


def test_never_neither_looks_nor_downloads(monkeypatch):
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack, cache_dir=None: pytest.fail('looked for a pack'))
    assert viewer.available_textures(_Loaded(['a']), _texture_options('never')) == []


def test_always_downloads_without_asking(monkeypatch, tmp_path):
    """For an automated run, which has no window to ask in."""
    monkeypatch.setattr(viewer.download, 'pack_root', lambda pack, cache_dir=None: None)
    monkeypatch.setattr(viewer.download, 'fetch_pack',
                        lambda pack, cache_dir=None: str(tmp_path))
    assert viewer.available_textures(_Loaded(['a']),
                                     _texture_options('always')) == [str(tmp_path)]


def test_always_fetches_the_pack_the_map_named(monkeypatch, tmp_path):
    """An OpenArena map wants OpenArena's art; the Quake 3 replacement set
    names none of its textures and would be 187 MB wasted."""
    fetched = []
    monkeypatch.setattr(viewer.download, 'pack_root', lambda pack, cache_dir=None: None)
    monkeypatch.setattr(viewer.download, 'fetch_pack',
                        lambda pack, cache_dir=None: fetched.append(pack.key)
                        or str(tmp_path))
    viewer.available_textures(_Loaded(['a']),
                              _texture_options('always', ['openarena-textures']))
    assert fetched == ['openarena-textures']


def test_a_failed_download_does_not_stop_the_map_loading(monkeypatch):
    def boom(pack, cache_dir=None):
        raise OSError('no network')

    monkeypatch.setattr(viewer.download, 'pack_root', lambda pack, cache_dir=None: None)
    monkeypatch.setattr(viewer.download, 'fetch_pack', boom)
    assert viewer.available_textures(_Loaded(['a']), _texture_options('always')) == []


def test_the_download_choice_is_a_command_line_option():
    assert viewer.build_parser().parse_args(['m.bsp']).core_textures == 'ask'
    for choice in ('ask', 'always', 'never'):
        options = viewer.build_parser().parse_args(['m.bsp', '--core-textures', choice])
        assert options.core_textures == choice


# -- looking up and down ------------------------------------------------------
#
# A rising pitch tips the gaze *down*, so look-up must subtract.  These tests
# measure where the camera actually looks rather than the sign of `nav.pitch`,
# which would only restate the code.


def test_the_gaze_rule_agrees_with_the_walk_direction(tmp_path):
    """The plan's instruction: validate the gaze rule against `_world_dir`
    before relying on it.  With no pitch, the two must be the same direction."""
    nav = walking_platform(tmp_path)
    nav.yaw = viewer.yaw_for_angle(0.0)
    assert viewer.gaze(nav) == pytest.approx(nav._world_dir(1.0, 0.0), abs=1e-6)


def test_looking_up_raises_the_gaze(tmp_path):
    nav = walking_platform(tmp_path)
    before = viewer.gaze(nav)
    look_once(nav, '<up>')
    assert viewer.gaze(nav)[1] > before[1]


def test_looking_down_lowers_the_gaze(tmp_path):
    nav = walking_platform(tmp_path)
    before = viewer.gaze(nav)
    look_once(nav, '<down>')
    assert viewer.gaze(nav)[1] < before[1]


def test_looking_does_not_swing_the_heading(tmp_path):
    """Pitch tilts; it must not also turn, which a wrong rotation order does."""
    nav = walking_platform(tmp_path)
    nav.yaw = viewer.yaw_for_angle(90.0)
    before = viewer.gaze(nav)
    look_once(nav, '<up>', 0.2)
    after = viewer.gaze(nav)
    assert np.sign(after[0] + 1e-9) == np.sign(before[0] + 1e-9)
    assert after[2] < 0 and before[2] < 0        # still facing the same way


def test_the_look_keys_tilt_without_walking(tmp_path):
    """Ctrl and an arrow means look, so the plain arrow's walk must not fire."""
    nav = walking_platform(tmp_path)
    start = np.array(nav.character.position, dtype='d')
    for _ in range(10):
        look_once(nav, '<up>')
        nav.update(0.1)
    moved = np.array(nav.character.position, dtype='d') - start
    assert abs(moved[0]) < 1e-6 and abs(moved[2]) < 1e-6


def test_the_pitch_is_bounded_so_the_view_cannot_flip(tmp_path):
    nav = walking_platform(tmp_path)
    for _ in range(200):
        look_once(nav, '<up>')
    assert abs(nav.pitch) < np.pi / 2
    assert viewer.gaze(nav)[1] < 1.0


def test_loading_a_map_never_asks_on_the_console(tmp_path, monkeypatch):
    """The viewer asks in the window, over the map.  A console prompt here
    blocks before the window is even open, so the overlay never gets a chance
    and the user answers a question they cannot see the context for."""
    def refuse(*args, **named):
        raise AssertionError('load_map prompted on the console')

    # A real run has a terminal attached; without this the console path skips
    # itself and the test passes for the wrong reason.
    monkeypatch.setattr(viewer.sys.stdin, 'isatty', lambda: True, raising=False)
    monkeypatch.setattr('builtins.input', refuse)
    options = viewer.build_parser().parse_args(
        [synthetic_map(tmp_path), '--cache-dir', str(tmp_path / 'cache')])
    loaded = viewer.load_map(options)
    assert loaded.missing_textures()            # there *is* something to ask about


def test_a_pack_already_on_disk_is_used_without_asking(tmp_path, monkeypatch):
    """Silently using what is already there is not a question."""
    pack = tmp_path / 'pack'
    (pack / 'textures').mkdir(parents=True)
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack_, cache_dir=None: str(pack))
    options = viewer.build_parser().parse_args([synthetic_map(tmp_path)])
    viewer.load_map(options)
    assert str(pack) in options.content


def test_always_still_fetches_without_a_window(tmp_path, monkeypatch):
    """`--core-textures always` is for automation, which has no overlay."""
    pack = tmp_path / 'pack'
    (pack / 'textures').mkdir(parents=True)
    monkeypatch.setattr(viewer.download, 'pack_root', lambda pack_, cache_dir=None: None)
    monkeypatch.setattr(viewer.download, 'fetch_pack',
                        lambda pack_, cache_dir=None: str(pack))
    options = viewer.build_parser().parse_args(
        [synthetic_map(tmp_path), '--core-textures', 'always'])
    viewer.load_map(options)
    assert str(pack) in options.content


# -- declared movement modes --------------------------------------------------

def test_the_viewer_declares_its_movement_modes():
    """Declared rather than hand-rolled, so a settings screen can enumerate
    them and a game can retune them without touching the viewer."""
    declared = viewer.movement_modes()
    names = [mode.name for mode in declared]
    assert 'walk' in names and 'fly' in names


def test_the_declared_modes_are_scaled_to_map_units():
    """SPEC-BSP38 §3.2: a map is in inches, the scene in metres, so the speeds
    a mode ships with are wrong here by a factor of forty."""
    walk = [m for m in viewer.movement_modes() if m.name == 'walk'][0]
    assert walk.walkSpeed == pytest.approx(viewer.WALK_SPEED_UNITS * 0.0254)
    assert walk.runSpeed == pytest.approx(viewer.RUN_SPEED_UNITS * 0.0254)


def test_a_swim_mode_is_declared_for_when_liquid_volumes_arrive():
    """It is world-imposed, so it is declared but never cycled into."""
    from OpenGLContext.move import modes as movemodes
    swim = [m for m in viewer.movement_modes()
            if isinstance(m, movemodes.SwimMode)]
    assert swim


class TestHowBigTheWindowOpens:
    """A game is played full-screen, so that is what starting it does.

    Two things want it back in a window and neither is the player: a capture
    is a picture of a scene at a stated size, and somebody working on the game
    wants it beside an editor.
    """

    def test_the_game_starts_full_screen(self):
        assert viewer.build_parser().parse_args([]).fullscreen

    def test_a_window_can_be_asked_for(self):
        assert not viewer.build_parser().parse_args(
            ['--no-fullscreen']).fullscreen

    def test_the_definition_carries_the_choice(self):
        assert viewer.context_definition().fullscreen
        assert not viewer.context_definition(fullscreen=False).fullscreen

    def test_a_capture_stays_in_its_window(self):
        """The frame is read back at the size that was asked for."""
        options = viewer.build_parser().parse_args(['--capture', 'shot.png'])
        assert not viewer.wants_fullscreen(options)

    def test_playing_fills_the_screen(self):
        options = viewer.build_parser().parse_args([])
        assert viewer.wants_fullscreen(options)

    def test_asking_for_a_window_is_honoured(self):
        options = viewer.build_parser().parse_args(['--no-fullscreen'])
        assert not viewer.wants_fullscreen(options)


def test_the_modes_reach_the_context_definition():
    definition = viewer.context_definition()
    assert list(definition.movementModes)
    assert [m.name for m in definition.movementModes] == \
        [m.name for m in viewer.movement_modes()]


def test_every_declared_mode_has_bindings_a_settings_window_could_show():
    for mode in viewer.movement_modes():
        assert mode.bindings
        assert all(binding.label for binding in mode.bindings)


# -- asset packs on the command line ------------------------------------------

def test_the_packs_can_be_listed_without_naming_a_map(capsys):
    """A user with nothing to look at needs a way to find out what is on offer
    before they are made to type a map name."""
    with pytest.raises(SystemExit) as exit_info:
        viewer.main(['--list-packs'])
    assert exit_info.value.code == 0
    printed = capsys.readouterr().out
    assert 'openarena' in printed.lower()
    assert 'MB' in printed
    assert 'OpenArena project' in printed


def test_no_map_on_the_command_line_is_a_start_screen_rather_than_an_error(
        monkeypatch):
    """Launching with no arguments has to be a reasonable thing to do.

    It used to be a usage error, which made the start screen unreachable from
    the one place a player would look for it.
    """
    started = []
    monkeypatch.setattr(viewer.TwigContext, 'ContextMainLoop',
                        classmethod(lambda cls, **named: started.append(named)))
    viewer.main([])
    assert started
    assert viewer.TwigContext._target in (None, '')


def test_a_named_map_still_goes_straight_into_it(monkeypatch, tmp_path):
    """The start screen is the *default*, not a step everyone has to walk past."""
    started = []
    monkeypatch.setattr(viewer.TwigContext, 'ContextMainLoop',
                        classmethod(lambda cls, **named: started.append(named)))
    viewer.main(['some-map.bsp'])
    assert viewer.TwigContext._target == 'some-map.bsp'


def test_naming_a_map_inside_a_pack_fetches_the_pack(tmp_path, monkeypatch):
    """Typing ``openarena:oa_dm1`` *is* the consent to download it: the pack has
    to be on disk before there is a window to ask in."""
    root = tmp_path / 'pack'
    (root / 'maps').mkdir(parents=True)
    (root / 'maps' / 'oa_dm1.bsp').write_bytes(b'IBSP')
    fetched = []

    def _fetch(pack, cache_dir=None):
        fetched.append(pack.key)
        return str(root)

    monkeypatch.setattr(viewer.download, 'fetch_pack', _fetch)
    options = viewer.build_parser().parse_args(['openarena:oa_dm1'])
    path = viewer.resolve_map_target(options)
    assert fetched == ['openarena-maps']
    assert path.endswith('oa_dm1.bsp')


def test_the_pack_directory_becomes_a_content_root(tmp_path, monkeypatch):
    """The map's textures live in the pack beside it, not next to the .bsp."""
    root = tmp_path / 'pack'
    (root / 'maps').mkdir(parents=True)
    (root / 'maps' / 'oa_dm1.bsp').write_bytes(b'IBSP')
    monkeypatch.setattr(viewer.download, 'fetch_pack',
                        lambda pack, cache_dir=None: str(root))
    options = viewer.build_parser().parse_args(['openarena:oa_dm1'])
    viewer.resolve_map_target(options)
    assert str(root) in options.content


def test_a_map_the_pack_does_not_hold_says_what_it_does_hold(tmp_path, monkeypatch):
    root = tmp_path / 'pack'
    (root / 'maps').mkdir(parents=True)
    (root / 'maps' / 'oa_dm1.bsp').write_bytes(b'IBSP')
    monkeypatch.setattr(viewer.download, 'fetch_pack',
                        lambda pack, cache_dir=None: str(root))
    options = viewer.build_parser().parse_args(['openarena:nosuch'])
    with pytest.raises(viewer.download.NoMapFound) as error:
        viewer.resolve_map_target(options)
    assert 'oa_dm1' in str(error.value)


def test_an_ordinary_path_is_resolved_as_before(tmp_path):
    path = synthetic_map(tmp_path)
    options = viewer.build_parser().parse_args([path])
    assert viewer.resolve_map_target(options) == path


def test_a_companion_pack_already_on_disk_is_used_as_a_content_root(tmp_path, monkeypatch):
    """The maps carry no art; once the texture pack has been fetched the maps
    must find it without the user saying so again."""
    maps_root = tmp_path / 'openarena-maps'
    (maps_root / 'maps').mkdir(parents=True)
    (maps_root / 'maps' / 'oa_dm1.bsp').write_bytes(b'IBSP')
    textures_root = tmp_path / 'openarena-textures'
    (textures_root / 'textures').mkdir(parents=True)
    monkeypatch.setattr(viewer.download, 'fetch_pack',
                        lambda pack, cache_dir=None: str(maps_root))
    monkeypatch.setattr(
        viewer.download, 'pack_root',
        lambda pack, cache_dir=None: (str(textures_root)
                                      if pack.key == 'openarena-textures' else None))
    options = viewer.build_parser().parse_args(['openarena:oa_dm1'])
    viewer.resolve_map_target(options)
    assert str(textures_root) in options.content


def test_a_map_from_a_pack_offers_that_familys_textures_not_quake3s(tmp_path, monkeypatch):
    """Offering the Quake 3 replacement pack for an OpenArena map would
    download 187 MB that cannot name a single one of its textures."""
    maps_root = tmp_path / 'openarena-maps'
    (maps_root / 'maps').mkdir(parents=True)
    (maps_root / 'maps' / 'oa_dm1.bsp').write_bytes(b'IBSP')
    monkeypatch.setattr(viewer.download, 'fetch_pack',
                        lambda pack, cache_dir=None: str(maps_root))
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack, cache_dir=None: None)
    options = viewer.build_parser().parse_args(['openarena:oa_dm1'])
    viewer.resolve_map_target(options)
    assert options.texture_packs == ['openarena-textures', 'openarena-data']


def test_an_ordinary_map_offers_the_quake3_replacement_pack(tmp_path):
    options = viewer.build_parser().parse_args([synthetic_map(tmp_path)])
    viewer.resolve_map_target(options)
    assert options.texture_packs == ['quake3-core']


def test_a_pack_can_be_fetched_deliberately_from_the_command_line(monkeypatch, capsys):
    """Consent for a 449 MB download is the user typing its name."""
    fetched = []
    monkeypatch.setattr(viewer.download, 'fetch_pack',
                        lambda pack, cache_dir=None: fetched.append(pack.key) or '/x')
    with pytest.raises(SystemExit) as exit_info:
        viewer.main(['--fetch', 'openarena-textures'])
    assert exit_info.value.code == 0
    assert fetched == ['openarena-textures']
    assert '/x' in capsys.readouterr().out


def test_fetching_an_unknown_pack_says_so(capsys):
    with pytest.raises(SystemExit) as exit_info:
        viewer.main(['--fetch', 'nonsense'])
    assert exit_info.value.code != 0


# -- which pack the missing-texture prompt offers ------------------------------

def test_nothing_is_offered_when_no_texture_is_missing(tmp_path):
    options = viewer.build_parser().parse_args([synthetic_map(tmp_path)])
    assert viewer.texture_pack_offer(_Loaded([]), options) == []


def test_nothing_is_offered_when_the_user_said_never(tmp_path):
    options = viewer.build_parser().parse_args([synthetic_map(tmp_path), '--core-textures', 'never'])
    assert viewer.texture_pack_offer(_Loaded(['a']), options) == []


def test_the_pack_named_by_the_map_is_the_one_offered(tmp_path, monkeypatch):
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack, cache_dir=None: None)
    options = viewer.build_parser().parse_args([synthetic_map(tmp_path)])
    options.texture_packs = ['openarena-textures', 'openarena-data']
    offer = viewer.texture_pack_offer(_Loaded(['a']), options)
    assert [pack.key for pack in offer] == ['openarena-textures', 'openarena-data']


def test_a_pack_already_on_disk_is_not_offered_again(tmp_path, monkeypatch):
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack, cache_dir=None: '/somewhere')
    options = viewer.build_parser().parse_args([synthetic_map(tmp_path)])
    assert viewer.texture_pack_offer(_Loaded(['a']), options) == []


def test_the_prompt_says_the_size_and_the_licence_before_downloading(tmp_path, monkeypatch):
    """A user cannot consent to a download whose size and terms they are not told."""
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack, cache_dir=None: None)
    options = viewer.build_parser().parse_args([synthetic_map(tmp_path)])
    prompt = viewer.build_texture_prompt(_Loaded(['textures/x/a']), options,
                                         on_answer=None)
    text = _prompt_text(prompt)
    assert '187 MB' in text
    assert 'ioquake3' in text
    assert 'textures/x/a' in text


def test_a_pack_wrapped_in_version_directories_still_resolves(tmp_path, monkeypatch):
    """A Debian source tarball unpacks under its own version directory, so the
    pack's top is not the level texture names are relative to."""
    inner = tmp_path / 'openarena-maps-0.8.5split.orig' / 'pak1-maps'
    (inner / 'maps').mkdir(parents=True)
    (inner / 'maps' / 'oa_dm1.bsp').write_bytes(b'IBSP')
    monkeypatch.setattr(viewer.download, 'fetch_pack',
                        lambda pack, cache_dir=None: str(tmp_path))
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack, cache_dir=None: None)
    options = viewer.build_parser().parse_args(['openarena:oa_dm1'])
    viewer.resolve_map_target(options)
    assert options.content == [str(inner)]


def test_a_texture_pack_used_without_asking_resolves_to_its_content_level(tmp_path, monkeypatch):
    pack = tmp_path / 'pack'
    inner = pack / 'openarena-textures-0.8.5split.orig' / 'pak2-textures'
    (inner / 'textures').mkdir(parents=True)
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack_, cache_dir=None: str(pack))
    options = viewer.build_parser().parse_args([synthetic_map(tmp_path), '--core-textures', 'always'])
    viewer.load_map(options)
    assert str(inner) in options.content


def test_the_prompt_asks_about_every_missing_pack_at_once(tmp_path, monkeypatch):
    """A release splits what one map needs across packs; a question that has to
    be answered again next launch to get the rest is a worse question."""
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack, cache_dir=None: None)
    options = viewer.build_parser().parse_args([synthetic_map(tmp_path)])
    options.texture_packs = ['openarena-textures', 'openarena-data']
    prompt = viewer.build_texture_prompt(_Loaded(['textures/x/a']), options,
                                         on_answer=None)
    text = _prompt_text(prompt)
    assert 'OpenArena textures' in text
    assert 'shader scripts' in text
    assert '540 MB' in text          # 449 + 91, so the total is what is stated


def _prompt_text(prompt):
    """Everything the prompt puts in front of the user, as one string."""
    from OpenGLContext.ui.widgets import Label
    return '\n'.join(widget.text for widget in prompt.walk()
                     if isinstance(widget, Label))


def test_the_download_prompt_is_modal_with_download_as_its_default(tmp_path, monkeypatch):
    """Nothing reaches the world while an unanswered question is up, and Enter
    takes the affirmative rather than needing the mouse."""
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack, cache_dir=None: None)
    options = viewer.build_parser().parse_args([synthetic_map(tmp_path)])
    answers = []
    prompt = viewer.build_texture_prompt(_Loaded(['textures/x/a']), options,
                                         on_answer=answers.append)
    assert prompt.modal
    prompt.layout((800, 600), _metrics())
    assert prompt.primary() is prompt.find('yes')
    prompt.key('<return>', (0, 0, 0))
    assert answers == [True]


def test_declining_the_download_answers_no(tmp_path, monkeypatch):
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack, cache_dir=None: None)
    options = viewer.build_parser().parse_args([synthetic_map(tmp_path)])
    answers = []
    prompt = viewer.build_texture_prompt(_Loaded(['textures/x/a']), options,
                                         on_answer=answers.append)
    prompt.layout((800, 600), _metrics())
    prompt.key('<escape>', (0, 0, 0))
    assert answers == [False]


def _metrics():
    from OpenGLContext.ui.metrics import FontMetrics
    return FontMetrics(8, 16, 2)


# -- the declared modes drive the walking navigator ---------------------------

def test_a_mouse_look_mode_is_offered():
    """Turning with `q`/`e` is unusable for anything but a slow look around;
    running an arena needs the mouse to steer."""
    names = [mode.name for mode in viewer.movement_modes()]
    assert 'fps' in names


def test_the_mouse_look_mode_walks_like_the_walk_mode():
    """It is walking with a different steering, not a different avatar."""
    modes = {mode.name: mode for mode in viewer.movement_modes()}
    assert modes['fps'].walkSpeed == modes['walk'].walkSpeed
    assert modes['fps'].runSpeed == modes['walk'].runSpeed


def test_the_mouse_look_mode_is_the_one_the_viewer_starts_in():
    """An arena is played with the mouse; walking with `q`/`e` is the fallback.

    The navigation manager takes the first selectable declared mode, so being
    the default is a matter of being declared first.
    """
    from OpenGLContext.move.navigation import NavigationManager
    definition = viewer.context_definition()
    NavigationManager(definition, _platform_stub())
    assert str(definition.movementMode.name) == 'fps'


def test_the_viewer_still_offers_the_keyboard_only_walk():
    """Being second is not being dropped: not every player wants mouse-look."""
    names = [mode.name for mode in viewer.movement_modes()]
    assert 'walk' in names


def _platform_stub():
    class _P:
        submerged = False

        def set_move(self, forward=0.0, strafe=0.0, mode='walk', speed=None):
            pass

        def set_fly_move(self, forward=0.0, strafe=0.0, up=0.0, speed=None):
            pass

        def jump(self):
            pass

        def turn(self, delta):
            pass

        def look(self, delta):
            pass
    return _P()


def test_the_mouse_look_mode_wants_the_pointer():
    modes = {mode.name: mode for mode in viewer.movement_modes()}
    assert modes['fps'].capturePointer
    assert not modes['walk'].capturePointer


def test_every_mode_can_tilt_the_view_with_ctrl_and_the_arrows():
    """The keys the viewer has always used for looking up and down."""
    for mode in viewer.movement_modes():
        assert mode.keys_for('lookup') == ('<up>',)
        binding = [b for b in mode.bindings if b.command == 'lookup'][0]
        assert binding.modifier == 'ctrl'


def test_entering_the_fly_mode_puts_the_character_into_noclip():
    """Flying is a property of the character controller, so the mode change has
    to reach it; a mode that only sets movement flies into the floor."""
    nav = NavStub()
    viewer.apply_mode(nav, viewer.movement_modes()[0])       # walk
    assert not nav.flying
    fly = [m for m in viewer.movement_modes() if m.name == 'fly'][0]
    viewer.apply_mode(nav, fly)
    assert nav.flying


def test_applying_no_mode_leaves_the_character_alone():
    nav = NavStub()
    nav.flying = True
    viewer.apply_mode(nav, None)
    assert nav.flying


def test_applying_a_mode_without_a_navigator_is_harmless():
    viewer.apply_mode(None, viewer.movement_modes()[0])


# -- events through the sampler into the character ----------------------------


def test_a_held_key_walks_the_character_through_the_declared_modes(tmp_path):
    """The whole input path the window uses: a key event reaches the sampler,
    the mode in force reads it, and the character controller moves."""
    nav = walking_platform(tmp_path)
    context = HeadlessContext(nav)
    start = np.array(nav.character.position, dtype='d')
    context._recordInput(KeyEvent('w', 1))
    for _ in range(10):
        context.updateNavigation(0.05)
        nav.update(0.05)
    moved = np.array(nav.character.position, dtype='d') - start
    assert np.linalg.norm(moved[[0, 2]]) > 0.1


def test_releasing_the_key_stops_the_character(tmp_path):
    nav = walking_platform(tmp_path)
    context = HeadlessContext(nav)
    context._recordInput(KeyEvent('w', 1))
    context.updateNavigation(0.05)
    context._recordInput(KeyEvent('w', 0))
    context.updateNavigation(0.05)
    nav.update(0.05)
    here = np.array(nav.character.position, dtype='d')
    for _ in range(10):
        context.updateNavigation(0.05)
        nav.update(0.05)
    after = np.array(nav.character.position, dtype='d')
    assert np.linalg.norm((after - here)[[0, 2]]) < 1e-6


def test_walking_and_jumping_happen_in_the_same_frame(tmp_path):
    """The reason the sampler exists: holding forward and tapping jump must do
    both, which an event-driven controller loses."""
    nav = walking_platform(tmp_path)
    nav.character.grounded = True
    context = HeadlessContext(nav)
    context._recordInput(KeyEvent('w', 1))
    context._recordInput(KeyEvent(' ', 1))
    start = np.array(nav.character.position, dtype='d')
    context.updateNavigation(0.05)
    assert nav.character.vy > 0                  # jumped
    nav.update(0.05)
    moved = np.array(nav.character.position, dtype='d') - start
    assert np.linalg.norm(moved[[0, 2]]) > 0     # and moved, in the same frame


# -- swimming -----------------------------------------------------------------

def test_the_physics_world_is_found_through_the_character(tmp_path):
    """The one query the bots, the shooting and the overlay all go through.

    A view platform does not hold the world — its *character* does — so asking
    the platform for one silently answered None.  Nothing raised: the bots
    simply never thought, no shot was ever traced, and the developer overlay
    quietly dropped its Physics section.  A wrong answer that everything
    downstream treats as "not ready yet" is the kind that hides for a long
    time, which is why this is tested rather than eyeballed.
    """
    nav = walking_platform(tmp_path)
    context = HeadlessContext(nav)
    assert context.physicsWorld() is nav.character.world


def test_no_physics_world_before_walking_begins(tmp_path):
    context = HeadlessContext(walking_platform(tmp_path))
    context._nav = None
    assert context.physicsWorld() is None


def _mode(name):
    return [m for m in viewer.movement_modes() if m.name == name][0]


def test_swimming_puts_the_character_in_the_water_rather_than_in_the_air():
    """Swimming is not flying, and the difference is a wall you can leave by.

    A swim implemented as noclip lets a player out of a pool through its side;
    a swimmer collides with the world and is held up by buoyancy instead.
    """
    nav = NavStub()
    viewer.apply_mode(nav, _mode('swim'))
    assert nav.swimming
    assert not nav.flying


def test_the_swim_mode_carries_its_buoyancy_to_the_character():
    nav = NavStub()
    viewer.apply_mode(nav, _mode('swim'))
    assert nav.buoyancy == pytest.approx(_mode('swim').buoyancy)


def test_leaving_the_water_takes_the_character_out_of_swimming():
    nav = NavStub()
    viewer.apply_mode(nav, _mode('swim'))
    viewer.apply_mode(nav, _mode('walk'))
    assert not nav.swimming


def test_being_in_a_liquid_volume_puts_the_avatar_in_the_swim_mode(tmp_path):
    """The world imposes the mode: nothing is selected, entering water is what
    decides it (`SPEC-BSP38 §9.4`)."""
    from twig_bb import liquids
    nav = walking_platform(tmp_path)
    context = HeadlessContext(nav)
    volumes = liquids.LiquidVolumes([
        liquids.LiquidVolume(mins=np.array([-100.0, -100.0, -100.0]),
                             maxs=np.array([100.0, 100.0, 100.0]))])
    viewer.update_submerged(nav, volumes)
    context.updateNavigation(0.05)
    assert context.contextDefinition.movementMode.name == 'swim'


def test_leaving_the_water_gives_the_mode_back(tmp_path):
    from twig_bb import liquids
    nav = walking_platform(tmp_path)
    context = HeadlessContext(nav)
    empty = liquids.LiquidVolumes([])
    viewer.update_submerged(nav, empty)
    context.updateNavigation(0.05)
    assert context.contextDefinition.movementMode.name != 'swim'


def test_a_map_with_no_liquid_never_reports_being_submerged(tmp_path):
    from twig_bb import liquids
    nav = walking_platform(tmp_path)
    viewer.update_submerged(nav, liquids.LiquidVolumes([]))
    assert not nav.submerged


def test_updating_without_volumes_is_harmless(tmp_path):
    viewer.update_submerged(walking_platform(tmp_path), None)
    viewer.update_submerged(None, None)


# -- where the water starts and where it lets go ------------------------------

class _Body:
    """A platform that knows where its eye and its feet are."""

    def __init__(self, eye, feet, submerged=False):
        self._eye, self._feet = eye, feet
        self.submerged = submerged

    def camera_position(self):
        return self._eye

    def feet_position(self):
        return self._feet


def _pool_volumes(surface=0.0, floor=-2.0):
    """One pool, wide enough that only the height decides these tests."""
    from twig_bb import liquids
    return liquids.LiquidVolumes([liquids.LiquidVolume(
        mins=np.array([-10.0, floor, -10.0]),
        maxs=np.array([10.0, surface, 10.0]))])


def test_swimming_starts_when_the_water_closes_over_the_eye():
    body = _Body(eye=(0.0, -0.1, 0.0), feet=(0.0, -1.3, 0.0))
    viewer.update_submerged(body, _pool_volumes())
    assert body.submerged


def test_wading_with_your_head_out_is_not_swimming():
    """Feet in the shallows and the eye in the air is somebody walking."""
    body = _Body(eye=(0.0, 0.9, 0.0), feet=(0.0, -0.3, 0.0))
    viewer.update_submerged(body, _pool_volumes())
    assert not body.submerged


def test_a_swimmer_whose_eye_breaks_the_surface_is_still_in_the_water():
    """The eye reaches the surface a body's height before the feet do.

    Ending the swim there pins the eye to the surface: the body sinks back the
    moment it stops swimming, so the feet can never rise past a head's depth
    and every pool with a rim above the water is a trap.
    """
    body = _Body(eye=(0.0, 0.4, 0.0), feet=(0.0, -0.8, 0.0), submerged=True)
    viewer.update_submerged(body, _pool_volumes())
    assert body.submerged


def test_a_swimmer_whose_feet_leave_the_water_is_out_of_it():
    body = _Body(eye=(0.0, 1.6, 0.0), feet=(0.0, 0.4, 0.0), submerged=True)
    viewer.update_submerged(body, _pool_volumes())
    assert not body.submerged


def test_a_platform_with_no_body_is_read_by_its_eye_alone():
    """A plain camera has no feet to ask about, and still has to work."""
    class _Camera:
        submerged = True

        def camera_position(self):
            return (0.0, 5.0, 0.0)

    camera = _Camera()
    viewer.update_submerged(camera, _pool_volumes())
    assert not camera.submerged


# -- getting out of a pool ----------------------------------------------------

#: The pit, as a map builds one: a deck with a square hole in it, the water
#: stopping a little below the deck, and the floor a swimmer's height further
#: down.  These are the proportions of the pool at 26,-7,-13 in `oa_spirit3`.
POOL_HALF = 1.5
POOL_FLOOR = -2.0
POOL_SURFACE = -0.2


def _quad(points, corners):
    """Add one rectangle's two triangles to ``points``, and index them."""
    first = len(points)
    points.extend(corners)
    return [(first, first + 1, first + 2), (first, first + 2, first + 3)]


def _pool_world():
    """A deck at y=0 with a pit in the middle of it, as one static trimesh."""
    from omi_physics import model
    from omi_physics.world import PhysicsWorld

    half, floor, edge = POOL_HALF, POOL_FLOOR, 8.0
    points, triangles = [], []
    spans = [(-edge, -half), (half, edge)]
    for low, high in spans:                     # the deck, front and back
        triangles += _quad(points, [(-edge, 0.0, low), (edge, 0.0, low),
                                    (edge, 0.0, high), (-edge, 0.0, high)])
    for low, high in spans:                     # and to the left and right
        triangles += _quad(points, [(low, 0.0, -half), (high, 0.0, -half),
                                    (high, 0.0, half), (low, 0.0, half)])
    triangles += _quad(points, [(-half, floor, -half), (half, floor, -half),
                                (half, floor, half), (-half, floor, half)])
    for sign in (-1.0, 1.0):                    # the pit's four walls
        triangles += _quad(points, [(-half, floor, sign * half),
                                    (half, floor, sign * half),
                                    (half, 0.0, sign * half),
                                    (-half, 0.0, sign * half)])
        triangles += _quad(points, [(sign * half, floor, -half),
                                    (sign * half, floor, half),
                                    (sign * half, 0.0, half),
                                    (sign * half, 0.0, -half)])
    for sign in (-1.0, 1.0):                    # a wall round the room, so a
        triangles += _quad(points, [(-edge, 0.0, sign * edge),   # player who
                                    (edge, 0.0, sign * edge),    # gets out and
                                    (edge, 4.0, sign * edge),    # keeps walking
                                    (-edge, 4.0, sign * edge)])  # stays in it
        triangles += _quad(points, [(sign * edge, 0.0, -edge),
                                    (sign * edge, 0.0, edge),
                                    (sign * edge, 4.0, edge),
                                    (sign * edge, 4.0, -edge)])
    world = PhysicsWorld(gravity=model.Gravity(gravity=9.81, direction=(0, -1, 0)))
    shape = world.add_shape(model.Shape.trimesh(np.array(points, dtype='d'),
                                                np.array(triangles, dtype='i')))
    world.add_body(model.Motion(type=model.STATIC),
                   collider=model.Collider(shape=shape), position=(0, 0, 0))
    return world


class _Holding(NullInput):
    """The keys a player is leaning on, for as long as the test runs."""

    def __init__(self, *keys):
        self.keys = set(keys)

    def held(self, *names):
        return any(name in self.keys for name in names)


def _swim_out(seconds=12.0, keys=('w', ' ')):
    """Drop a player in the pool, hold ``keys``, and say where they end up.

    The whole path a player's own keys take: the modes decide which of them
    applies from what the liquid volumes say, and the character controller
    moves the capsule against the real pit.
    """
    from OpenGLContext.move.physicsplatform import PhysicsViewPlatform
    from twig_bb import liquids

    volumes = liquids.LiquidVolumes([liquids.LiquidVolume(
        mins=np.array([-POOL_HALF, POOL_FLOOR, -POOL_HALF]),
        maxs=np.array([POOL_HALF, POOL_SURFACE, POOL_HALF]))])
    platform = PhysicsViewPlatform(_pool_world(), viewer.character_capabilities(),
                                   position=(0.0, POOL_FLOOR + 1.0, 0.0))
    platform.bind((0.0, POOL_FLOOR + 1.0, 0.0))
    platform.yaw = np.pi                        # forward is +z
    modes = {mode.name: mode for mode in viewer.movement_modes()}
    inputs, dt, current = _Holding(*keys), 1.0 / 60.0, None
    for _frame in range(int(seconds / dt)):
        viewer.update_submerged(platform, volumes)
        wanted = modes['swim'] if modes['swim'].enter_when(platform) else modes['fps']
        if wanted is not current:
            viewer.apply_mode(platform, wanted)
            current = wanted
        current.update(dt, inputs, platform)
        platform.update(dt)
    return platform


def test_a_swimmer_starts_out_swimming():
    """The guard on the test below: it has to begin in the water."""
    platform = _swim_out(seconds=1.0 / 60.0)
    assert platform.submerged


def test_a_player_can_swim_out_of_a_pool_sunk_below_its_deck():
    """Forward and the rise key, which is all a player has to get out with.

    A pool whose rim stands above the water is the ordinary shape of one, and
    a player who can fall in but not climb out is stuck for the rest of the
    match.
    """
    platform = _swim_out()
    feet = platform.feet_position()
    assert feet[1] == pytest.approx(0.0, abs=0.1), 'not standing on the deck'
    assert feet[2] > POOL_HALF, 'still over the pit'
    assert platform.character.grounded


def test_a_companion_key_naming_no_registered_pack_is_ignored(tmp_path, monkeypatch):
    """A registry edit that leaves a dangling key must not break a load."""
    maps_root = tmp_path / 'pack'
    (maps_root / 'maps').mkdir(parents=True)
    (maps_root / 'maps' / 'oa_dm1.bsp').write_bytes(b'IBSP')
    import dataclasses
    pack = dataclasses.replace(viewer.download.pack_for_key('openarena-maps'),
                               companions=('nonsense',))
    monkeypatch.setattr(viewer.download, 'parse_pack_target',
                        lambda target: (pack, target.split(':')[1]))
    monkeypatch.setattr(viewer.download, 'fetch_pack',
                        lambda p, cache_dir=None: str(maps_root))
    options = viewer.build_parser().parse_args(['openarena:oa_dm1'])
    assert viewer.resolve_map_target(options).endswith('oa_dm1.bsp')


def test_a_texture_pack_key_naming_no_registered_pack_is_ignored(tmp_path):
    options = viewer.build_parser().parse_args([synthetic_map(tmp_path)])
    options.texture_packs = ['nonsense']
    assert viewer.available_textures(_Loaded(['a']), options) == []
    assert viewer.texture_pack_offer(_Loaded(['a']), options) == []


# -- the keys that open a screen ---------------------------------------------

from OpenGLContext.contextdefinition import ContextDefinition  # noqa: E402
from OpenGLContext.events import eventhandlermixin, keyboardevents  # noqa: E402
from OpenGLContext.move.navigation import NavigationManager  # noqa: E402


def test_function_keys_are_bound_where_they_are_actually_delivered():
    """GLFW reports a function key as a `keyboard` transition and never as a
    `keypress`: it produces no character.  A keypress binding for one is
    accepted and then silently never fires."""
    recorder = BindingRecorder()
    viewer.TwigContext.bindScreenKeys(recorder)
    for kind, name, state in recorder.bindings:
        if name and name.startswith('<F'):
            assert kind == 'keyboard', '%s bound on %r' % (name, kind)
            assert state == 1, '%s bound without a key-down state' % (name,)


def test_the_settings_and_binding_screens_have_keys():
    recorder = BindingRecorder()
    viewer.TwigContext.bindScreenKeys(recorder)
    names = [name for _kind, name, _state in recorder.bindings]
    assert '<F10>' in names
    assert '<F6>' in names


class _KeyStub(eventhandlermixin.EventHandlerMixin):
    """The viewer's key bindings over a real event registry, with no window."""

    EventManagerClasses = [('keyboard', keyboardevents.KeyboardEventManager)]
    TimeManagerClass = None
    drawing = False

    def __init__(self):
        self.initializeEventManagers()
        self.opened = []
        viewer.TwigContext.bindScreenKeys(self)

    def _settings(self, event):
        self.opened.append('settings')

    def _bindings(self, event):
        self.opened.append('bindings')

    def press(self, name):
        event = keyboardevents.KeyboardEvent()
        event.name, event.state, event.modifiers = name, 1, (0, 0, 0)
        self.ProcessEvent(event)


def test_pressing_the_screen_keys_actually_reaches_their_handlers():
    """Through the real registry and a real event, because the binding this
    replaced was accepted by the registry and then never delivered."""
    stub = _KeyStub()
    for name in ('<F10>', '<F6>'):
        stub.press(name)
    assert stub.opened == ['settings', 'bindings']


def test_a_key_nothing_binds_reaches_nothing():
    stub = _KeyStub()
    stub.press('<F11>')
    assert stub.opened == []


# -- the mode name, now on the developer overlay ------------------------------
# It used to be drawn over the game in the top-left corner.  A player does not
# want to be told the name of the camera mode; a developer wants that and a
# dozen things it never showed, so it moved to the debug overlay (§2).

def _mode_row(definition):
    """What the developer overlay's Player section says the mode is."""
    from twig_bb import debug as twigdebug

    class Viewer:
        contextDefinition = definition
        _walking = True
        _nav = None
        loaded = None
        player = None

        def getViewPlatform(self):
            return None

    return dict(twigdebug.player_provider(Viewer())()).get('mode')


def test_the_overlay_names_the_mode_in_force():
    """Nothing else on screen says which way of moving is live."""
    definition = ContextDefinition(movementModes=viewer.movement_modes())
    navigation = NavigationManager(definition, _ModePlatform())
    navigation.select('fps')
    assert _mode_row(definition) == 'fps'
    navigation.select('walk')
    assert _mode_row(definition) == 'walk'


def test_no_mode_in_force_is_not_an_empty_row():
    assert _mode_row(ContextDefinition()) is None


def test_a_world_imposed_mode_shows_too():
    """Swimming is imposed rather than chosen, and that is exactly when being
    told which mode you are in matters."""
    definition = ContextDefinition(movementModes=viewer.movement_modes())
    platform = _ModePlatform()
    navigation = NavigationManager(definition, platform)
    platform.submerged = True
    navigation.update(0.016, NullInput())
    assert _mode_row(definition) == 'swim'


class _ModePlatform:
    submerged = False

    def set_move(self, **named):
        pass

    def set_fly_move(self, **named):
        pass

    def turn(self, delta):
        pass

    def look(self, delta):
        pass

    def jump(self):
        pass


# -- the jump diagnostic ------------------------------------------------------

class _WatchedCharacter:
    grounded = True
    crouching = False
    flying = False
    vy = 0.0

    def __init__(self):
        self.jumps = 0

    def jump(self):
        self.jumps += 1
        return self.grounded


class _WatchedNav:
    def __init__(self):
        self.character = _WatchedCharacter()

    def jump(self):
        return self.character.jump()


def test_the_jump_report_names_the_reason_a_press_did_nothing():
    """`doesn't jump' is unanswerable without knowing what the capsule thought."""
    nav = _WatchedNav()
    nav.character.grounded = False
    lines = []
    viewer.watch_jumps(nav, report=lines.append)
    nav.jump()
    assert lines and 'refused' in lines[0]
    assert 'grounded=False' in lines[0]


def test_it_says_so_when_the_jump_did_fire():
    nav = _WatchedNav()
    lines = []
    viewer.watch_jumps(nav, report=lines.append)
    nav.jump()
    assert lines and 'jumped' in lines[0]


def test_the_jump_still_happens_while_it_is_being_watched():
    nav = _WatchedNav()
    viewer.watch_jumps(nav, report=lambda line: None)
    assert nav.jump()
    assert nav.character.jumps == 1


def test_watching_twice_does_not_stack_two_reports():
    nav = _WatchedNav()
    lines = []
    viewer.watch_jumps(nav, report=lines.append)
    viewer.watch_jumps(nav, report=lines.append)
    nav.jump()
    assert len(lines) == 1


# -- the HUD ------------------------------------------------------------------

def test_the_hud_is_on_by_default():
    assert viewer.build_parser().parse_args(['m.bsp']).hud is None


def test_a_capture_leaves_the_hud_out_unless_it_is_asked_for():
    """A reference image is of the map, not of a health bar over one."""
    def visible(argv):
        options = viewer.build_parser().parse_args(argv)
        wanted = options.hud
        return (options.capture is None if wanted is None else bool(wanted))

    assert visible(['m.bsp']) is True
    assert visible(['m.bsp', '--capture', 'out.png']) is False
    assert visible(['m.bsp', '--capture', 'out.png', '--hud']) is True
    assert visible(['m.bsp', '--no-hud']) is False
