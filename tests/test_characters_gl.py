"""The half of an armed combatant that only a real driver can settle.

Which clip a body plays and what it is carrying are arithmetic, and are tested
without a window in :mod:`tests.test_characters`.  What is left is what a
player would notice and no headless test can see: that a bot actually appears
holding its weapon, and that several bots holding the same one all do.

That second case is the trap this file exists for.  One weapon model is loaded
per key and **shared** between everybody carrying it, so a subtree that were
drawn once, or drawn at only one of its parents, would leave one bot armed and
the rest waving empty hands -- with every arithmetic test still green.  The
pickups were bitten by exactly this (see :mod:`tests.test_items_gl`).

Deliberately shallow, like its neighbours: it asserts that pixels appeared
where they should have and nothing about how any of it looks.
"""

from __future__ import annotations

import numpy as np
import pytest

# Imported for its side effects as much as for the fixture: it selects the
# renderer, profile and backend the game itself uses, before any GL import.
from test_combat_gl import AHEAD, _lit, render        # noqa: F401

from OpenGLContext.scenegraph.transform import Transform

from twig_bb import characters, weapons

pytestmark = [pytest.mark.gl]


def armed(weapon='rifle', ids=('bot0',)):
    """A cast holding one weapon each, posed as if carrying it."""
    cast = characters.Cast(list(ids),
                           armoury=characters.Armoury(weapons.default_table()))
    for id in ids:
        cast.update(id, characters.Motion(weapon=weapon), 0.1)
    return cast


def standing(cast, ids, at=AHEAD):
    """Each figure on its own transform, spread across the view."""
    spread = np.linspace(-1.2, 1.2, len(ids)) if len(ids) > 1 else [0.0]
    return [Transform(translation=(float(x), -1.0, at),
                      children=[cast.subtree(id)])
            for id, x in zip(ids, spread, strict=True)]


class TestABotHoldingItsWeapon:
    def test_a_figure_reaches_the_framebuffer(self, render):
        cast = armed()
        assert _lit(render(standing(cast, ['bot0']))) > 0

    def test_the_weapon_draws_as_well_as_the_body(self, render):
        """More is lit with a rifle in the hand than without one.

        The *pose* is held while the weapon is taken away, because a figure
        that stopped carrying would also stop playing the carry clip -- and a
        difference that is really a change of stance would prove nothing about
        whether the rifle ever reached the framebuffer.
        """
        cast = armed()
        scene = standing(cast, ['bot0'])
        with_weapon = _lit(render(scene))
        cast.of('bot0').drop()
        assert _lit(render(scene)) < with_weapon

    def test_every_bot_carrying_one_is_drawn_with_it(self, render):
        """The shared subtree is drawn at each of its parents, not one of them."""
        ids = ['bot0', 'bot1', 'bot2']
        cast = armed(ids=ids)
        held = [cast.of(one)._held for one in ids]
        assert len({id(node) for node in held}) == 1, 'one model, shared'
        scene = standing(cast, ids)
        three = _lit(render(scene))
        for one in ids[1:]:
            cast.of(one).drop()
        assert _lit(render(scene)) < three
