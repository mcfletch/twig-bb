"""The stand-in HUD demo: the room, and the weapon held in the player's hands.

The parts that can be checked without a window are the scene it builds and the
arithmetic that puts a weapon where a first-person view wants it; the window
itself is one subprocess capture at the end, the same shape as the viewer's.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from twitchoglc import hudsample

VENV_PYTHON = sys.executable


class TestTheRoom:
    def test_it_builds_something_to_stand_in(self):
        assert hudsample.build_room()

    def test_it_is_lit(self):
        """A HUD over an unlit room says nothing about whether it reads."""
        from OpenGLContext.scenegraph.light import DirectionalLight, PointLight
        lights = [child for child in hudsample.build_room()
                  if isinstance(child, (DirectionalLight, PointLight))]
        assert lights

    def test_it_is_closed_in(self):
        """Floor, ceiling and four walls: six slabs before the blocks."""
        from OpenGLContext.scenegraph.basenodes import Transform
        boxes = [child for child in hudsample.build_room()
                 if isinstance(child, Transform)]
        assert len(boxes) >= 6


class TestCommandLine:
    def test_the_capture_options_are_offered(self):
        options = hudsample.build_parser().parse_args(['--capture', 'out.png'])
        assert options.capture == 'out.png'

    def test_it_runs_with_no_arguments_at_all(self):
        assert hudsample.build_parser().parse_args([]).capture is None


@pytest.mark.gl
@pytest.mark.slow
def test_the_demo_renders_the_hud_and_the_weapon(tmp_path):
    """The whole path: a room, a glTF weapon in hand and the HUD over both."""
    out = tmp_path / 'hud.png'
    result = subprocess.run(
        [VENV_PYTHON, '-m', 'twitchoglc.hudsample', '--capture', str(out),
         '--frames', '6', '--capture-delay', '0.2'],
        capture_output=True, text=True, timeout=300,
        env=dict(os.environ, OPENGLCONTEXT_PROFILE='core',
                 OPENGLCONTEXT_BACKEND='glfw'))
    assert out.exists(), 'no capture written:\n%s\n%s' % (result.stdout,
                                                          result.stderr)
    from PIL import Image
    import numpy as np
    pixels = np.asarray(Image.open(out).convert('RGB')).astype(int)
    height, width = pixels.shape[:2]
    # The reticule is in the middle and the weapon bar along the bottom; both
    # are the HUD rather than the room, so a frame without them is a frame the
    # HUD did not reach.
    middle = pixels[height // 2 - 12:height // 2 + 12,
                    width // 2 - 12:width // 2 + 12]
    assert middle.std() > 4, 'nothing that looks like a reticule in the middle'
    bottom = pixels[height - 40:, :]
    assert bottom.std() > 4, 'nothing along the bottom of the screen'


class TestChoosingAWeaponUpFront:
    def test_a_weapon_can_be_named_on_the_command_line(self):
        options = hudsample.build_parser().parse_args(['--weapon', 'shotgun'])
        assert options.weapon == 'shotgun'

    def test_none_is_the_default(self):
        assert hudsample.build_parser().parse_args([]).weapon is None
