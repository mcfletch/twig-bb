"""Holding a weapon where a first-person view wants it.

Both the map viewer and the demo draw the weapon through this, so it is tested
on its own: where the holder sits, which way the hand faces, and that switching
weapons neither re-reads a model nor breaks on one that will not load.
"""

from __future__ import annotations

import math

import pytest

from OpenGLContext.scenegraph.basenodes import Transform

from twitchoglc import firstperson, weapons


class FakeQuaternion:
    def __init__(self, xyzr):
        self._xyzr = xyzr

    def XYZR(self):
        return self._xyzr


class FakePlatform:
    def __init__(self, position=(1.0, 2.0, 3.0, 1.0), xyzr=(0.0, 1.0, 0.0, 0.5)):
        self.position = position
        self.quaternion = FakeQuaternion(xyzr)


class TestWeaponInHand:
    def test_the_holder_carries_the_weapon_s_own_placement(self):
        weapon = weapons.default_table().by_key('pistol')
        holder = firstperson.weapon_transform(weapon)
        assert tuple(round(float(v), 4) for v in holder.translation) \
            == tuple(round(float(v), 4) for v in weapon.modelOffset)
        assert float(holder.scale[0]) == pytest.approx(float(weapon.modelScale))

    def test_the_yaw_is_about_the_up_axis_in_radians(self):
        """The holder positions; the turning hangs beneath it."""
        weapon = weapons.Weapon(modelYaw=90.0)
        holder = firstperson.weapon_transform(weapon)
        turn = holder.children[0]
        assert tuple(float(v) for v in turn.rotation[:3]) == (0.0, 1.0, 0.0)
        assert float(turn.rotation[3]) == pytest.approx(math.pi / 2)

    def test_the_hand_follows_the_camera(self):
        hand = Transform()
        firstperson.aim_at_camera(hand, FakePlatform())
        assert tuple(float(v) for v in hand.translation) == (1.0, 2.0, 3.0)

    def test_the_hand_turns_the_opposite_way_to_the_view(self):
        """The view matrix rotates the world; the camera is its inverse."""
        hand = Transform()
        firstperson.aim_at_camera(hand, FakePlatform(xyzr=(0.0, 1.0, 0.0, 0.5)))
        assert float(hand.rotation[3]) == pytest.approx(-0.5)

    def test_a_context_with_no_camera_yet_is_not_an_error(self):
        hand = Transform()
        firstperson.aim_at_camera(hand, None)
        assert tuple(float(v) for v in hand.translation) == (0.0, 0.0, 0.0)


class TestSwappingWeapons:
    def test_selecting_puts_a_model_in_the_hand(self):
        table = weapons.default_table()
        hand = firstperson.WeaponHand(table)
        assert hand.select(table.by_key('pistol')) is True
        assert hand.group.children

    def test_selecting_the_same_weapon_again_changes_nothing(self):
        table = weapons.default_table()
        hand = firstperson.WeaponHand(table)
        hand.select(table.by_key('pistol'))
        assert hand.select(table.by_key('pistol')) is False

    def held(self, hand):
        """The model node at the end of the holder's turning chain."""
        node = hand.group.children[0]
        while getattr(node, 'children', None):
            node = node.children[0]
        return node

    def test_a_model_is_read_once_however_often_it_is_selected(self):
        """Switching weapons is a thing done several times a second."""
        table = weapons.default_table()
        hand = firstperson.WeaponHand(table)
        hand.select(table.by_key('pistol'))
        first = self.held(hand)
        hand.select(table.by_key('shotgun'))
        hand.select(table.by_key('pistol'))
        assert self.held(hand) is first

    def test_a_model_that_will_not_load_leaves_the_hand_empty(self):
        table = weapons.default_table()
        hand = firstperson.WeaponHand(table)
        broken = weapons.Weapon(key='ghost', model='weapons/absent.glb')
        assert hand.select(broken) is True
        assert list(hand.group.children[0].children) == []

    def test_holding_nothing_is_allowed(self):
        hand = firstperson.WeaponHand(weapons.default_table())
        assert hand.select(None) is False        # nothing was held to begin with


class TestPinnedToTheView:
    """A held weapon must not lag the camera by a frame.

    Posed from an idle callback it is written *before* the camera moves, so it
    hangs back and then slides forward as the player walks -- which is the
    single most distracting thing a first-person model can do.  The renderer
    offers one window where the camera is settled and nothing has been gathered
    (``placeViewAttachments``), and the pose has to be written there.
    """

    def test_the_viewer_places_its_weapon_through_the_render_hook(self):
        from twitchoglc import viewer
        assert hasattr(viewer.TwitchContext, 'placeViewAttachments')

    def test_the_demo_does_too(self):
        from twitchoglc import hudsample
        assert hasattr(hudsample.HUDSampleContext, 'placeViewAttachments')

    def test_the_hook_poses_the_hand_from_the_camera_it_is_given(self):
        """The pose written is the one the frame is about to be drawn with."""
        hand = Transform()
        firstperson.aim_at_camera(hand, FakePlatform(position=(5.0, 6.0, 7.0, 1.0)))
        assert tuple(float(v) for v in hand.translation) == (5.0, 6.0, 7.0)

    def test_moving_the_camera_moves_the_hand_with_it(self):
        """No lag: two poses in a row, and the hand is at the second."""
        hand = Transform()
        firstperson.aim_at_camera(hand, FakePlatform(position=(0.0, 0.0, 0.0, 1.0)))
        firstperson.aim_at_camera(hand, FakePlatform(position=(0.0, 0.0, -4.0, 1.0)))
        assert tuple(float(v) for v in hand.translation) == (0.0, 0.0, -4.0)

    def test_nothing_poses_the_weapon_from_the_idle_callback(self):
        """The regression itself: OnIdle must not be where this happens."""
        import inspect
        from twitchoglc import viewer
        source = inspect.getsource(viewer.TwitchContext.OnIdle)
        assert '_updateWeapon' not in source, (
            'the weapon is posed in OnIdle, which runs before the camera moves')


class TestItIsActuallyInViewSpace:
    """The property "pinned", stated as arithmetic rather than as ordering.

    The renderer draws a node with ``modelview = view x model``.  A weapon put
    at the camera's own pose carries ``model = cameraPose x local``, and the
    view matrix *is* that pose inverted -- so the two cancel and what is left
    is ``local``, whatever the camera is doing.  Assert that directly and the
    weapon cannot drift, lag or swim: it is the same pixels every frame by
    construction.
    """

    @staticmethod
    def forward(node):
        """A transform's forward matrix; identity when it has nothing to do.

        A Transform with no translation, rotation or scale bakes no matrix at
        all and answers None, which is the camera-at-the-origin case here.
        """
        import numpy as np
        matrix = node.localMatrices().data[0]
        return np.identity(4) if matrix is None else matrix

    def modelview(self, platform, hand, local):
        """What the pass would draw the weapon with, from real matrices."""
        import numpy as np
        firstperson.aim_at_camera(hand, platform)
        view = platform.modelMatrix()
        # Row-vector convention, as the renderer uses: a point runs through the
        # local transform, then the hand's, then the view.
        model = np.dot(self.forward(local), self.forward(hand))
        return np.dot(model, view)

    def local(self):
        from twitchoglc import weapons
        return firstperson.weapon_transform(
            weapons.default_table().by_key('pistol'))

    def platform(self, position, rotation=(0, 1, 0, 0.0)):
        from OpenGLContext.move.viewplatform import ViewPlatform
        return ViewPlatform(position=position, orientation=rotation)

    def test_the_camera_cancels_out_of_the_weapon_s_modelview(self):
        import numpy as np
        local = self.local()
        here = self.modelview(self.platform((0.0, 0.0, 0.0)), Transform(), local)
        there = self.modelview(self.platform((12.0, 3.0, -40.0)), Transform(),
                               local)
        assert np.allclose(here, there, atol=1e-4), (
            'the weapon moves in view space when the camera moves')

    def test_turning_the_camera_does_not_move_it_either(self):
        import numpy as np
        import math
        local = self.local()
        ahead = self.modelview(self.platform((0.0, 0.0, 0.0)), Transform(), local)
        turned = self.modelview(
            self.platform((0.0, 0.0, 0.0), (0, 1, 0, math.pi / 3)),
            Transform(), local)
        assert np.allclose(ahead, turned, atol=1e-4), (
            'the weapon swings away from the view when the camera turns')

    def test_walking_and_turning_at_once_still_leaves_it_put(self):
        import numpy as np
        local = self.local()
        start = self.modelview(self.platform((0.0, 1.7, 0.0)), Transform(), local)
        moved = self.modelview(
            self.platform((-3.0, 1.9, 8.0), (0, 1, 0, -2.2)), Transform(), local)
        assert np.allclose(start, moved, atol=1e-4)

    def test_what_is_left_is_the_weapon_s_own_offset(self):
        """And it is the offset the table asked for, not some other place."""
        import numpy as np
        local = self.local()
        drawn = self.modelview(self.platform((4.0, 5.0, 6.0)), Transform(), local)
        assert np.allclose(drawn, self.forward(local), atol=1e-4)


class TestOrientingASourceModel:
    """Art does not arrive facing the way a first-person view wants it.

    The CC0 firearms are modelled lying along +Y in centimetres; the renderer
    works in metres with the view looking down -Z.  Turning one to face
    forward needs a rotation about more than the up axis, so the table carries
    all three angles and they are applied in a stated order.
    """

    def rotations(self, holder):
        """Every rotation on the chain, outermost first."""
        found = []
        node = holder
        while node is not None:
            rotation = tuple(float(v) for v in node.rotation)
            if rotation[3]:
                found.append(rotation)
            children = list(getattr(node, 'children', []))
            node = children[0] if children else None
        return found

    def test_a_weapon_can_be_pitched_as_well_as_yawed(self):
        from twitchoglc import weapons
        holder = firstperson.weapon_transform(
            weapons.Weapon(modelPitch=-90.0))
        assert self.rotations(holder), 'the pitch was dropped'

    def test_the_pitch_is_about_the_side_axis_in_radians(self):
        from twitchoglc import weapons
        holder = firstperson.weapon_transform(weapons.Weapon(modelPitch=90.0))
        axis = self.rotations(holder)[0]
        assert axis[:3] == (1.0, 0.0, 0.0)
        assert axis[3] == pytest.approx(math.pi / 2)

    def test_all_three_angles_can_be_used_at_once(self):
        from twitchoglc import weapons
        holder = firstperson.weapon_transform(
            weapons.Weapon(modelYaw=10.0, modelPitch=20.0, modelRoll=30.0))
        assert len(self.rotations(holder)) == 3

    def test_a_weapon_that_needs_no_turning_gets_no_rotation_nodes(self):
        from twitchoglc import weapons
        holder = firstperson.weapon_transform(weapons.Weapon())
        assert self.rotations(holder) == []

    def test_the_model_hangs_below_whatever_turning_it_needed(self):
        """Whatever the chain, the model is at the end of it."""
        from twitchoglc import weapons
        holder = firstperson.weapon_transform(
            weapons.Weapon(modelYaw=10.0, modelPitch=20.0))
        node, depth = holder, 0
        while getattr(node, 'children', None):
            node = node.children[0]
            depth += 1
        assert depth >= 2


class TestSeeingTheWeaponAtAll:
    """A weapon must not be a black blob in a map that places no dynamic lights.

    Both map families bake their lighting into lightmaps, so geometry that is
    not part of the map is lit by almost nothing.  The obvious fix -- a fill
    light riding the camera -- was tried and *measured*: it brightened the map
    more than it brightened the weapon, which is a flashlight washing out the
    baked lighting to show a stand-in.  So the light stays out of the rig and
    the fill lives in the model's own material, where it touches that model and
    nothing else.
    """

    def rig(self):
        from twitchoglc import weapons
        return firstperson.view_rig(
            firstperson.WeaponHand(weapons.default_table()))

    def test_nothing_in_the_rig_lights_the_world(self):
        from OpenGLContext.scenegraph.light import PointLight
        lights = [child for child in self.rig().children
                  if isinstance(child, PointLight)]
        assert lights == [], (
            'a light on the camera relights the map, which is baked')

    def test_the_hand_is_in_the_rig(self):
        from twitchoglc import weapons
        hand = firstperson.WeaponHand(weapons.default_table())
        assert hand.group in list(firstperson.view_rig(hand).children)

    def test_every_shipped_weapon_carries_its_own_fill(self):
        """Emission in the material is what keeps it visible in a dark map."""
        import json
        import struct
        from twitchoglc import weapons

        for weapon in weapons.default_table().weapons:
            data = open(weapons.model_path(weapon), 'rb').read()
            length = struct.unpack('<I', data[8:12])[0]
            off, document = 12, None
            while off < length:
                clen, ctype = struct.unpack('<II', data[off:off + 8])
                if ctype == 0x4E4F534A:
                    document = json.loads(data[off + 8:off + 8 + clen])
                    break
                off += 8 + clen
            for material in document.get('materials', []):
                emissive = material.get('emissiveFactor', [0, 0, 0])
                assert max(emissive) > 0, (
                    '%s would be a silhouette in a map' % (weapon.key,))

    def test_the_fill_is_small_enough_not_to_glow(self):
        """It is a floor under the lighting, not a light source."""
        import importlib.util
        import os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec = importlib.util.spec_from_file_location(
            'prepare_weapon', os.path.join(root, 'tools', 'prepare_weapon.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        DEFAULT_FILL = module.DEFAULT_FILL
        assert 0 < DEFAULT_FILL <= 0.15
