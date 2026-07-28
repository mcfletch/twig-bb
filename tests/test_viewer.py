"""The viewer's command line, spawn placement and navigation rules.

The window itself is exercised by the GL test at the end; everything above it
is arranged so it can be checked without one.
"""

from __future__ import annotations

import os
import subprocess
import sys

import numpy as np
import pytest

import bspbuilder
from OpenGLContext.move.viewplatformmixin import ViewPlatformMixin
from twitchoglc import maploader, viewer

VENV_PYTHON = sys.executable


def _map(tmp_path, lumps=None, name='ctf-test.bsp'):
    maps = tmp_path / 'maps'
    maps.mkdir(parents=True, exist_ok=True)
    path = maps / name
    path.write_bytes(bspbuilder.build(38, lumps or bspbuilder.v38_quad(size=512.0)))
    return str(path)


# -- rendering environment ----------------------------------------------------

def test_the_viewer_asks_for_the_core_profile_and_the_pbr_pass():
    """The plan requires the core profile and the PBR render pass."""
    assert os.environ['OPENGLCONTEXT_PROFILE'] == 'core'
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
    lumps = bspbuilder.v38_quad(size=512.0)
    lumps['entities'] = bspbuilder.entity_text([
        {'classname': 'worldspawn'},
        {'classname': 'info_player_deathmatch', 'origin': '128 256 64'}])
    loaded = maploader.load(_map(tmp_path, lumps))
    eye, _yaw = viewer.choose_spawn(loaded)
    assert eye[0] == pytest.approx(128 * 0.0254)
    assert eye[1] > 64 * 0.0254         # lifted to eye height above the origin


def test_a_map_with_no_spawn_still_places_the_avatar_inside_it(tmp_path):
    loaded = maploader.load(_map(tmp_path))
    eye, yaw = viewer.choose_spawn(loaded)
    low, high = loaded.world.bounds
    assert (eye[0] >= low[0]) and (eye[0] <= high[0])
    assert yaw == 0.0


def test_the_spawn_index_selects_among_several(tmp_path):
    lumps = bspbuilder.v38_quad(size=512.0)
    lumps['entities'] = bspbuilder.entity_text([
        {'classname': 'info_player_deathmatch', 'origin': '0 0 0'},
        {'classname': 'info_player_deathmatch', 'origin': '256 0 0'}])
    loaded = maploader.load(_map(tmp_path, lumps))
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
    loaded = maploader.load(_map(tmp_path))
    world = viewer.collision_world(loaded)
    assert world is not None
    assert world.body_count == 1
    assert int(world.motion_type[0]) != 2        # not kinematic; a static body


def test_a_map_with_nothing_solid_has_no_collision_world(tmp_path):
    lumps = bspbuilder.v38_quad(flags=0)
    loaded = maploader.load(_map(tmp_path, lumps))
    for batch in loaded.world.batches:
        batch.style = batch.style.replace(solid=False)
    assert viewer.collision_world(loaded) is None


def test_the_jump_pad_impulse_reaches_the_character(tmp_path):
    """The end-to-end rule: a pad sets the capsule's motion outright, which is
    what `apply_impulse` does (SPEC-TRIGGER-PUSH §2.4)."""
    from OpenGLContext.move.physicsplatform import PhysicsViewPlatform
    loaded = maploader.load(_map(tmp_path))
    world = viewer.collision_world(loaded)
    nav = PhysicsViewPlatform(world, viewer.character_capabilities(),
                              position=(0, 1, 0))
    nav.character.vy = -5.0
    nav.apply_impulse(np.array([0.0, 7.0, 0.0]))
    assert nav.character.vy == pytest.approx(7.0)    # replaced, not added
    assert not nav.character.grounded


# -- the window ---------------------------------------------------------------

@pytest.mark.gl
@pytest.mark.slow
def test_the_viewer_renders_a_map_and_captures_it(tmp_path, arena_map):
    """The whole path: load, build a PBR scene, render on the core profile."""
    out = tmp_path / 'shot.png'
    result = subprocess.run(
        [VENV_PYTHON, '-m', 'twitchoglc.viewer', arena_map,
         '--capture', str(out), '--frames', '6', '--capture-delay', '0.2',
         '--no-physics'],
        capture_output=True, text=True, timeout=300,
        env=dict(os.environ, OPENGLCONTEXT_PROFILE='core',
                 OPENGLCONTEXT_BACKEND='glfw'))
    assert out.exists(), 'no capture written:\n%s\n%s' % (result.stdout, result.stderr)
    from PIL import Image
    pixels = np.asarray(Image.open(str(out)))
    assert pixels.any(), 'the captured frame is entirely black'


@pytest.mark.gl
@pytest.mark.slow
def test_the_viewer_walks_a_map_under_physics(tmp_path, arena_map):
    """Walk mode must survive a real window, not only the unit tests."""
    out = tmp_path / 'walk.png'
    result = subprocess.run(
        [VENV_PYTHON, '-m', 'twitchoglc.viewer', arena_map,
         '--capture', str(out), '--frames', '10', '--capture-delay', '0.5',
         '--physics'],
        capture_output=True, text=True, timeout=300,
        env=dict(os.environ, OPENGLCONTEXT_PROFILE='core',
                 OPENGLCONTEXT_BACKEND='glfw'))
    assert out.exists(), 'no capture written:\n%s\n%s' % (result.stdout, result.stderr)


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

def _nav(tmp_path):
    from OpenGLContext.move.physicsplatform import PhysicsViewPlatform
    loaded = maploader.load(_map(tmp_path))
    return PhysicsViewPlatform(viewer.collision_world(loaded),
                               viewer.character_capabilities(), position=(0, 1, 0))


def test_the_gaze_rule_agrees_with_the_walk_direction(tmp_path):
    """The plan's instruction: validate the gaze rule against `_world_dir`
    before relying on it.  With no pitch, the two must be the same direction."""
    nav = _nav(tmp_path)
    nav.yaw = viewer.yaw_for_angle(0.0)
    assert viewer.gaze(nav) == pytest.approx(nav._world_dir(1.0, 0.0), abs=1e-6)


class _Look:
    """Ctrl held with an arrow: what the look bindings are declared against."""

    def __init__(self, key):
        self.key = key

    def held(self, *names):
        return self.key in names

    def pressed(self, *names):
        return False

    def modifiers(self, name):
        return (0, 1, 0) if name == self.key else (0, 0, 0)

    def mouse_delta(self):
        return (0.0, 0.0)


def _walk_mode():
    return [mode for mode in viewer.movement_modes() if mode.name == 'walk'][0]


def _look(nav, key, dt=0.1):
    """Drive the walk mode for one frame with a look key held."""
    _walk_mode().update(dt, _Look(key), nav)


def test_looking_up_raises_the_gaze(tmp_path):
    nav = _nav(tmp_path)
    before = viewer.gaze(nav)
    _look(nav, '<up>')
    assert viewer.gaze(nav)[1] > before[1]


def test_looking_down_lowers_the_gaze(tmp_path):
    nav = _nav(tmp_path)
    before = viewer.gaze(nav)
    _look(nav, '<down>')
    assert viewer.gaze(nav)[1] < before[1]


def test_looking_does_not_swing_the_heading(tmp_path):
    """Pitch tilts; it must not also turn, which a wrong rotation order does."""
    nav = _nav(tmp_path)
    nav.yaw = viewer.yaw_for_angle(90.0)
    before = viewer.gaze(nav)
    _look(nav, '<up>', 0.2)
    after = viewer.gaze(nav)
    assert np.sign(after[0] + 1e-9) == np.sign(before[0] + 1e-9)
    assert after[2] < 0 and before[2] < 0        # still facing the same way


def test_the_look_keys_tilt_without_walking(tmp_path):
    """Ctrl and an arrow means look, so the plain arrow's walk must not fire."""
    nav = _nav(tmp_path)
    start = np.array(nav.character.position, dtype='d')
    for _ in range(10):
        _look(nav, '<up>')
        nav.update(0.1)
    moved = np.array(nav.character.position, dtype='d') - start
    assert abs(moved[0]) < 1e-6 and abs(moved[2]) < 1e-6


def test_the_pitch_is_bounded_so_the_view_cannot_flip(tmp_path):
    nav = _nav(tmp_path)
    for _ in range(200):
        _look(nav, '<up>')
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
        [_map(tmp_path), '--cache-dir', str(tmp_path / 'cache')])
    loaded = viewer.load_map(options)
    assert loaded.missing_textures()            # there *is* something to ask about


def test_a_pack_already_on_disk_is_used_without_asking(tmp_path, monkeypatch):
    """Silently using what is already there is not a question."""
    pack = tmp_path / 'pack'
    (pack / 'textures').mkdir(parents=True)
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack_, cache_dir=None: str(pack))
    options = viewer.build_parser().parse_args([_map(tmp_path)])
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
        [_map(tmp_path), '--core-textures', 'always'])
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


def test_a_map_is_still_required_when_no_pack_is_being_listed(capsys):
    with pytest.raises(SystemExit) as exit_info:
        viewer.main([])
    assert exit_info.value.code != 0
    assert 'map' in capsys.readouterr().err.lower()


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
    path = _map(tmp_path)
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
    options = viewer.build_parser().parse_args([_map(tmp_path)])
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
    options = viewer.build_parser().parse_args([_map(tmp_path)])
    assert viewer.texture_pack_offer(_Loaded([]), options) == []


def test_nothing_is_offered_when_the_user_said_never(tmp_path):
    options = viewer.build_parser().parse_args([_map(tmp_path), '--core-textures', 'never'])
    assert viewer.texture_pack_offer(_Loaded(['a']), options) == []


def test_the_pack_named_by_the_map_is_the_one_offered(tmp_path, monkeypatch):
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack, cache_dir=None: None)
    options = viewer.build_parser().parse_args([_map(tmp_path)])
    options.texture_packs = ['openarena-textures', 'openarena-data']
    offer = viewer.texture_pack_offer(_Loaded(['a']), options)
    assert [pack.key for pack in offer] == ['openarena-textures', 'openarena-data']


def test_a_pack_already_on_disk_is_not_offered_again(tmp_path, monkeypatch):
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack, cache_dir=None: '/somewhere')
    options = viewer.build_parser().parse_args([_map(tmp_path)])
    assert viewer.texture_pack_offer(_Loaded(['a']), options) == []


def test_the_prompt_says_the_size_and_the_licence_before_downloading(tmp_path, monkeypatch):
    """A user cannot consent to a download whose size and terms they are not told."""
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack, cache_dir=None: None)
    options = viewer.build_parser().parse_args([_map(tmp_path)])
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
    options = viewer.build_parser().parse_args([_map(tmp_path), '--core-textures', 'always'])
    viewer.load_map(options)
    assert str(inner) in options.content


def test_the_prompt_asks_about_every_missing_pack_at_once(tmp_path, monkeypatch):
    """A release splits what one map needs across packs; a question that has to
    be answered again next launch to get the rest is a worse question."""
    monkeypatch.setattr(viewer.download, 'pack_root',
                        lambda pack, cache_dir=None: None)
    options = viewer.build_parser().parse_args([_map(tmp_path)])
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
    options = viewer.build_parser().parse_args([_map(tmp_path)])
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
    options = viewer.build_parser().parse_args([_map(tmp_path)])
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

        def set_move(self, forward=0.0, strafe=0.0, mode='walk'):
            pass

        def set_fly_move(self, forward=0.0, strafe=0.0, up=0.0):
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


class _Nav:
    def __init__(self):
        self.flying = False

    def set_fly(self, flying):
        self.flying = flying


def test_entering_the_fly_mode_puts_the_character_into_noclip():
    """Flying is a property of the character controller, so the mode change has
    to reach it; a mode that only sets movement flies into the floor."""
    nav = _Nav()
    viewer.apply_mode(nav, viewer.movement_modes()[0])       # walk
    assert not nav.flying
    fly = [m for m in viewer.movement_modes() if m.name == 'fly'][0]
    viewer.apply_mode(nav, fly)
    assert nav.flying


def test_applying_no_mode_leaves_the_character_alone():
    nav = _Nav()
    nav.flying = True
    viewer.apply_mode(nav, None)
    assert nav.flying


def test_applying_a_mode_without_a_navigator_is_harmless():
    viewer.apply_mode(None, viewer.movement_modes()[0])


# -- events through the sampler into the character ----------------------------

class _Headless(ViewPlatformMixin):
    """The context's input path with no window: dispatch, sampler, modes."""

    drawing = False

    def __init__(self, nav):
        self.contextDefinition = viewer.context_definition()
        self.platform = nav
        self._nav = nav

    def getNavigationPlatform(self):
        return self._nav

    def getEventManager(self, kind):
        return None

    def ProcessEvent(self, event):
        return None

    def triggerRedraw(self, value=1):
        pass


class _KeyEvent:
    type = 'keyboard'

    def __init__(self, name, state):
        self.name, self.state = name, state

    def getModifiers(self):
        return (0, 0, 0)


def test_a_held_key_walks_the_character_through_the_declared_modes(tmp_path):
    """The whole input path the window uses: a key event reaches the sampler,
    the mode in force reads it, and the character controller moves."""
    nav = _nav(tmp_path)
    context = _Headless(nav)
    start = np.array(nav.character.position, dtype='d')
    context._recordInput(_KeyEvent('w', 1))
    for _ in range(10):
        context.updateNavigation(0.05)
        nav.update(0.05)
    moved = np.array(nav.character.position, dtype='d') - start
    assert np.linalg.norm(moved[[0, 2]]) > 0.1


def test_releasing_the_key_stops_the_character(tmp_path):
    nav = _nav(tmp_path)
    context = _Headless(nav)
    context._recordInput(_KeyEvent('w', 1))
    context.updateNavigation(0.05)
    context._recordInput(_KeyEvent('w', 0))
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
    nav = _nav(tmp_path)
    nav.character.grounded = True
    context = _Headless(nav)
    context._recordInput(_KeyEvent('w', 1))
    context._recordInput(_KeyEvent(' ', 1))
    start = np.array(nav.character.position, dtype='d')
    context.updateNavigation(0.05)
    assert nav.character.vy > 0                  # jumped
    nav.update(0.05)
    moved = np.array(nav.character.position, dtype='d') - start
    assert np.linalg.norm(moved[[0, 2]]) > 0     # and moved, in the same frame


# -- swimming -----------------------------------------------------------------

def test_swimming_moves_the_character_free_of_gravity():
    """A swimmer that is still falling sinks to the bottom of every pool."""
    nav = _Nav()
    swim = [m for m in viewer.movement_modes() if m.name == 'swim'][0]
    viewer.apply_mode(nav, swim)
    assert nav.flying


def test_being_in_a_liquid_volume_puts_the_avatar_in_the_swim_mode(tmp_path):
    """The world imposes the mode: nothing is selected, entering water is what
    decides it (`SPEC-BSP38 §9.4`)."""
    from twitchoglc import liquids
    nav = _nav(tmp_path)
    context = _Headless(nav)
    volumes = liquids.LiquidVolumes([
        liquids.LiquidVolume(mins=np.array([-100.0, -100.0, -100.0]),
                             maxs=np.array([100.0, 100.0, 100.0]))])
    viewer.update_submerged(nav, volumes)
    context.updateNavigation(0.05)
    assert context.contextDefinition.movementMode.name == 'swim'


def test_leaving_the_water_gives_the_mode_back(tmp_path):
    from twitchoglc import liquids
    nav = _nav(tmp_path)
    context = _Headless(nav)
    empty = liquids.LiquidVolumes([])
    viewer.update_submerged(nav, empty)
    context.updateNavigation(0.05)
    assert context.contextDefinition.movementMode.name != 'swim'


def test_a_map_with_no_liquid_never_reports_being_submerged(tmp_path):
    from twitchoglc import liquids
    nav = _nav(tmp_path)
    viewer.update_submerged(nav, liquids.LiquidVolumes([]))
    assert not nav.submerged


def test_updating_without_volumes_is_harmless(tmp_path):
    viewer.update_submerged(_nav(tmp_path), None)
    viewer.update_submerged(None, None)


def test_a_companion_key_naming_no_registered_pack_is_ignored(tmp_path, monkeypatch):
    """A registry edit that leaves a dangling key must not break a load."""
    maps_root = tmp_path / 'pack'
    (maps_root / 'maps').mkdir(parents=True)
    (maps_root / 'maps' / 'oa_dm1.bsp').write_bytes(b'IBSP')
    import dataclasses
    pack = dataclasses.replace(viewer.download.OPENARENA_MAPS,
                               companions=('nonsense',))
    monkeypatch.setattr(viewer.download, 'parse_pack_target',
                        lambda target: (pack, target.split(':')[1]))
    monkeypatch.setattr(viewer.download, 'fetch_pack',
                        lambda p, cache_dir=None: str(maps_root))
    options = viewer.build_parser().parse_args(['openarena:oa_dm1'])
    assert viewer.resolve_map_target(options).endswith('oa_dm1.bsp')


def test_a_texture_pack_key_naming_no_registered_pack_is_ignored(tmp_path):
    options = viewer.build_parser().parse_args([_map(tmp_path)])
    options.texture_packs = ['nonsense']
    assert viewer.available_textures(_Loaded(['a']), options) == []
    assert viewer.texture_pack_offer(_Loaded(['a']), options) == []


# -- the keys that open a screen ---------------------------------------------

from OpenGLContext.contextdefinition import ContextDefinition  # noqa: E402
from OpenGLContext.events import eventhandlermixin, keyboardevents  # noqa: E402
from OpenGLContext.move.navigation import NavigationManager  # noqa: E402


class _Recorder:
    """Records what a context would bind, without needing a window."""

    def __init__(self):
        self.bindings = []

    def addEventHandler(self, kind, **named):
        self.bindings.append((kind, named.get('name'), named.get('state')))

    def __getattr__(self, name):
        return lambda event=None: None      # stands in for the handlers


def test_function_keys_are_bound_where_they_are_actually_delivered():
    """GLFW reports a function key as a `keyboard` transition and never as a
    `keypress`: it produces no character.  A keypress binding for one is
    accepted and then silently never fires."""
    recorder = _Recorder()
    viewer.TwitchContext.bindScreenKeys(recorder)
    for kind, name, state in recorder.bindings:
        if name and name.startswith('<F'):
            assert kind == 'keyboard', '%s bound on %r' % (name, kind)
            assert state == 1, '%s bound without a key-down state' % (name,)


def test_the_settings_and_binding_screens_have_keys():
    recorder = _Recorder()
    viewer.TwitchContext.bindScreenKeys(recorder)
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
        viewer.TwitchContext.bindScreenKeys(self)

    def _settings(self, event):
        self.opened.append('settings')

    def _bindings(self, event):
        self.opened.append('bindings')

    def _screenshot(self, event):
        self.opened.append('screenshot')

    def press(self, name):
        event = keyboardevents.KeyboardEvent()
        event.name, event.state, event.modifiers = name, 1, (0, 0, 0)
        self.ProcessEvent(event)


def test_pressing_the_screen_keys_actually_reaches_their_handlers():
    """Through the real registry and a real event, because the binding this
    replaced was accepted by the registry and then never delivered."""
    stub = _KeyStub()
    for name in ('<F10>', '<F6>', '<F2>'):
        stub.press(name)
    assert stub.opened == ['settings', 'bindings', 'screenshot']


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
    from twitchoglc import debug as twitchdebug

    class Viewer:
        contextDefinition = definition
        _walking = True
        _nav = None
        loaded = None
        player = None

        def getViewPlatform(self):
            return None

    return dict(twitchdebug.player_provider(Viewer())()).get('mode')


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
    navigation.update(0.016, _NullInput())
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


class _NullInput:
    def held(self, *names):
        return False

    def pressed(self, *names):
        return False

    def modifiers(self, name):
        return (0, 0, 0)

    def mouse_delta(self):
        return (0.0, 0.0)


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
