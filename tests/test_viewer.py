"""The viewer's command line, spawn placement and navigation rules.

Everything here is arranged so it can be checked without a live GL window.
"""

from __future__ import annotations

import os
import types

import numpy as np
import pytest

import bspbuilder
from OpenGLContext.move import viewplatform
from OpenGLContext.move.viewplatformmixin import ViewPlatformMixin
from twig_bb import (
    arena, collision, deathcam, firstperson, game, hud, maploader, player,
    projectiles, rules, viewer, weapons,
)


def _map(tmp_path, lumps=None, name='ctf-test.bsp'):
    maps = tmp_path / 'maps'
    maps.mkdir(parents=True, exist_ok=True)
    path = maps / name
    path.write_bytes(bspbuilder.build(46, lumps or bspbuilder.v46_quad(size=512.0)))
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
    lumps = bspbuilder.v46_quad(size=512.0)
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
    lumps = bspbuilder.v46_quad(size=512.0)
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
    world = collision.from_map(loaded).world
    assert world.body_count == 1
    assert int(world.motion_type[0]) != 2        # not kinematic; a static body


def test_a_map_with_nothing_solid_has_no_collision_world(tmp_path):
    lumps = bspbuilder.v46_quad()
    loaded = maploader.load(_map(tmp_path, lumps))
    for batch in loaded.world.batches:
        batch.style = batch.style.replace(solid=False)
    assert collision.from_map(loaded) is None


def test_the_jump_pad_impulse_reaches_the_character(tmp_path):
    """The end-to-end rule: a pad sets the capsule's motion outright, which is
    what `apply_impulse` does (SPEC-TRIGGER-PUSH §2.4)."""
    from OpenGLContext.move.physicsplatform import PhysicsViewPlatform
    loaded = maploader.load(_map(tmp_path))
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

def _nav(tmp_path):
    from OpenGLContext.move.physicsplatform import PhysicsViewPlatform
    loaded = maploader.load(_map(tmp_path))
    return PhysicsViewPlatform(collision.from_map(loaded).world,
                               viewer.character_capabilities(), position=(0, 1, 0))


def test_the_gaze_rule_agrees_with_the_walk_direction(tmp_path):
    """The plan's instruction: validate the gaze rule against `_world_dir`
    before relying on it.  With no pitch, the two must be the same direction."""
    nav = _nav(tmp_path)
    nav.yaw = viewer.yaw_for_angle(0.0)
    assert viewer.gaze(nav) == pytest.approx(nav._world_dir(1.0, 0.0), abs=1e-6)


class _NullInput:
    """Nobody touching anything: the input a mode is driven with by default."""

    def held(self, *names):
        return False

    def pressed(self, *names):
        return False

    def modifiers(self, name):
        return (0, 0, 0)

    def mouse_delta(self):
        return (0.0, 0.0)


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


class _Nav:
    def __init__(self):
        self.flying = False
        self.swimming = False
        self.buoyancy = None

    def set_fly(self, flying):
        self.flying = flying

    def set_swim(self, swimming, buoyancy=0.9):
        self.swimming = swimming
        self.buoyancy = buoyancy


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
    #: As on the real context before a level is walked in; a shot resolved
    #: without one still lands, it just cannot name the surface it met.
    _collision = None
    #: Nothing in the air.  A hitscan weapon needs no batch at all.
    flight = None

    def __init__(self, nav):
        self.contextDefinition = viewer.context_definition()
        #: The platform the renderer draws from, which on the real context is
        #: **not** the navigator: it is driven by the navigator each frame and
        #: its orientation does not carry the look.  Kept distinct here so a
        #: test can tell the two apart, which is the whole of what the aim
        #: tests are about.
        self.platform = viewplatform.ViewPlatform()
        self._nav = nav

    def getNavigationPlatform(self):
        return self._nav

    def getViewPort(self):
        return (800, 600)

    physicsWorld = viewer.TwigContext.physicsWorld

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

def test_the_physics_world_is_found_through_the_character(tmp_path):
    """The one query the bots, the shooting and the overlay all go through.

    A view platform does not hold the world — its *character* does — so asking
    the platform for one silently answered None.  Nothing raised: the bots
    simply never thought, no shot was ever traced, and the developer overlay
    quietly dropped its Physics section.  A wrong answer that everything
    downstream treats as "not ready yet" is the kind that hides for a long
    time, which is why this is tested rather than eyeballed.
    """
    nav = _nav(tmp_path)
    context = _Headless(nav)
    assert context.physicsWorld() is nav.character.world


def test_no_physics_world_before_walking_begins(tmp_path):
    context = _Headless(_nav(tmp_path))
    context._nav = None
    assert context.physicsWorld() is None


def _mode(name):
    return [m for m in viewer.movement_modes() if m.name == name][0]


def test_swimming_puts_the_character_in_the_water_rather_than_in_the_air():
    """Swimming is not flying, and the difference is a wall you can leave by.

    A swim implemented as noclip lets a player out of a pool through its side;
    a swimmer collides with the world and is held up by buoyancy instead.
    """
    nav = _Nav()
    viewer.apply_mode(nav, _mode('swim'))
    assert nav.swimming
    assert not nav.flying


def test_the_swim_mode_carries_its_buoyancy_to_the_character():
    nav = _Nav()
    viewer.apply_mode(nav, _mode('swim'))
    assert nav.buoyancy == pytest.approx(_mode('swim').buoyancy)


def test_leaving_the_water_takes_the_character_out_of_swimming():
    nav = _Nav()
    viewer.apply_mode(nav, _mode('swim'))
    viewer.apply_mode(nav, _mode('walk'))
    assert not nav.swimming


def test_being_in_a_liquid_volume_puts_the_avatar_in_the_swim_mode(tmp_path):
    """The world imposes the mode: nothing is selected, entering water is what
    decides it (`SPEC-BSP38 §9.4`)."""
    from twig_bb import liquids
    nav = _nav(tmp_path)
    context = _Headless(nav)
    volumes = liquids.LiquidVolumes([
        liquids.LiquidVolume(mins=np.array([-100.0, -100.0, -100.0]),
                             maxs=np.array([100.0, 100.0, 100.0]))])
    viewer.update_submerged(nav, volumes)
    context.updateNavigation(0.05)
    assert context.contextDefinition.movementMode.name == 'swim'


def test_leaving_the_water_gives_the_mode_back(tmp_path):
    from twig_bb import liquids
    nav = _nav(tmp_path)
    context = _Headless(nav)
    empty = liquids.LiquidVolumes([])
    viewer.update_submerged(nav, empty)
    context.updateNavigation(0.05)
    assert context.contextDefinition.movementMode.name != 'swim'


def test_a_map_with_no_liquid_never_reports_being_submerged(tmp_path):
    from twig_bb import liquids
    nav = _nav(tmp_path)
    viewer.update_submerged(nav, liquids.LiquidVolumes([]))
    assert not nav.submerged


def test_updating_without_volumes_is_harmless(tmp_path):
    viewer.update_submerged(_nav(tmp_path), None)
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


class _Holding(_NullInput):
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
    viewer.TwigContext.bindScreenKeys(recorder)
    for kind, name, state in recorder.bindings:
        if name and name.startswith('<F'):
            assert kind == 'keyboard', '%s bound on %r' % (name, kind)
            assert state == 1, '%s bound without a key-down state' % (name,)


def test_the_settings_and_binding_screens_have_keys():
    recorder = _Recorder()
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


class TestDyingAndComingBack:
    """Being killed has to be something the player *experiences*.

    The scoreboard said "Bot 1 fragged you" while the player went on standing
    in the same place shooting, which reads as the message being wrong rather
    than as a death: nothing about the world changed.  Three things follow from
    the rules deciding somebody died -- the gun stops answering, the camera
    stops being published as a body to shoot at, and coming back puts the
    player somewhere new.
    """

    def context(self, tmp_path, monkeypatch):
        """A viewer's match wiring with a real character and no window."""
        from OpenGLContext.move.viewplatform import ViewPlatform
        nav = _nav(tmp_path)
        context = _Headless(nav)
        # The physics platform drives a plain view platform, which is what the
        # window renders from and what a shot is aimed along.
        context.platform = ViewPlatform(position=nav.camera_position())
        context.config = viewer.build_parser().parse_args(['map.bsp'])
        context.weapons = weapons.default_table()
        context.player = player.PlayerState()
        context.player.selected = context.weapons.weapons[0].key
        context.arena = arena.Arena(weapons=context.weapons, fragLimit=15,
                                    timeLimit=10.0)
        context.arena.add(game.PLAYER_ID, position=np.zeros(3), name='You')
        context.loaded = None
        context.minds = {}
        context.botBodies = {}
        context.hud = None
        # What plays the tick.  The viewer holds one of these and the rules
        # inside it are tested against a constructed world in test_rules; what
        # is checked here is that this context is wired to one.
        context.rules = rules.Rules(context.arena, minds={},
                                    flight=projectiles.Projectiles(),
                                    spawns=[np.array([4.0, 2.0, 4.0])])
        context.deathCamera = deathcam.DeathCamera()
        # A hand with nothing in it: what a context has before a model loads,
        # and enough to take the recoil a shot writes to it.
        context.hand = firstperson.WeaponHand(context.weapons)
        for name in ('_shoot', '_aim', '_cameBack', '_watchDeath'):
            setattr(context, name,
                    getattr(viewer.TwigContext, name).__get__(context))
        fired = []
        monkeypatch.setattr(viewer.game, 'shoot',
                            lambda *a, **k: fired.append(a) or None)
        return context, fired

    def kill(self, context):
        context.arena.damage(game.PLAYER_ID, 1000.0, by='bot1')
        assert not context.arena.combatant(game.PLAYER_ID).alive

    def test_a_dead_player_cannot_shoot(self, tmp_path, monkeypatch):
        context, fired = self.context(tmp_path, monkeypatch)
        self.kill(context)
        context._shoot()
        assert fired == []

    def test_pulling_the_trigger_while_dead_asks_to_come_back(self, tmp_path,
                                                              monkeypatch):
        """The trigger is what ends a death; the timer is only its floor."""
        context, _fired = self.context(tmp_path, monkeypatch)
        self.kill(context)
        assert context.rules.waiting_to_come_back(game.PLAYER_ID)
        context._shoot()
        assert not context.rules.waiting_to_come_back(game.PLAYER_ID)

    def test_an_empty_rifle_still_comes_back(self, tmp_path, monkeypatch):
        """Dying with an empty gun must not trap you at the scoreboard.

        The whole trigger path runs here, not just ``_shoot``: a dead player
        holding fire with no ammunition went through the weapon accounting,
        which answered "OUT OF CARTRIDGES" and never reached the respawn.  The
        trigger is a respawn request while dead, whatever the gun holds.
        """
        context, _fired = self.context(tmp_path, monkeypatch)
        context._runCommands = viewer.TwigContext._runCommands.__get__(context)
        posted = []
        context.hud = type('_Hud', (),
                           {'post': lambda _self, text: posted.append(text)})()
        weapon = context.weapons.by_key(context.player.selected)
        context.player.ammo[str(weapon.ammoType)] = 0
        self.kill(context)
        assert context.rules.waiting_to_come_back(game.PLAYER_ID)
        context._runCommands([], firing=True)
        assert not context.rules.waiting_to_come_back(game.PLAYER_ID)
        # And the empty gun said nothing: a corpse has no round to be out of.
        assert posted == []

    def test_a_corpse_does_not_burn_ammunition(self, tmp_path, monkeypatch):
        """Holding fire while dead must not drain the ammunition you respawn
        with: a corpse has no gun, so the accounting does not run."""
        context, _fired = self.context(tmp_path, monkeypatch)
        context._runCommands = viewer.TwigContext._runCommands.__get__(context)
        context.hud = type('_Hud', (), {'post': lambda _self, text: None})()
        weapon = context.weapons.by_key(context.player.selected)
        context.player.ammo[str(weapon.ammoType)] = 5
        self.kill(context)
        context._runCommands([], firing=True)
        assert context.player.ammo[str(weapon.ammoType)] == 5

    def test_dying_takes_the_view_away_from_the_navigator(self, tmp_path,
                                                          monkeypatch):
        """The camera was the piece of a death with no owner: it stayed where
        it was killed, still steered by the mouse, which reads as the notice
        being wrong rather than as a death."""
        context, _fired = self.context(tmp_path, monkeypatch)
        self.kill(context)
        context._watchDeath(context.arena.drain(), dt=0.0)
        assert context.deathCamera.watching

    def test_the_view_falls_towards_the_floor(self, tmp_path, monkeypatch):
        context, _fired = self.context(tmp_path, monkeypatch)
        was = float(context._nav.camera_position()[1])
        self.kill(context)
        context._watchDeath(context.arena.drain(), dt=0.0)
        context.deathCamera.advance(deathcam.DROP_SECONDS * 2)
        assert float(context.deathCamera.position()[1]) < was

    def test_coming_back_gives_the_view_to_the_navigator_again(self, tmp_path,
                                                               monkeypatch):
        context, _fired = self.context(tmp_path, monkeypatch)
        self.kill(context)
        context._watchDeath(context.arena.drain(), dt=0.0)
        context.arena.advance(10.0)
        context.rules.ask_to_respawn(game.PLAYER_ID)
        context._cameBack(context.rules.respawn_due())
        assert not context.deathCamera.watching

    def test_a_death_with_nobody_to_blame_still_takes_the_view(self, tmp_path,
                                                               monkeypatch):
        """The lava, a long fall: there is nothing to look at, and dying is
        still dying."""
        context, _fired = self.context(tmp_path, monkeypatch)
        context.arena.kill(game.PLAYER_ID, cause='lava')
        context._watchDeath(context.arena.drain(), dt=0.0)
        assert context.deathCamera.watching

    def test_a_living_player_can(self, tmp_path, monkeypatch):
        context, fired = self.context(tmp_path, monkeypatch)
        context._shoot()
        assert fired

    def test_a_dead_player_is_not_published_into_the_match(self, tmp_path,
                                                           monkeypatch):
        """While dead there is no body to shoot at, and the camera is not it."""
        context, _fired = self.context(tmp_path, monkeypatch)
        self.kill(context)
        before = np.array(context.arena.combatant(game.PLAYER_ID).position)
        context.rules.publish(game.PLAYER_ID, (9.0, 9.0, 9.0))
        assert np.allclose(
            context.arena.combatant(game.PLAYER_ID).position, before)

    def test_a_living_player_is(self, tmp_path, monkeypatch):
        context, _fired = self.context(tmp_path, monkeypatch)
        before = np.array(context.arena.combatant(game.PLAYER_ID).position)
        context.rules.publish(game.PLAYER_ID, (9.0, 9.0, 9.0))
        assert not np.allclose(
            context.arena.combatant(game.PLAYER_ID).position, before)

    def test_respawning_moves_the_camera_rather_than_only_the_record(
            self, tmp_path, monkeypatch):
        """The camera is where the player *is*.

        The arena's respawn is overwritten a frame later by the tick that
        publishes the camera into the match, so a respawn nothing told the
        camera about puts the player straight back where they were shot.  The
        rules decide *where*; what is checked here is that this context does
        something with the answer.
        """
        context, _fired = self.context(tmp_path, monkeypatch)
        self.kill(context)
        was = np.array(context._nav.camera_position()[:3])
        context.arena.advance(10.0)
        # The player comes back when they *ask*; see `Rules.ask_to_respawn`.
        context.rules.ask_to_respawn(game.PLAYER_ID)
        context._cameBack(context.rules.respawn_due())
        assert context.arena.combatant(game.PLAYER_ID).alive
        assert not np.allclose(context._nav.camera_position()[:3], was)


class _MessageSink:
    """Just enough HUD for the weapon commands: somewhere to post a line."""

    def __init__(self):
        self.lines = []

    def post(self, text, *args, **named):
        self.lines.append(text)


class _WheelRecorder(_Recorder):
    """A recorder that also keeps the *functions* a wheel notch would reach."""

    def __init__(self):
        super().__init__()
        self.wheel = {}
        self._wheelHandlers = []

    def addEventHandler(self, kind, **named):
        super().addEventHandler(kind, **named)
        if kind == 'mousebutton':
            self.wheel.setdefault(
                (named.get('button'), named.get('state')), []
            ).append(named.get('function'))

    def notch(self, button):
        """Deliver one wheel notch the way GLFW's scroll callback does.

        A notch is a press *and* a release (see
        :meth:`OpenGLContext.events.glfwevents.GLFWEventHandler._emitWheel`),
        so both states are offered and only the ones bound to them run.
        """
        for state in (1, 0):
            for function in self.wheel.get((button, state), ()):
                function(None)


class TestTheWeaponWheel:
    """One notch of the wheel is one weapon.

    A wheel notch arrives as a press *and* a release, so anything bound to
    both — or bound twice — steps twice for one movement of the finger, which
    reads as a wheel that skips a weapon.
    """

    def context(self):
        recorder = _WheelRecorder()
        recorder.weapons = weapons.default_table()
        recorder.player = player.PlayerState.carrying(recorder.weapons)
        recorder.weaponBindings = viewer.controls.WeaponBindings()
        recorder.hud = _MessageSink()
        for name in ('_bindWeaponKeys', '_wheelWeapon', '_runCommands'):
            setattr(recorder, name,
                    getattr(viewer.TwigContext, name).__get__(recorder))
        recorder._bindWeaponKeys()
        return recorder

    def held(self, recorder):
        return str(recorder.player.selected)

    def test_one_notch_up_moves_one_weapon(self):
        recorder = self.context()
        keys = recorder.weapons.keys()
        before = self.held(recorder)
        recorder.notch(viewer.WHEEL_UP)
        assert self.held(recorder) == keys[(keys.index(before) + 1) % len(keys)]

    def test_one_notch_down_moves_one_weapon(self):
        recorder = self.context()
        keys = recorder.weapons.keys()
        before = self.held(recorder)
        recorder.notch(viewer.WHEEL_DOWN)
        assert self.held(recorder) == keys[(keys.index(before) - 1) % len(keys)]

    def test_a_notch_is_bound_once_and_only_on_the_press(self):
        """Bound to the release as well, every notch would count twice."""
        recorder = self.context()
        for button in (viewer.WHEEL_UP, viewer.WHEEL_DOWN):
            assert len(recorder.wheel.get((button, 1), [])) == 1
            assert not recorder.wheel.get((button, 0))

    def test_a_full_turn_of_the_wheel_comes_back_to_where_it_started(self):
        recorder = self.context()
        before = self.held(recorder)
        for _notch in range(len(recorder.weapons.keys())):
            recorder.notch(viewer.WHEEL_UP)
        assert self.held(recorder) == before


class TestTheScoreboardKey:
    """The board is held down, not toggled.

    It covers the middle of the screen, so a board somebody left up by
    accident is a board they get shot behind.
    """

    def context(self):
        recorder = _WheelRecorder()
        recorder.weapons = weapons.default_table()
        recorder.player = player.PlayerState.starting(recorder.weapons)
        recorder.weaponBindings = viewer.controls.WeaponBindings()
        recorder.arena = arena.Arena(weapons=recorder.weapons, fragLimit=15,
                                     timeLimit=10.0)
        recorder.arena.add(game.PLAYER_ID, name='You')
        recorder.arena.add('bot1', bot=True, name='Bot 1')
        recorder.hud = hud.GameHUD(recorder.weapons)
        for name in ('_bindWeaponKeys', '_wheelWeapon', '_runCommands',
                     '_showScores', '_hideScores'):
            setattr(recorder, name,
                    getattr(viewer.TwigContext, name).__get__(recorder))
        recorder._bindWeaponKeys()
        return recorder

    def bound(self, recorder, state):
        return [name for kind, name, at in recorder.bindings
                if kind == 'keyboard' and at == state]

    def test_it_is_bound_to_both_the_press_and_the_release(self):
        recorder = self.context()
        assert viewer.SCOREBOARD_KEY in self.bound(recorder, 1)
        assert viewer.SCOREBOARD_KEY in self.bound(recorder, 0)

    def test_holding_it_puts_the_board_up(self):
        recorder = self.context()
        recorder._showScores()
        assert recorder.hud.standings.visible
        assert len(recorder.hud.standings.children) == 3   # heading and two

    def test_letting_go_takes_it_down(self):
        recorder = self.context()
        recorder._showScores()
        recorder._hideScores()
        assert not recorder.hud.standings.visible

    def test_a_run_with_no_hud_is_harmless(self):
        """A capture run has none and must still be able to press keys."""
        recorder = self.context()
        recorder.hud = None
        recorder._showScores()
        recorder._hideScores()


class TestTheMatchWiringStaysInStep:
    """What draws a fight must be what a fight is emitted into.

    The match is built once at start-up (so the menu has something) and again
    when a level is loaded, and each build makes a fresh arena, a fresh set of
    effect emitters and a fresh projectile batch. Anything that captured the
    *first* set and was not rebuilt with the second is then looking at objects
    nothing writes to any more: the effects go on being born into emitters that
    are not in the scene, so they are never stepped and never drawn, and from
    inside the game the weapons appear to do nothing at all.
    """

    def context(self):
        """The match wiring built twice, as a launch does.

        The weapon table and the audio engine are supplied rather than built:
        what is under test is which objects the presenter ends up holding, and
        loading a first-person model to find that out would be a test that
        failed for two reasons.
        """
        made = _Headless(None)
        made.config = viewer.build_parser().parse_args(['map.bsp'])
        made.loaded = None
        made.weapons = weapons.default_table()
        made._audioEngine = lambda: None
        for name in ('_buildMatch', '_installMatch', '_bindPresenter'):
            setattr(made, name,
                    getattr(viewer.TwigContext, name).__get__(made))
        made._buildMatch()          # what OnInit does before a level exists
        made.hud = _MessageSink()
        made._bindPresenter()       # what _startGame does once there is a HUD
        made._buildMatch()          # what loading a level does
        return made

    def test_the_presenter_reads_the_match_that_is_being_played(self):
        made = self.context()
        assert made._presenter.match is made.arena

    def test_the_effects_it_draws_into_are_the_ones_in_the_scene(self):
        made = self.context()
        assert made._presenter.effects is made.effects

    def test_the_sounds_it_plays_are_for_the_match_being_played(self):
        made = self.context()
        assert made._presenter.sounds.match is made.arena

    def test_the_bots_think_about_the_match_being_played(self):
        made = self.context()
        assert set(made.minds) == {one.id for one in made.arena.bots()}

    def test_a_burst_reaches_an_emitter_that_is_in_the_scene(self):
        """The end of the chain, and the thing a player actually notices."""
        made = self.context()
        made.arena.impact(point=(1, 0, 0), normal=(0, 1, 0), surface='stone')
        made._presenter.show(made.arena.drain(), camera=(0, 0, 0),
                             forward=(0, 0, -1))
        drawn = {id(child) for child in made.effects.group.children}
        alive = [emitter for emitter in made.effects.emitters.values()
                 if emitter.pool.live]
        assert alive
        assert all(id(emitter) in drawn for emitter in alive)


class TestTheMouseFiresInTheGame:
    """A click on the left button has to reach a shot, through the real path.

    The unit tests say the binding names the button and the sampler records
    it; this says the two meet — that a press delivered as the backend
    delivers it, sampled the way the frame loop samples it, spends a round and
    takes a shot.
    """

    def context(self, monkeypatch):
        from OpenGLContext.events.inputstate import InputState
        made = _Headless(None)
        made.config = viewer.build_parser().parse_args(['map.bsp'])
        made.weapons = weapons.default_table()
        made.player = player.PlayerState.carrying(made.weapons)
        made.player.selected = made.weapons.weapons[0].key
        # A shot can only come from a living body in a match, and the trigger
        # path now asks whether that body is alive before spending a round.
        made.arena = arena.Arena(weapons=made.weapons, fragLimit=15,
                                 timeLimit=10.0)
        made.arena.add(game.PLAYER_ID, position=np.zeros(3), name='You')
        made.weaponBindings = viewer.controls.WeaponBindings()
        made.hud = _MessageSink()
        made._inputState = InputState()
        made.getInputState = lambda: made._inputState
        made._fov = None
        fired = []
        for name in ('_sampleWeapons', '_runCommands', '_sight'):
            setattr(made, name,
                    getattr(viewer.TwigContext, name).__get__(made))
        made._shoot = lambda: fired.append(1)
        return made, fired

    def press(self, made, down=1, button=viewer.controls.LEFT_BUTTON):
        from OpenGLContext.events.mouseevents import MouseButtonEvent
        event = MouseButtonEvent()
        event.button = button
        event.state = down
        made._inputState.process(event)

    def test_a_held_button_takes_a_shot(self, monkeypatch):
        made, fired = self.context(monkeypatch)
        self.press(made)
        made._sampleWeapons()
        assert fired

    def test_it_spends_a_round(self, monkeypatch):
        made, _fired = self.context(monkeypatch)
        weapon = made.weapons.by_key(made.player.selected)
        before = made.player.ammo_for(weapon)
        self.press(made)
        made._sampleWeapons()
        assert made.player.ammo_for(weapon) < before

    def test_nothing_is_fired_before_the_button_goes_down(self, monkeypatch):
        made, fired = self.context(monkeypatch)
        made._sampleWeapons()
        assert not fired

    def test_letting_go_stops_it(self, monkeypatch):
        made, fired = self.context(monkeypatch)
        self.press(made)
        made._sampleWeapons()
        self.press(made, down=0)
        del fired[:]
        made._sampleWeapons()
        assert not fired


class TestTheMouseSightsTheRifle:
    """The other button, through the same sampler: it narrows the frustum.

    The whole of the zoom on the window's side is that the field of view the
    view is drawn with follows what is in the player's hand -- so what is
    checked is the platform's own frustum, which is what the projection is
    built from and what the reticule is scaled through.
    """

    def context(self, key='rifle'):
        from OpenGLContext.events.inputstate import InputState
        made = _Headless(None)
        made.config = viewer.build_parser().parse_args(['map.bsp'])
        made.weapons = weapons.default_table()
        made.player = player.PlayerState.carrying(made.weapons)
        made.player.selected = key
        made.weaponBindings = viewer.controls.WeaponBindings()
        made.hud = _MessageSink()
        made._fov = None
        made._inputState = InputState()
        made.getInputState = lambda: made._inputState
        for name in ('_sampleWeapons', '_runCommands', '_sight'):
            setattr(made, name,
                    getattr(viewer.TwigContext, name).__get__(made))
        made._shoot = lambda: None
        return made

    def press(self, made, down=1):
        from OpenGLContext.events.mouseevents import MouseButtonEvent
        event = MouseButtonEvent()
        event.button = viewer.controls.RIGHT_BUTTON
        event.state = down
        made._inputState.process(event)

    def test_holding_it_narrows_the_view(self):
        made = self.context()
        wide = viewer.view_fov(made.platform)
        self.press(made)
        made._sampleWeapons()
        assert viewer.view_fov(made.platform) < wide

    def test_letting_go_gives_the_view_back(self):
        made = self.context()
        wide = viewer.view_fov(made.platform)
        self.press(made)
        made._sampleWeapons()
        self.press(made, down=0)
        made._sampleWeapons()
        assert viewer.view_fov(made.platform) == pytest.approx(wide)

    def test_switching_weapon_while_sighted_gives_it_back_too(self):
        """Nothing has to remember to cancel it: it is read from the hand."""
        made = self.context()
        wide = viewer.view_fov(made.platform)
        self.press(made)
        made._sampleWeapons()
        made.player.selected = 'pistol'
        made._sampleWeapons()
        assert viewer.view_fov(made.platform) == pytest.approx(wide)

    def test_a_weapon_with_no_sight_does_nothing(self):
        made = self.context(key='shotgun')
        wide = viewer.view_fov(made.platform)
        self.press(made)
        made._sampleWeapons()
        assert viewer.view_fov(made.platform) == pytest.approx(wide)

    def test_the_near_and_far_planes_are_left_alone(self):
        """A frustum is four numbers and only one of them is the zoom."""
        made = self.context()
        made.platform.setFrustum(near=0.05, far=9000.0)
        self.press(made)
        made._sampleWeapons()
        assert made.platform.frustum[2:] == (0.05, 9000.0)


class TestAShotGoesWhereTheCameraLooks:
    """The reticule is in the middle of the screen, so a shot leaves along it.

    There are two ways to ask a view platform which way it is looking and they
    are not interchangeable: **the platform's angles rotate the world, not the
    camera**, so a heading built from the inverse of its orientation agrees
    with the gaze only while nothing is turned, and mirrors it as soon as
    something is. That is a shot that goes left when the player turns right,
    and up when they look down — and it looks correct in the one case anybody
    checks first, straight ahead.

    `viewer.gaze` is the verified one: `test_the_gaze_rule_agrees_with_the_walk_direction`
    checks it against `_world_dir`, which is checked against the map-angle
    spec. So a shot must agree with `gaze`.
    """

    def platform(self, tmp_path, yaw=0.0, pitch=0.0):
        """The navigator the viewer actually aims from."""
        made = _nav(tmp_path)
        made.yaw, made.pitch = yaw, pitch
        return made

    def fired(self, nav):
        """The direction the *context* would fire, given this navigator.

        Through the context's own aim rather than a helper, because the bug
        was which object the context asked: the view platform the renderer
        draws from does not carry the look at all, so a shot taken from it
        went the same way whichever way the player turned.
        """
        context = _Headless(nav)
        context._nav = nav
        return np.asarray(viewer.TwigContext._aim(context)[1], dtype='d')

    def origin(self, nav):
        context = _Headless(nav)
        context._nav = nav
        return np.asarray(viewer.TwigContext._aim(context)[0], dtype='d')

    def test_straight_ahead_it_agrees(self, tmp_path):
        made = self.platform(tmp_path)
        assert self.fired(made) == pytest.approx(viewer.gaze(made), abs=1e-6)

    def test_turned_left_it_still_agrees(self, tmp_path):
        made = self.platform(tmp_path, yaw=0.7)
        assert self.fired(made) == pytest.approx(viewer.gaze(made), abs=1e-6)

    def test_turned_right_it_still_agrees(self, tmp_path):
        made = self.platform(tmp_path, yaw=-0.7)
        assert self.fired(made) == pytest.approx(viewer.gaze(made), abs=1e-6)

    def test_a_pitched_shot_goes_the_way_the_camera_looks(self, tmp_path):
        """The grenade that went up when the player looked down.

        Which sign of ``pitch`` looks down is not asserted -- the platform's
        angles turn the world, so the sign says nothing on its own. What is
        asserted is that the shot goes the same way the gaze does, for both.
        """
        for pitch in (-0.6, 0.6):
            made = self.platform(tmp_path, pitch=pitch)
            looking = float(viewer.gaze(made)[1])
            assert abs(looking) > 0.1, 'the fixture is not pitched'
            assert float(self.fired(made)[1]) * looking > 0.0

    def test_looking_down_with_the_keys_shoots_downward(self, tmp_path):
        """Through the look binding, which is how a player pitches the view."""
        made = self.platform(tmp_path)
        for _frame in range(5):
            _look(made, '<down>')
        looking = float(viewer.gaze(made)[1])
        assert looking < 0.0, 'the look-down key did not lower the gaze'
        assert float(self.fired(made)[1]) < 0.0

    def test_turned_and_pitched_together_it_agrees(self, tmp_path):
        made = self.platform(tmp_path, yaw=1.1, pitch=-0.4)
        assert self.fired(made) == pytest.approx(viewer.gaze(made), abs=1e-6)

    def test_it_is_a_unit_heading(self, tmp_path):
        made = self.platform(tmp_path, yaw=1.1, pitch=-0.4)
        assert float(np.linalg.norm(self.fired(made))) == pytest.approx(1.0)

    def test_the_shot_leaves_from_where_the_camera_is(self, tmp_path):
        """From the navigator too: the same object that knows where it looks."""
        made = self.platform(tmp_path, yaw=1.1)
        assert self.origin(made) == pytest.approx(
            np.asarray(made.camera_position()[:3], dtype='d'), abs=1e-6)

    def test_with_no_navigator_it_aims_straight_ahead(self, tmp_path):
        """A viewer that has not started walking still answers something sane."""
        class _NotWalkingYet:
            _nav = None

        origin, direction = viewer.TwigContext._aim(_NotWalkingYet())
        assert np.asarray(direction) == pytest.approx((0.0, 0.0, -1.0))
        assert np.asarray(origin) == pytest.approx((0.0, 0.0, 0.0))


class TestTheShotIsUnderTheCrosshair:
    """The one test above this that could not be argued with.

    Everything else here checks the aim against `viewer.gaze`, and `gaze`
    against `_world_dir`: three rules that agree with each other and could all
    be wrong the same way, which is what a shot that pans the wrong way *is*.

    So this checks the aim against something that is not a rule at all — the
    two matrices the renderer builds the frame from. A point along the aim is
    put through them exactly as a vertex is, and the answer has to be the
    middle of the screen, because that is where the crosshair is drawn. There
    is no convention left to get backwards: if this passes, what the player
    sees under the crosshair is what the shot hits.

    The matrices are pure arithmetic (`ViewPlatform.modelMatrix` and
    `.viewMatrix`), so this needs no window; the same measurement taken from
    inside the running game agrees with it.
    """

    #: Metres down the aim to put the mark.  Far enough that any error in the
    #: heading is a large screen offset rather than a rounding difference.
    RANGE = 30.0

    def screen_position(self, nav):
        """Where the shot's mark lands on screen, in normalised device space.

        (0, 0) is the middle -- the crosshair -- and (±1, ±1) the edges.
        """
        platform = viewplatform.ViewPlatform()
        # Driven the way the game drives it, so the frame measured here is the
        # frame the player is shown.
        platform.setPosition(nav.camera_position())
        platform.setOrientation(nav.camera_orientation())
        context = _Headless(nav)
        context._nav = nav
        origin, direction = viewer.TwigContext._aim(context)
        mark = np.append(np.asarray(origin, dtype='d')
                         + np.asarray(direction, dtype='d') * self.RANGE, 1.0)
        clip = np.dot(mark, np.dot(np.asarray(platform.modelMatrix()),
                                   np.asarray(platform.viewMatrix())))
        assert clip[3] > 0.0, 'the shot went behind the camera'
        return clip[:2] / clip[3]

    @pytest.mark.parametrize('yaw', [0.0, 0.7, -0.7, 2.4, -2.4])
    @pytest.mark.parametrize('pitch', [0.0, 0.5, -0.5])
    def test_it_lands_in_the_middle_of_the_screen(self, tmp_path, yaw, pitch):
        made = _nav(tmp_path)
        made.yaw, made.pitch = yaw, pitch
        assert self.screen_position(made) == pytest.approx((0.0, 0.0),
                                                           abs=1e-6)


class TestEscapeMidMatch:
    """Escape must never end a match without asking.

    It was bound straight to the context's forcible quit, so a key pressed to
    close a screen, dismiss a notice or back out of anything at all ended the
    session -- with no confirmation and nothing to undo it.
    """

    def context(self, loaded=True):
        recorder = _WheelRecorder()
        recorder.quits = 0
        recorder.pushed = []
        recorder._menuPanel = None
        recorder.loaded = (types.SimpleNamespace(name='q3dm1')
                           if loaded else None)
        recorder.config = types.SimpleNamespace(cache_dir=None)
        recorder.pushOverlay = lambda panel: (recorder.pushed.append(panel)
                                              or panel)
        recorder.OnQuit = lambda event=None: setattr(
            recorder, 'quits', recorder.quits + 1)
        for name in ('OnEscape', 'showMenu', '_closeMenu', '_menuSubtitle',
                     '_playScreen', '_contentScreen', '_creditsScreen',
                     '_settings'):
            setattr(recorder, name,
                    getattr(viewer.TwigContext, name).__get__(recorder))
        return recorder

    def test_it_puts_the_menu_up_instead_of_quitting(self):
        recorder = self.context()
        recorder.OnEscape()
        assert recorder.pushed, 'no menu appeared'
        assert recorder.quits == 0

    def test_that_menu_offers_resume(self):
        recorder = self.context()
        recorder.OnEscape()
        assert recorder.pushed[-1].find('resume') is not None

    def test_resuming_puts_the_menu_away_and_keeps_the_match(self):
        recorder = self.context()
        recorder.OnEscape()
        panel = recorder.pushed[-1]
        panel.find('resume').activate()
        assert panel.closed
        assert recorder.quits == 0

    def test_quitting_is_still_offered(self):
        recorder = self.context()
        recorder.OnEscape()
        recorder.pushed[-1].find('quit').activate()
        assert recorder.quits == 1

    def test_with_no_match_running_there_is_nothing_to_resume(self):
        """At the start screen, Escape has nothing to go back to."""
        recorder = self.context(loaded=False)
        recorder.OnEscape()
        assert recorder.pushed[-1].find('resume') is None
