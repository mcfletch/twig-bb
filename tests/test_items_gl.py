"""The half of a pickup's art that only a real driver can settle: does it draw?

What each health pack is *worth* is arithmetic and is tested without a window.
What is left is the thing a headless test cannot see and a player cannot miss:
that the medikit reaches the framebuffer at all, and that the four of them
reach it in four different colours.

Both halves of that matter, and for a reason this project has already been
bitten by once (see :mod:`tests.test_combat_gl`): geometry can load, place and
pass every arithmetic test while drawing nothing under the pass the game
actually renders with.  A model behind glass is a particularly good way to
manage it, because the bubble is 85% transparent and goes through the
transparent pass rather than the opaque one.

Deliberately shallow, like its neighbour.  It asserts that pixels appeared and
that they differ, and nothing about how any of it *looks*.
"""

from __future__ import annotations

import numpy as np
import pytest

# Imported for its side effects as much as for the fixture: it selects the
# renderer, profile and backend the game itself uses, before any GL import.
from test_combat_gl import AHEAD, _lit, render        # noqa: F401

from OpenGLContext.scenegraph.transform import Transform

from twig_bb import game, items

pytestmark = [pytest.mark.gl]

#: The four that share the medikit, worst to best.
HEALTH = ('health-small', 'health', 'health-large', 'health-mega')


def level(key, at=(0.0, 0.0, AHEAD)):
    """A level holding a single pickup of one kind, in front of the camera."""
    table = items.default_table()
    return items.Pickups([items.Pickup(kind=table.by_key(key),
                                       position=np.asarray(at, dtype='d'))])


class TestTheMedikitDraws:
    def test_a_health_pickup_reaches_the_framebuffer(self, render):
        where = level('health')
        group, bodies = game.item_bodies(where)
        game.move_items(where, bodies, now=0.0)
        assert _lit(render([group])) > 0

    def test_several_of_a_kind_draw_in_several_places(self, render):
        """The subtree is shared between them, and sharing must not mean *one*.

        A map places several health packs and they are one loaded model under
        several transforms.  If a shared node were drawn once, or drawn at only
        one of its parents, the arithmetic tests would all still pass.
        """
        table = items.default_table()
        where = items.Pickups([
            items.Pickup(kind=table.by_key('health'),
                         position=np.array([across, 0.0, AHEAD]))
            for across in (-1.2, 0.0, 1.2)])
        group, bodies = game.item_bodies(where)
        game.move_items(where, bodies, now=0.0)
        three = _lit(render([group]))
        for taken in (0, 2):
            where.items[taken].waiting = 10.0
        game.move_items(where, bodies, now=0.0)
        assert three > _lit(render()) * 2.5

    def test_one_that_has_been_taken_draws_nothing(self, render):
        """Parked out of sight, not merely stopped from being collected."""
        where = level('health')
        group, bodies = game.item_bodies(where)
        game.move_items(where, bodies, now=0.0)
        assert _lit(render([group])) > 0
        where.items[0].waiting = 10.0
        game.move_items(where, bodies, now=0.0)
        assert _lit(render()) == 0


class TestTheyDoNotAllLookTheSame:
    """The colour is the whole signal; two of them alike is one pickup."""

    def test_each_health_pack_draws_a_different_picture(self, render):
        """All four are in the scene throughout and three are parked offstage.

        The scene is gathered once and swapping a node's ``children`` after
        that is not seen — so this shows one at a time the way the game itself
        does, by moving the other three out of sight (:func:`game.move_items`).
        """
        table = items.default_table()
        holders = [Transform(translation=game.OFFSTAGE,
                             children=[game.item_look(table.by_key(key))])
                   for key in HEALTH]
        render(holders)
        seen = []
        for index, key in enumerate(HEALTH):
            for slot, holder in enumerate(holders):
                holder.translation = ((0.0, 0.0, AHEAD) if slot == index
                                      else game.OFFSTAGE)
            seen.append(render().astype(int))
            assert _lit(seen[-1]) > 0, '%s drew nothing' % (key,)
        for index, first in enumerate(seen):
            for offset, second in enumerate(seen[index + 1:]):
                apart = int(np.abs(first - second).max())
                assert apart > 20, '%s and %s differ by only %d' % (
                    HEALTH[index], HEALTH[index + 1 + offset], apart)
