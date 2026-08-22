"""Which rooms a map says can be seen from which.

A level is mostly walls, and the frustum is not told about them: a pickup two
rooms ahead is straight in front of the camera and passes every test the
renderer has. The map carries the answer, and these are the tests that it is
read the way the file means it.

The set is *potentially* visible and therefore conservative: whatever it rejects
is certainly out of sight, and some of what it keeps is behind a wall anyway. So
what has to be true is that it never rejects something visible -- everything
here that cannot be answered is answered "visible".
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

from twig_bb import visibility
from twig_bb.visibility import NO_CLUSTER, Visibility


def vectors(rows):
    """A visdata lump for ``rows``, each an iterable of visible clusters."""
    width = max(1, (max((max(r) for r in rows if r), default=0) // 8) + 1)
    body = bytearray()
    for row in rows:
        vector = bytearray(width)
        for cluster in row:
            vector[cluster >> 3] |= 1 << (cluster & 7)
        body += vector
    return struct.pack('<ii', len(rows), width) + bytes(body)


PLANE = np.dtype([('normal', '<f4', 3), ('distance', '<f4')])
NODE = np.dtype([('plane', '<i4'), ('children', '<i4', 2),
                 ('mins', '<i4', 3), ('maxs', '<i4', 3)])
LEAF = np.dtype([('cluster', '<i4'), ('area', '<i4'), ('mins', '<i4', 3),
                 ('maxs', '<i4', 3), ('leafface', '<i4'),
                 ('num_leaffaces', '<i4'), ('leafbrush', '<i4'),
                 ('num_leafbrushes', '<i4')])


def two_rooms(seen=((0,), (1,))):
    """A world split at x=0: leaf 0 (cluster 0) in front, leaf 1 behind."""
    planes = np.zeros(1, dtype=PLANE)
    planes[0] = ((1.0, 0.0, 0.0), 0.0)
    nodes = np.zeros(1, dtype=NODE)
    # SPEC-BSP46 4.3.1: a negative child denotes leaf -(child) - 1.
    nodes[0] = (0, (-1, -2), (0, 0, 0), (0, 0, 0))
    leafs = np.zeros(2, dtype=LEAF)
    leafs[0]['cluster'] = 0
    leafs[1]['cluster'] = 1
    return Visibility(nodes=nodes, leafs=leafs, planes=planes,
                      visdata=vectors(list(seen)))


class TestFindingWhichRoomAPointIsIn:
    """Descending the tree by which side of each plane the point falls."""

    def test_a_point_in_front_of_the_plane_is_the_front_leaf(self):
        assert two_rooms().cluster_at((10.0, 0.0, 0.0)) == 0

    def test_a_point_behind_it_is_the_back_leaf(self):
        assert two_rooms().cluster_at((-10.0, 0.0, 0.0)) == 1

    def test_a_point_exactly_on_the_plane_takes_the_front(self):
        """At or in front, so a point on a wall is never in no room at all."""
        assert two_rooms().cluster_at((0.0, 0.0, 0.0)) == 0

    def test_a_map_with_no_tree_says_nothing(self):
        assert Visibility().cluster_at((0.0, 0.0, 0.0)) == NO_CLUSTER


class TestWhatOneRoomSees:

    def test_a_room_sees_what_its_vector_names(self):
        found = two_rooms(seen=((0, 1), (1,)))
        assert found.sees(0, 1) and found.sees(0, 0)

    def test_a_room_does_not_see_what_its_vector_omits(self):
        found = two_rooms(seen=((0,), (1,)))
        assert not found.sees(0, 1)
        assert not found.sees(1, 0)

    def test_the_answer_need_not_be_symmetric(self):
        """One room may see into another that cannot see back; the file says."""
        found = two_rooms(seen=((0, 1), (1,)))
        assert found.sees(0, 1) and not found.sees(1, 0)

    @pytest.mark.parametrize('here,there', [
        (NO_CLUSTER, 0), (0, NO_CLUSTER), (99, 0), (0, 9999),
    ])
    def test_a_question_it_cannot_answer_is_answered_visible(self, here, there):
        """Not knowing has to mean drawing it: the set is what may be rejected."""
        assert two_rooms(seen=((0,), (1,))).sees(here, there)

    def test_a_map_with_no_visibility_data_sees_everything(self):
        assert Visibility().sees(0, 1)
        assert not Visibility()


class TestTheMaskForAskingAboutMany:
    """One unpacking of the standing room's vector, for a level's worth."""

    def test_the_mask_agrees_with_asking_one_at_a_time(self):
        found = two_rooms(seen=((0, 1), (1,)))
        mask = found.visible_from((10.0, 0.0, 0.0))
        assert mask is not None
        for cluster in (0, 1):
            assert bool(mask[cluster]) == found.sees(0, cluster)

    def test_no_data_is_no_mask_rather_than_an_empty_one(self):
        """None means "all of it", where an empty mask would mean "none"."""
        assert Visibility().visible_from((0.0, 0.0, 0.0)) is None


class TestContentThisCannotRead:
    """A map is drawn whether or not its visibility can be made sense of."""

    def test_a_truncated_lump_is_a_map_with_no_culling(self, caplog):
        cut = vectors([(0, 1), (1,)])[:-1]
        found = Visibility(visdata=cut)
        assert not found and found.sees(0, 1)

    def test_a_header_claiming_nothing_is_no_data(self):
        assert not Visibility(visdata=struct.pack('<ii', 0, 0))

    def test_a_lump_too_short_for_a_header_is_no_data(self):
        assert not Visibility(visdata=b'\x00\x00')

    def test_a_tree_that_never_reaches_a_leaf_gives_up(self):
        """A child pointing back up the tree must not spin for ever."""
        planes = np.zeros(1, dtype=PLANE)
        planes[0] = ((1.0, 0.0, 0.0), 0.0)
        nodes = np.zeros(1, dtype=NODE)
        nodes[0] = (0, (0, 0), (0, 0, 0), (0, 0, 0))     # points at itself
        found = Visibility(nodes=nodes, leafs=np.zeros(1, dtype=LEAF),
                           planes=planes, visdata=vectors([(0,)]))
        assert found.cluster_at((1.0, 0.0, 0.0)) == NO_CLUSTER


class TestWhichPickupsAreWorthDrawing:
    """``game.ItemRooms`` over a map's pickups, from where the player stands."""

    def pickups(self, *positions):
        from twig_bb import items
        kind = items.ItemKind(key='test', title='TEST', health=25)
        return items.Pickups([
            items.Pickup(kind=kind, position=np.array(at, dtype='d'))
            for at in positions])

    def rooms(self, seen, *positions):
        from twig_bb import game
        return game.ItemRooms(two_rooms(seen=seen), self.pickups(*positions))

    def test_a_pickup_in_a_room_the_camera_sees_is_drawn(self):
        from twig_bb.worldgeometry import to_scene_points
        here = to_scene_points([[10.0, 0.0, 0.0]])[0]
        there = to_scene_points([[20.0, 0.0, 0.0]])[0]
        found = self.rooms(((0,), (1,)), there)
        assert list(found.drawable(here)) == [True]

    def test_a_pickup_in_a_room_it_cannot_see_is_not(self):
        from twig_bb.worldgeometry import to_scene_points
        here = to_scene_points([[10.0, 0.0, 0.0]])[0]
        behind = to_scene_points([[-20.0, 0.0, 0.0]])[0]
        found = self.rooms(((0,), (1,)), behind)
        assert list(found.drawable(here)) == [False]

    def test_a_map_with_no_visibility_draws_everything(self):
        from twig_bb import game
        from twig_bb.worldgeometry import to_scene_points
        found = game.ItemRooms(Visibility(), self.pickups((0.0, 0.0, 0.0)))
        assert found.drawable(to_scene_points([[0.0, 0.0, 0.0]])[0]) is None

    def test_no_camera_is_no_answer_rather_than_nothing_drawn(self):
        assert self.rooms(((0,), (1,)), (0.0, 0.0, 0.0)).drawable(None) is None

    def test_a_level_with_no_pickups_is_no_answer(self):
        from twig_bb.worldgeometry import to_scene_points
        assert self.rooms(((0,), (1,))).drawable(
            to_scene_points([[10.0, 0.0, 0.0]])[0]) is None
